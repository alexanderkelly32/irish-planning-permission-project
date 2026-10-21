#!/usr/bin/env python3
"""Are type-coded SHD descriptions actually mishandled? Direct diagnostic."""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))

from build_8020_regime_experiment import build_data  # noqa: E402
from build_description_lexicon import type_code_features  # noqa: E402

ARTIFACT = ROOT / "05_policy" / "current" / "model_v4" / "national_residential_v4_full.joblib"


def main() -> None:
    data, train, test, y = build_data()
    tparse = type_code_features(test["description_stripped"].fillna(""))
    test = test.join(tparse)
    artifact = joblib.load(ARTIFACT)
    ranking = artifact["ranking_model"]
    ge10 = test[test["units"] >= 10].copy()
    ge10["risk"] = ranking.predict_proba(ge10[artifact["feature_columns"]])[:, 1]
    ge10["quintile"] = pd.qcut(ge10["risk"], 5, labels=False)
    ge10["refused"] = ge10["target_refused"].astype(int)

    typed = ge10[ge10["tparse_has_type_codes"] == 1]
    untyped = ge10[ge10["tparse_has_type_codes"] == 0]
    report = {
        "type_coded_ge10": {
            "n": int(len(typed)),
            "refusal_rate": round(float(typed["target_refused"].mean()), 4) if len(typed) else None,
            "mean_risk": round(float(typed["risk"].mean()), 4) if len(typed) else None,
            "share_in_top_two_quintiles": round(float((typed["quintile"] >= 3).mean()), 4) if len(typed) else None,
        },
        "untyped_ge10": {
            "n": int(len(untyped)),
            "refusal_rate": round(float(untyped["target_refused"].mean()), 4),
            "mean_risk": round(float(untyped["risk"].mean()), 4),
            "share_in_top_two_quintiles": round(float((untyped["quintile"] >= 3).mean()), 4),
        },
    }
    typed_refusals = typed[typed["refused"] == 1]
    report["type_coded_refusals_caught"] = {
        "n_refusals": int(len(typed_refusals)),
        "share_in_top_two_quintiles": round(float((typed_refusals["quintile"] >= 3).mean()), 4) if len(typed_refusals) else None,
    }
    if len(typed) >= 10 and typed["target_refused"].nunique() == 2:
        report["type_coded_auc"] = round(float(roc_auc_score(typed["target_refused"], typed["risk"])), 4)
    examples = typed[typed["refused"] == 1].head(4)
    report["type_coded_refusal_examples"] = [
        {"key": str(r["case_key"]), "risk": round(float(r["risk"]), 3), "description": str(r["description_stripped"])[:200]}
        for _, r in examples.iterrows()
    ]
    (OUT / "typecode_diagnostic.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
