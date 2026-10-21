"""Phase 4: parse conditions from downloaded iDocs texts + forensics ablation.

Per scheme: concatenate Schedule of Conditions texts, split into numbered
conditions, flag pre-commencement + category. Compare fast vs slow residual
groups on condition burden. Outputs: idocs/condition_forensics.csv + report.
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

DOCS = settings.SILVER_DIR / "idocs" / "docs"

PRE_COMM_RE = re.compile(
    r"prior to (?:the )?(?:commencement|any development|construction|the ?submission)|"
    r"before (?:any )?(?:development|construction|works) commenc|"
    r"shall be (?:submitted|agreed|paid|lodged|provided) (?:to the planning authority )?prior to", re.I)
NUMBER_LINE_RE = re.compile(r"^\s*(\d{1,2}|l)\s*[\.\)]\s*$", re.I)
NUMBER_INLINE_RE = re.compile(r"^\s*(\d{1,2}|l)[\.\)]\s*\(?[a-z]?\)?\s*[A-Z(]", re.I)
PAGE_FOOTER_RE = re.compile(r"page\s*\d+?\s*of\s*\d+|inspection purposes only", re.I)
SPLIT_RE = re.compile(r"(\d{1,2}|l)\.\s*\(?([a-z])?\)?\s*([A-Z])")


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_conditions(text: str) -> list[str]:
    text = SPLIT_RE.sub(lambda m: f"\n{m.group(1)}.{m.group(2) or ''}{m.group(3)}", text)
    m = re.search(r"schedule of conditions|conditions attached|GENERAL", text, re.I)
    body = text[m.start():] if m else text
    conds = []
    current = []
    for line in body.splitlines():
        if NUMBER_LINE_RE.match(line) or NUMBER_INLINE_RE.match(line):
            if current:
                conds.append(norm(" ".join(current)))
                current = []
        current.append(re.sub(NUMBER_LINE_RE, "", line).strip())
    if current:
        conds.append(norm(" ".join(current)))
    return [c for c in conds if len(c) > 40 and not PAGE_FOOTER_RE.search(c)]
FINANCIAL_RE = re.compile(r"contribution|bond|security|financial|levy", re.I)
ARCH_RE = re.compile(r"archaeolog", re.I)
ECOL_RE = re.compile(r"ecolog|habitat|bat |bird|tree|natura|landscap", re.I)
UISCE_RE = re.compile(r"uisce|irish water|water supply|wastewater|sewer|drainage|attenuation", re.I)
ROADS_RE = re.compile(r"road|access|footpath|cycle|traffic|junction|roundabout|car park", re.I)
PHASING_RE = re.compile(r"phas", re.I)


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def main() -> None:
    with zipfile.ZipFile(settings.SILVER_DIR / "audit_packs" / "PACK_24_residual_forensics.zip") as z:
        cohort = pd.read_csv(z.open("residual_forensics_cohort.csv"))
    rows = []
    for text_path in sorted(DOCS.glob("*/*_text.json")):
        data = json.loads(text_path.read_text(encoding="utf-8"))
        key = text_path.parent.name.replace("_", " ")[:80]
        sched = [v.get("text", "") for k, v in data.items()
                 if "schedule of conditions" in k.lower() and v.get("status") == "ok"]
        grants = [v.get("text", "") for k, v in data.items()
                  if "final grant" in k.lower() and v.get("status") == "ok" and "schedule" not in k.lower()]
        ceo = [v.get("text", "") for k, v in data.items()
               if "chief executives order" in k.lower() and v.get("status") == "ok"]
        primary = "\n".join(sched + grants + ceo)
        full = primary
        if len(norm(primary)) < 2000:
            planner = [v.get("text", "") for k, v in data.items()
                       if "planners report" in k.lower() and v.get("status") == "ok"]
            full = primary + "\n" + "\n".join(planner)
        if not norm(full):
            continue
        conds = parse_conditions(full)
        if not conds:
            continue
        n_pre = sum(1 for c in conds if PRE_COMM_RE.search(c))
        row = {"case_key": key, "n_conditions": len(conds), "n_precommencement": n_pre,
               "n_financial": sum(1 for c in conds if FINANCIAL_RE.search(c)),
               "n_financial_pre": sum(1 for c in conds if FINANCIAL_RE.search(c) and PRE_COMM_RE.search(c)),
               "n_arch": sum(1 for c in conds if ARCH_RE.search(c)),
               "n_arch_pre": sum(1 for c in conds if ARCH_RE.search(c) and PRE_COMM_RE.search(c)),
               "n_ecol": sum(1 for c in conds if ECOL_RE.search(c)),
               "n_uisce": sum(1 for c in conds if UISCE_RE.search(c)),
               "n_roads": sum(1 for c in conds if ROADS_RE.search(c)),
               "n_phasing": sum(1 for c in conds if PHASING_RE.search(c))}
        rows.append(row)
    feats = pd.DataFrame(rows)
    feats.to_csv(settings.SILVER_DIR / "idocs" / "condition_forensics.csv", index=False)
    cohort["case_key_clean"] = cohort["case_key"].str.replace(" ", "_").str[:80]
    feats["case_key_clean"] = feats["case_key"].str.replace(" ", "_").str[:80]
    merged = cohort.merge(feats, on="case_key_clean", how="inner")
    report = {
        "schemes_with_parsed_conditions": int(len(merged)),
        "median_conditions": round(float(feats["n_conditions"].median()), 1),
        "median_precommencement": round(float(feats["n_precommencement"].median()), 1),
        "median_financial": round(float(feats["n_financial"].median()), 1),
        "median_arch": round(float(feats["n_arch"].median()), 1),
    }
    if len(merged) >= 6 and merged["residual_group"].nunique() == 2:
        fast = merged[merged["residual_group"].str.contains("fast", case=False, na=False)]
        slow = merged[merged["residual_group"].str.contains("slow", case=False, na=False)]
        report.update({
            "n_fast": int(len(fast)), "n_slow": int(len(slow)),
            "fast_median_precommencement": round(float(fast["n_precommencement"].median()), 1),
            "slow_median_precommencement": round(float(slow["n_precommencement"].median()), 1),
            "fast_median_financial": round(float(fast["n_financial"].median()), 1),
            "slow_median_financial": round(float(slow["n_financial"].median()), 1),
            "fast_median_arch": round(float(fast["n_arch"].median()), 1),
            "slow_median_arch": round(float(slow["n_arch"].median()), 1),
            "fast_median_conditions": round(float(fast["n_conditions"].median()), 1),
            "slow_median_conditions": round(float(slow["n_conditions"].median()), 1),
        })
    out = settings.SILVER_DIR / "idocs" / "condition_forensics_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
