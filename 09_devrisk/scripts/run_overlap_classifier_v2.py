"""Runner: overlap classifier v2 - retrain with PACK_15 negatives folded in.

PACK_15 rejected 153 road-level candidates; recompute their token overlap vs
the scheme register address and add them to the negative pool, retrain the
GBM, re-score the overlap=2 review band, and report CV AUC + band sizes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingClassifier  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402
from sklearn.model_selection import StratifiedKFold  # noqa: E402

from devrisk import settings  # noqa: E402
from run_overlap2_classifier import tokens  # noqa: E402

RNG = 7

if __name__ == "__main__":
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    scheme_addr = dict(zip(cohort["case_key"].astype(str), cohort["DevelopmentAddress"].fillna("").astype(str)))

    positives = pd.read_csv(settings.SILVER_DIR / "scheme_sales_register_name_auto.csv")
    positives = positives[positives["token_overlap"] >= 3].copy()
    positive_rows = positives[["token_overlap", "not_full_market_price"]].assign(label=1)

    negative_rows = []
    for path in ("ppr_townland_candidates_sample_COMPLETED.xlsx", "ppr_review_batch_2_COMPLETED.xlsx", "ppr_review_batch_3_COMPLETED.xlsx"):
        p = settings.SILVER_DIR / "audit_packs" / "returned" / path
        if not p.exists():
            continue
        frame = pd.read_excel(p)
        rejected = frame[frame["verdict"].fillna("").astype(str).str.strip().str.lower() == "rejected"]
        for _, row in rejected.iterrows():
            scheme_tokens = tokens(scheme_addr.get(str(row["scheme_id"]), ""))
            ppr_tokens = tokens(str(row.get("ppr_address") or ""))
            negative_rows.append({
                "token_overlap": len(scheme_tokens & ppr_tokens),
                "not_full_market_price": float(row.get("not_full_market_price") or 0),
                "label": 0,
            })

    pack15 = pd.read_csv(settings.SILVER_DIR / "audit" / "ppr_negatives_accumulated.csv")
    for _, row in pack15.iterrows():
        scheme_tokens = tokens(scheme_addr.get(str(row["scheme_id"]), ""))
        ppr_tokens = tokens(str(row.get("ppr_candidate_address") or ""))
        negative_rows.append({
            "token_overlap": len(scheme_tokens & ppr_tokens),
            "not_full_market_price": 0,
            "label": 0,
        })
    negatives = pd.DataFrame(negative_rows)

    train = pd.concat([positive_rows, negatives], ignore_index=True)
    X = train[["token_overlap", "not_full_market_price"]].to_numpy()
    y = train["label"].to_numpy()
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=RNG)
    aucs = []
    for tr_idx, va_idx in skf.split(X, y):
        model = GradientBoostingClassifier(n_estimators=150, max_depth=3, learning_rate=0.05, random_state=RNG)
        model.fit(X[tr_idx], y[tr_idx])
        aucs.append(roc_auc_score(y[va_idx], model.predict_proba(X[va_idx])[:, 1]))

    report = {
        "positives": int(len(positive_rows)),
        "negatives_total": int(len(negatives)),
        "negatives_from_pack15": int(len(pack15)),
        "cv_auc": round(float(np.mean(aucs)), 3),
    }

    review_path = settings.SILVER_DIR / "audit" / "ppr_register_name_review.csv"
    if review_path.exists():
        review = pd.read_csv(review_path)
        X_review = review[["token_overlap", "not_full_market_price"]].fillna(0).to_numpy()
        model = GradientBoostingClassifier(n_estimators=150, max_depth=3, learning_rate=0.05, random_state=RNG)
        model.fit(X, y)
        review["p_link"] = model.predict_proba(X_review)[:, 1]
        review.to_csv(settings.SILVER_DIR / "ppr_overlap2_scored.csv", index=False)
        report["band_sizes"] = {
            str(threshold): int((review["p_link"] >= threshold).sum()) for threshold in (0.9, 0.7, 0.5)
        }

    out = settings.SILVER_DIR / "overlap_classifier_v2.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
