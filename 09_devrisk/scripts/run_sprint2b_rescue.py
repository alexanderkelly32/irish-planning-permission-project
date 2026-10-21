"""Sprint 2b: Minimum-Change Rescue Plan - retrospective test.

Recommendations frozen on train data only (first refusal < 2021):
R1 reduce units (if current units above the conversion-median)
R2 keep the same application route/type
R3 keep description similar to refused version (trim rather than expand)
R4 do not add new technical-language families
Test on held-out pairs (first refusal >= 2021): agreement rate between
recommendations and actual successful revisions, and whether pairs that
follow the recommendations grant more. Correlational language only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "sprint2"


def main() -> None:
    frame = pd.read_csv(OUT / "refusal_grant_pairs.csv")
    train = frame[frame["year_1"] < 2021]
    test = frame[frame["year_1"] >= 2021]

    med_units = train[train["decision_2"] == "grant"]["units_2"].median()
    rec = {
        "R1_reduce_units": f"reduce units toward ~{int(med_units)} if currently above",
        "R2_keep_route": "keep the same application route/type",
        "R3_trim_description": "keep description similar to the refused version, trimmed",
        "R4_no_new_technical_families": "do not add new access/drainage/parking/height/ecology language",
    }
    test = test.copy()
    test["rec1_match"] = (test["units_reduced"] == 1) | (test["units_2"].fillna(0) <= med_units)
    test["rec2_match"] = (test["type_change"] == 0)
    test["rec3_match"] = (test["desc_len_ratio"] <= 1.3)
    test["rec4_match"] = (test["fam_access_roads_added"] + test["fam_drainage_uisce_added"] +
                          test["fam_parking_added"] + test["fam_height_storeys_added"] +
                          test["fam_ecology_added"]) == 0
    test["n_rec_matched"] = test[["rec1_match", "rec2_match", "rec3_match", "rec4_match"]].sum(axis=1)
    granted = test[test["decision_2"] == "grant"]
    refused = test[test["decision_2"] == "refuse"]
    report = {
        "recommendations": rec,
        "train_median_units_of_conversions": float(med_units),
        "n_test_pairs": int(len(test)),
        "agreement": {
            "R1": {"grant_pairs": round(float(granted["rec1_match"].mean()), 3),
                   "refuse_pairs": round(float(refused["rec1_match"].mean()), 3)},
            "R2": {"grant_pairs": round(float(granted["rec2_match"].mean()), 3),
                   "refuse_pairs": round(float(refused["rec2_match"].mean()), 3)},
            "R3": {"grant_pairs": round(float(granted["rec3_match"].mean()), 3),
                   "refuse_pairs": round(float(refused["rec3_match"].mean()), 3)},
            "R4": {"grant_pairs": round(float(granted["rec4_match"].mean()), 3),
                   "refuse_pairs": round(float(refused["rec4_match"].mean()), 3)},
        },
        "grant_rate_by_n_matched": {
            str(k): {"n": int(len(sub)), "grant_rate": round(float((sub["decision_2"] == "grant").mean()), 3)}
            for k, sub in test.groupby("n_rec_matched")
        },
    }
    (OUT / "rescue_plan_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
