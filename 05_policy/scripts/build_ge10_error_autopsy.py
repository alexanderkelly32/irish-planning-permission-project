#!/usr/bin/env python3
"""Error autopsy for GE10 2024-2025: what do the model's mistakes share?

Buckets (from the frozen model's out-of-sample scores):
  missed refusals   refused but scored in the bottom two quintiles
  caught refusals   refused and scored in the top two quintiles
  false alarms      granted but scored in the top two quintiles
  quiet grants      granted and scored in the bottom two quintiles

Profiles each bucket and finds text markers over/under-represented in the
mistakes versus the correctly-called counterparts.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))

from build_8020_regime_experiment import build_data  # noqa: E402
from build_description_lexicon import lexicon_features  # noqa: E402

ARTIFACT = ROOT / "05_policy" / "current" / "model_v4" / "national_residential_v4_full.joblib"


def profile(sel: pd.DataFrame, label: str) -> dict:
    return {
        "label": label,
        "n": int(len(sel)),
        "median_units": round(float(sel["units"].median()), 1),
        "median_density_ha": round(float(sel["density_units_per_ha"].median()), 1),
        "flood_hit_share": round(float(sel["flood_any"].fillna(0).gt(0).mean()), 3),
        "desc_words_median": round(float(sel["description_stripped"].fillna("").str.split().str.len().median()), 1),
        "apartment_wording": round(float((sel["lex_apartment"] > 0).mean()), 3),
        "extension_wording": round(float((sel["lex_extension"] > 0).mean()), 3),
        "conversion_wording": round(float((sel["lex_conversion"] > 0).mean()), 3),
        "parking_wording": round(float((sel["lex_parking"] > 0).mean()), 3),
        "access_wording": round(float((sel["lex_access_road"] > 0).mean()), 3),
        "comp_top5_median": round(float(sel["comp_top5_refusal_rate"].median()), 3),
        "council_rate_median": round(float(sel["authority_prior_12m_refusal_rate"].median()), 3),
        "is_urban_share": round(float(sel["is_urban"].fillna(0).mean()), 3),
        "policy_covered": round(float(sel["policy_plan_covered"].mean()), 3),
        "top_councils": sel["PlanningAuthority"].value_counts().head(5).to_dict(),
    }


def text_markers(mistakes: pd.DataFrame, reference: pd.DataFrame, n: int = 12) -> list[dict]:
    def grams(sel: pd.DataFrame) -> Counter:
        counter: Counter[str] = Counter()
        for text in sel["description_stripped"].fillna(""):
            words = re.findall(r"[a-z]+", str(text).lower())
            for i in range(len(words) - 1):
                counter[" ".join(words[i:i + 2])] += 1
        return counter

    m, r = grams(mistakes), grams(reference)
    total_m, total_r = sum(m.values()) or 1, sum(r.values()) or 1
    ratios = []
    for gram, count in m.items():
        rate_m = count / total_m
        rate_r = r.get(gram, 0) / total_r
        if count >= 2 and rate_m >= rate_r * 1.8:
            ratios.append({"gram": gram, "mistakes": count, "ratio": round(rate_m / max(rate_r, 1e-6), 1)})
    ratios.sort(key=lambda x: -x["ratio"])
    return ratios[:n]


def main() -> None:
    data, train, test, y = build_data()
    lex = lexicon_features(test["description_stripped"].fillna(""))
    test = test.join(lex)
    artifact = joblib.load(ARTIFACT)
    ranking = artifact["ranking_model"]
    ge10 = test[test["units"] >= 10].copy()
    ge10["risk"] = ranking.predict_proba(ge10[artifact["feature_columns"]])[:, 1]
    ge10["quintile"] = pd.qcut(ge10["risk"], 5, labels=False)
    ge10["refused"] = ge10["target_refused"].astype(int)

    missed = ge10[(ge10["refused"] == 1) & (ge10["quintile"] <= 1)]
    caught = ge10[(ge10["refused"] == 1) & (ge10["quintile"] >= 3)]
    alarms = ge10[(ge10["refused"] == 0) & (ge10["quintile"] >= 3)]
    quiet = ge10[(ge10["refused"] == 0) & (ge10["quintile"] <= 1)]

    report = {
        "bucket_sizes": {
            "missed_refusals": int(len(missed)),
            "caught_refusals": int(len(caught)),
            "false_alarms": int(len(alarms)),
            "quiet_grants": int(len(quiet)),
        },
        "missed_refusals_profile": profile(missed, "missed"),
        "caught_refusals_profile": profile(caught, "caught"),
        "false_alarms_profile": profile(alarms, "alarms"),
        "quiet_grants_profile": profile(quiet, "quiet"),
        "missed_vs_caught_text_markers": text_markers(missed, caught),
        "alarms_vs_quiet_text_markers": text_markers(alarms, quiet),
        "missed_refusal_examples": [
            {"council": str(r["PlanningAuthority"]), "units": float(r["units"]), "risk": round(float(r["risk"]), 3), "description": str(r["description_stripped"])[:220]}
            for _, r in missed.head(6).iterrows()
        ],
    }
    (OUT / "ge10_error_autopsy.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
