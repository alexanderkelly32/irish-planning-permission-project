"""v4 wording service: make the description text work like an instrument.

- highlight_description: your own text with risk-raising / risk-lowering
  phrases highlighted, hover to see the measured phrase effect and how often
  the phrase appears in the historical record
- rewrite_variants: 2-3 concrete alternative descriptions aligned with
  granted schemes of your typology, each rescored against your proposal with
  the delta shown. Variants are generated locally from measured phrase
  effects and granted comparable descriptions - no LLM.

All deltas are model-attributed sensitivity statements, not guarantees.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
for scripts_dir in (ROOT / "05_policy" / "scripts", ROOT / "06_copilot" / "scripts"):
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

from model_feature_builder import score_proposal  # noqa: E402

PHRASE_EFFECTS = ROOT / "05_policy" / "current" / "text_phrase_pp_effects.json"
NEWBUILD_LOWERING = ROOT / "05_policy" / "current" / "text_newbuild_lowering_phrases.json"
VOCAB_COEFS = ROOT / "05_policy" / "current" / "text_vocabulary_coefficients.csv"

PHRASES_BY_KIND = {
    "new build": [
        ("semi detached", "house form"),
        ("residential development", "scheme wording"),
        ("duplex apartments", "apartment type"),
        ("landscaped open space", "open space"),
        ("bicycle parking", "parking"),
        ("community facilities", "amenity"),
        ("masonry construction", "finish"),
        ("brick finish", "finish"),
        ("single storey", "height"),
    ],
    "extension": [
        ("single storey extension", "extension type"),
        ("ground floor extension", "extension type"),
        ("room extension", "extension type"),
        ("conservatory", "extension type"),
        ("rooflights", "extension detail"),
        ("porch", "extension detail"),
        ("garage conversion", "conversion type"),
    ],
    "one-off house": [
        ("masonry construction", "finish"),
        ("brick finish", "finish"),
        ("landscaping works", "open space"),
        ("private open space", "open space"),
    ],
}
CONFLICT_GROUPS = {
    "semi detached": ["terraced", "detached", "end of terrace"],
    "residential development": ["housing development", "housing estate"],
    "masonry construction": ["timber", "timber frame"],
    "brick finish": ["timber", "timber frame", "render"],
    "duplex apartments": ["apartment block"],
    "single storey": ["two storey", "three storey", "four storey"],
    "single storey extension": ["two storey extension", "first floor extension"],
    "ground floor extension": ["first floor extension"],
    "room extension": [],
    "conservatory": [],
    "rooflights": ["velux"],
    "porch": [],
    "garage conversion": [],
    "bicycle parking": [],
    "landscaped open space": [],
    "landscaping works": [],
    "private open space": ["communal open space", "public open space"],
    "community facilities": [],
}

SWAPS = [
    ("housing development", "residential development"),
    ("housing estate", "residential development"),
    ("apartment block", "duplex apartment block"),
    ("terraced", "semi detached"),
    ("detached", "semi detached"),
    ("timber frame", "masonry construction"),
    ("communal open space", "private open space"),
    ("public open space", "landscaped open space"),
]


def _fix_articles(text: str) -> str:
    fixed = re.sub(r"\ban\s+(duplex|residential|semi|masonry|landscaped)\b", r"a \1", text, flags=re.IGNORECASE)
    fixed = re.sub(r"\ba\s+(apartment)\b", "an apartment", fixed, flags=re.IGNORECASE)
    return fixed

UNIT_CONTEXT = re.compile(
    r"(?:no\.?|number of|units?|apartments?|dwellings?|houses?|homes?|residential units?|residential)",
    re.IGNORECASE,
)


def detect_scheme_kind(description: str, units: int) -> str:
    text = (description or "").lower()
    extension_words = ["extension", "alteration", "conversion", "retention", "conservatory", "porch", "dormer"]
    new_build_words = ["apartment", "development", "estate", "dwelling", "houses", "dwellings", "units"]
    if any(word in text for word in extension_words) and units <= 2:
        return "extension"
    if units == 1 and not any(word in text for word in extension_words):
        return "one-off house"
    return "new build"


def _load_effects() -> dict:
    effects = json.loads(PHRASE_EFFECTS.read_text(encoding="utf-8"))
    newbuild = json.loads(NEWBUILD_LOWERING.read_text(encoding="utf-8"))
    effect_map = {r["term"]: r for r in effects["effects"]}
    vocab = pd.read_csv(VOCAB_COEFS)
    freq_map = {str(r["term"]): int(r["approx_document_frequency"]) for _, r in vocab.iterrows()}
    return {"effect_map": effect_map, "newbuild": newbuild, "freq_map": freq_map}


def phrase_highlights(description: str, artifact) -> list[dict]:
    """Risk-raising and risk-lowering phrases found in the description with spans."""
    pre = artifact["ranking_model"].named_steps["preprocessor"]
    model = artifact["ranking_model"].named_steps["model"]
    vectorizer = pre.named_transformers_["txt"]
    coefs = model.coef_[0]
    names = pre.get_feature_names_out()
    coef_map = {}
    for full, coef in zip(names, coefs):
        if full.startswith("txt__"):
            coef_map[full.split("__", 1)[1]] = float(coef)
    effects = _load_effects()
    effect_map = effects["effect_map"]
    freq_map = effects["freq_map"]

    text = description or ""
    lower = text.lower()
    grams = set(vectorizer.build_analyzer()(lower))
    found: list[dict] = []
    for gram in grams:
        words = gram.split()
        if len(words) < 2 or all(w.isdigit() for w in words) or all(len(w) < 3 for w in words):
            continue
        if gram not in coef_map:
            continue
        positions = [m.start() for m in re.finditer(re.escape(gram), lower)]
        if not positions:
            continue
        effect = effect_map.get(gram)
        found.append({
            "term": gram,
            "coefficient": round(coef_map[gram], 3),
            "pp_change": round(effect["pp_change_vs_baseline"], 1) if effect else None,
            "doc_frequency": freq_map.get(gram),
            "start": positions[0],
            "end": positions[0] + len(gram),
        })
    found.sort(key=lambda item: -abs(item["coefficient"]))
    raising = [f for f in found if f["coefficient"] > 0.05]
    lowering = [f for f in found if f["coefficient"] < -0.05]
    return {"raising": raising[:10], "lowering": lowering[:10], "all": found[:24]}


def highlighted_description_html(description: str, artifact) -> str:
    """Escaped description with colour-coded spans and hover tooltips."""
    highlights = phrase_highlights(description, artifact)
    spans = sorted(
        highlights["raising"] + highlights["lowering"],
        key=lambda h: (h["start"], -h["end"]),
    )
    text = description or ""
    out: list[str] = []
    cursor = 0
    for item in spans:
        if item["start"] < cursor:
            continue
        out.append(html.escape(text[cursor:item["start"]]))
        kind = "raising" if item["coefficient"] > 0 else "lowering"
        colour = "#c0392b" if kind == "raising" else "#1e8449"
        pp = f", {item['pp_change']:+.1f}pp in the standard scheme" if item["pp_change"] is not None else ""
        freq = f", appears in {item['doc_frequency']:,} historical cases" if item["doc_frequency"] else ""
        tooltip = html.escape(
            f"{item['term']}: coefficient {item['coefficient']:+.2f}{pp}{freq}"
        )
        out.append(
            f'<span style="background-color:{colour}22;border-bottom:2px solid {colour};cursor:help;" '
            f'title="{tooltip}">{html.escape(text[item["start"]:item["end"]])}</span>'
        )
        cursor = item["end"]
    out.append(html.escape(text[cursor:]))
    return "".join(out)


def _splice_numbers(template: str, units: float | None, site_sqm: float | None) -> str:
    """Replace unit-context numbers in a granted comparable description with the
    user's counts. Keeps the granted scheme's structure, corrects the quantities."""
    text = template
    if units is not None and units > 0:
        pattern = re.compile(r"\d{1,4}(?=\s*(?:no\.?|number of|units?|apartments?|dwellings?|houses?|homes?))", re.IGNORECASE)
        text = pattern.sub(str(int(units)), text, count=1)
    return text


def _similarity_ratio(original: str, variant: str) -> float:
    words_a = set(re.findall(r"[a-z\u00e9\u00ed\u00fa\u00e1\u00f3]+", original.lower()))
    words_b = set(re.findall(r"[a-z\u00e9\u00ed\u00fa\u00e1\u00f3]+", variant.lower()))
    if not words_a or not words_b:
        return 0.0
    return round(len(words_a & words_b) / len(words_a | words_b), 2)


def rewrite_variants(proposal: dict, k: int = 3) -> list[dict]:
    """2-3 rewritten descriptions with rescored deltas."""
    description = str(proposal.get("description") or "")
    units = proposal.get("units")
    kind = detect_scheme_kind(description, int(units or 0))
    effects = _load_effects()
    baseline = score_proposal(proposal)["refusal_probability"]
    variants: list[dict] = []

    comparable = None
    try:
        from v4_evidence_service import matched_precedents

        comparable = matched_precedents(proposal, k=20)
        granted = [c for c in comparable["precedents"] if c["outcome"] == "Granted" and len(c["description"]) > 60]
    except Exception:
        comparable = None
    if comparable is None:
        from v4_evidence_service import comparable_details

        comparable = comparable_details(proposal, k=20)
        granted = [c for c in comparable["comparables"] if c["outcome"] == "Granted" and len(c["description"]) > 60]
    if granted:
        template = granted[0]["description"]
        spliced = _splice_numbers(template, units, proposal.get("site_area_sqm"))
        variants.append({
            "label": "Phrasing of the closest granted scheme (quantities corrected to yours)",
            "description": spliced,
            "source": f"{granted[0]['council']} {granted[0]['application_number']} (granted {granted[0]['decision_date'] or granted[0]['received_date']})",
            "similarity_to_yours": _similarity_ratio(description, spliced),
            "rationale": "Adopts the structure and wording of a granted application of the same type and size.",
        })

    lower_phrases = []
    for phrase, _kind in PHRASES_BY_KIND.get(kind, PHRASES_BY_KIND["new build"]):
        if phrase in description.lower():
            continue
        if any(conflict in description.lower() for conflict in CONFLICT_GROUPS.get(phrase, [])):
            continue
        effect = effects["effect_map"].get(phrase)
        pp = effect["pp_change_vs_baseline"] if effect else 0.0
        lower_phrases.append((phrase, pp))
    for term in [r["term"] for r in effects["newbuild"]["effects"]]:
        if kind != "new build":
            break
        if term in description.lower():
            continue
        effect = effects["effect_map"].get(term)
        pp = effect["pp_change_vs_baseline"] if effect else 0.0
        lower_phrases.append((term, pp))
    lower_phrases.sort(key=lambda pair: pair[1])
    additions = [p for p, _ in lower_phrases if p not in description.lower()][:3]
    if additions:
        joined = ", ".join(f"with {phrase}" for phrase in additions)
        variants.append({
            "label": "Add accurate-type phrases used by granted schemes",
            "description": f"{description} {joined}",
            "source": "measured phrase effects on the standard 12-unit scheme",
            "similarity_to_yours": _similarity_ratio(description, f"{description} {joined}"),
            "rationale": "Appends phrases that describe the scheme accurately and appear most often in granted applications of this type.",
        })

    swapped: list[str] = []
    new_text = description
    for risky, safe in SWAPS:
        if risky in new_text.lower() and safe not in new_text.lower():
            new_text = re.sub(re.escape(risky), safe, new_text, flags=re.IGNORECASE)
            swapped.append(f"{risky} -> {safe}")
    if swapped:
        new_text = _fix_articles(new_text)
    if swapped:
        variants.append({
            "label": "Align risky wording with granted-scheme equivalents",
            "description": new_text,
            "source": "phrase equivalence pairs measured on historical outcomes",
            "similarity_to_yours": _similarity_ratio(description, new_text),
            "rationale": f"Swaps: {'; '.join(swapped)}. Only keep a swap if it still describes the scheme truthfully.",
        })

    scored: list[dict] = []
    for variant in variants[:k]:
        try:
            new_risk = score_proposal({**proposal, "description": variant["description"]})["refusal_probability"]
        except Exception:
            continue
        variant["refusal_probability"] = round(new_risk, 4)
        variant["delta_pp"] = round((new_risk - baseline) * 100, 1)
        scored.append(variant)
    scored.sort(key=lambda v: v["delta_pp"])
    return {"baseline_refusal_probability": baseline, "kind": kind, "variants": scored}
