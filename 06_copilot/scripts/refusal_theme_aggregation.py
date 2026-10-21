"""Source-linked refusal-theme aggregation for comparable refused cases."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from precedent_copilot_logic import THEME_LABELS, clean_text, short_text

REFUSAL_CASES_DEFAULT_PATH = (
    Path(__file__).resolve().parents[2]
    / "03_refusal"
    / "current"
    / "refusal_reasons_cases_master.csv"
)

INDEX_COLUMNS = [
    "case_key",
    "source_file",
    "available_files",
    "extraction_source",
    "extraction_method",
    "reason_count",
    "reasons_joined",
    "case_primary_tags",
    "case_top_primary_tag",
]


def build_refusal_theme_index(path: str | Path | None = None) -> pd.DataFrame:
    """Load the refusal extraction master keyed by case_key; empty frame if unavailable."""
    source = Path(path) if path else REFUSAL_CASES_DEFAULT_PATH
    empty = pd.DataFrame(columns=INDEX_COLUMNS).set_index("case_key")
    if not source.exists():
        return empty
    frame = pd.read_csv(source, low_memory=False)
    for column in INDEX_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    frame["case_key"] = frame["case_key"].fillna("").astype(str).str.strip()
    frame = frame[frame["case_key"] != ""].drop_duplicates("case_key", keep="first")
    return frame.set_index("case_key")


def extraction_provenance_label(index_row: pd.Series | dict | None) -> str:
    """Human-readable provenance for a refusal extraction, or an explicit gap note."""
    if index_row is None or not isinstance(index_row, (pd.Series, dict)):
        return "no refusal extraction record"
    source = clean_text(index_row.get("extraction_source"))
    method = clean_text(index_row.get("extraction_method"))
    parts: list[str] = []
    if source == "pdf_ocr":
        parts.append("OCR-based decision text")
    elif source == "pdf_text":
        parts.append("text-based decision document")
    elif source:
        parts.append(source)
    if method == "numbered":
        parts.append("numbered refusal reasons")
    elif method == "phrase_split":
        parts.append("phrase-split decision text")
    elif method == "not_found":
        parts.append("no discrete refusal reasons extracted")
    elif method == "fallback":
        parts.append("low-confidence extraction")
    elif method:
        parts.append(method)
    return "; ".join(parts) or "extraction provenance unavailable"


def _case_tags(row: pd.Series) -> list[str]:
    tags = clean_text(row.get("case_primary_tags"))
    if not tags:
        tags = clean_text(row.get("case_top_primary_tag"))
    return [part for part in tags.split(";") if part.strip()]


def _build_case_record(row: pd.Series, index_row: pd.Series | dict | None, excerpt_chars: int) -> dict[str, Any]:
    citation = " ".join(
        part for part in [
            clean_text(row.get("PlanningAuthority")),
            clean_text(row.get("ApplicationNumber")),
            f"({clean_text(row.get('Decision'))})" if clean_text(row.get("Decision")) else "",
        ] if part
    )
    refusal_excerpt = clean_text(row.get("refusal_excerpt"))
    if not refusal_excerpt and index_row is not None:
        refusal_excerpt = clean_text(index_row.get("reasons_joined"))
    return {
        "case_key": clean_text(row.get("case_key")),
        "citation": citation,
        "source_url": clean_text(row.get("source_url")),
        "source_file": clean_text(index_row.get("source_file")) if index_row is not None else "",
        "extraction_provenance": extraction_provenance_label(index_row),
        "reason_count": (
            int(index_row.get("reason_count"))
            if index_row is not None and pd.notna(index_row.get("reason_count"))
            else None
        ),
        "excerpt": short_text(refusal_excerpt, excerpt_chars),
    }


def aggregate_refusal_themes_sourced(
    refused: pd.DataFrame,
    refusal_index: pd.DataFrame | None = None,
    limit: int = 4,
    excerpt_chars: int = 220,
) -> dict[str, Any]:
    """Aggregate themes from comparable refused cases with per-case source linkage.

    Theme scores are similarity-weighted counts over the refused comparables only.
    They describe recurring issues in similar past decisions; they are not
    predictions about the scenario under review.
    """
    if refused.empty:
        return {
            "themes": [],
            "refused_case_count": 0,
            "tagged_case_count": 0,
            "linked_case_count": 0,
        }
    weights = pd.to_numeric(refused.get("hybrid_score"), errors="coerce").fillna(0.0) + 0.05
    theme_scores: dict[str, float] = {}
    theme_cases: dict[str, list[tuple[float, pd.Series, pd.Series | None]]] = {}
    tagged_cases = 0
    linked_cases = 0
    index_rows = {} if refusal_index is None else refusal_index.to_dict("index")
    for weight, (_, row) in zip(weights.tolist(), refused.iterrows(), strict=False):
        index_row = index_rows.get(clean_text(row.get("case_key")))
        if index_row is not None:
            linked_cases += 1
        tags = _case_tags(row)
        if not tags:
            continue
        tagged_cases += 1
        for tag in tags:
            theme_scores[tag] = theme_scores.get(tag, 0.0) + float(weight)
            theme_cases.setdefault(tag, []).append((float(weight), row, index_row))
    ranked_tags = sorted(
        theme_scores.items(),
        key=lambda item: (-item[1], -len(theme_cases.get(item[0], [])), item[0]),
    )
    themes: list[dict[str, Any]] = []
    for tag, score in ranked_tags[:limit]:
        cases = [
            _build_case_record(row, index_row, excerpt_chars)
            for _, row, index_row in sorted(theme_cases.get(tag, []), key=lambda item: -item[0])
        ]
        themes.append({
            "tag": tag,
            "label": THEME_LABELS.get(tag, tag.replace("_", " ")),
            "weighted_score": round(score, 3),
            "case_count": len(cases),
            "cases": cases,
        })
    return {
        "themes": themes,
        "refused_case_count": int(len(refused)),
        "tagged_case_count": tagged_cases,
        "linked_case_count": linked_cases,
    }


def refusal_theme_coverage_note(aggregation: dict[str, Any]) -> str:
    """Conservative coverage wording for the aggregated refusal themes."""
    refused = int(aggregation.get("refused_case_count", 0))
    tagged = int(aggregation.get("tagged_case_count", 0))
    linked = int(aggregation.get("linked_case_count", 0))
    if refused == 0:
        return ""
    return (
        f"Themes aggregate similarity-weighted, extraction-tagged refusal reasons from "
        f"{tagged} of {refused} comparable refused cases ({linked} with a matched "
        f"decision-document extraction record). Extraction is OCR/text based and "
        f"coverage is partial; themes describe recurring issues in similar past "
        f"decisions, not predictions about this scenario."
    )
