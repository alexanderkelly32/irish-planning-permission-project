"""Runner: JR (judicial review) conditional priors from the 4Dublin pipeline.

JR is post-decision, Dublin-only evidence (courts data not published in bulk
nationally). Fits no model - produces honest conditional prevalence priors:
JR concentrates almost entirely in LRD and SHD applications.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

if __name__ == "__main__":
    pipeline = pd.read_csv(settings.SILVER_DIR / "4dublin" / "pipeline_all.csv", low_memory=False)
    dublin = {"Dublin City Council", "Dun Laoghaire Rathdown County Council", "Fingal County Council", "South Dublin County Council"}
    pipeline = pipeline[pipeline["Planning_Authority"].isin(dublin)]
    pipeline["app_norm"] = pipeline["Planning_Reference"].astype(str).str.upper().str.replace(r"\s+", "", regex=True)
    latest = pipeline.sort_values("Year_Quarter").groupby("app_norm").tail(1)
    latest["jr_flag"] = latest["JR_Reference"].notna() | latest["Subject_to_Live_JR"].fillna("").astype(str).str.upper().eq("YES")

    report = {
        "source": "4Dublin pipeline (Dublin only), latest quarter per reference",
        "n_records": int(len(latest)),
        "jr_flagged": int(latest["jr_flag"].sum()),
        "overall_rate": round(float(latest["jr_flag"].mean()), 4),
        "by_app_type": {
            str(k): {"n": int(len(v)), "jr": int(v["jr_flag"].sum()), "rate": round(float(v["jr_flag"].mean()), 4)}
            for k, v in latest.groupby("App_Type", dropna=False)
        },
        "by_authority": {
            str(k): {"n": int(len(v)), "jr": int(v["jr_flag"].sum()), "rate": round(float(v["jr_flag"].mean()), 4)}
            for k, v in latest.groupby("Planning_Authority", dropna=False)
        },
        "note": "post-submission event; evidence-grade priors only, never submission-time model features",
    }
    out = settings.SILVER_DIR / "jr_priors.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
