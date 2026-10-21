"""Runner: token-overlap classifier for the overlap=2 PPR review band.

Positives: the auto-confirmed register-address matches (overlap >= 3).
Negatives: audit-rejected candidates with token overlap computed from their
addresses vs the scheme's register address. Train a GBM, score the 100k
overlap=2 band, auto-confirm the high-confidence slice.
"""
from __future__ import annotations

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
from devrisk.entity_resolution.ppr_matching import STOPWORDS  # noqa: E402
from devrisk.entity_resolution.scoring import uncommon_place_tokens  # noqa: E402

RNG = 7
COUNTY_WORDS = {
    "carlow", "cavan", "clare", "cork", "donegal", "dublin", "galway", "kerry",
    "kildare", "kilkenny", "laois", "leitrim", "limerick", "longford", "louth",
    "mayo", "meath", "monaghan", "offaly", "roscommon", "sligo", "tipperary",
    "waterford", "westmeath", "wexford", "wicklow",
}


def tokens(text: str) -> set[str]:
    return uncommon_place_tokens(str(text or ""), STOPWORDS) - COUNTY_WORDS


if __name__ == "__main__":
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    scheme_addr = dict(zip(cohort["case_key"].astype(str), cohort["DevelopmentAddress"].fillna("").astype(str)))

    # Positives: auto-confirmed overlap>=3 rows.
    auto = pd.read_csv(settings.SILVER_DIR / "scheme_sales_register_name_auto.csv")
    positives = auto[auto["token_overlap"] >= 3].copy()
    print("positives:", len(positives), flush=True)

    # Negatives: audit-rejected candidates; compute token overlap vs scheme address.
    negatives = []
    for path in ("ppr_townland_candidates_sample_COMPLETED.xlsx", "ppr_review_batch_2_COMPLETED.xlsx", "ppr_review_batch_3_COMPLETED.xlsx"):
        p = settings.SILVER_DIR / "audit_packs" / "returned" / path
        if not p.exists():
            continue
        frame = pd.read_excel(p)
        rejected = frame[frame["verdict"].fillna("").astype(str).str.strip().str.lower() == "rejected"]
        for _, row in rejected.iterrows():
            scheme_tokens = tokens(scheme_addr.get(str(row["scheme_id"]), ""))
            ppr_tokens = tokens(str(row.get("ppr_address") or ""))
            overlap = len(scheme_tokens & ppr_tokens)
            negatives.append({
                "token_overlap": overlap,
                "not_full_market_price": float(row.get("not_full_market_price") or 0),
                "label": 0,
            })
    negatives = pd.DataFrame(negatives)
    print("negatives:", len(negatives), "| negative overlap distribution:", negatives["token_overlap"].value_counts().to_dict(), flush=True)

    train = pd.concat([
        positives[["token_overlap", "not_full_market_price"]].assign(label=1),
        negatives[["token_overlap", "not_full_market_price"]].assign(label=0),
    ], ignore_index=True)
    X = train[["token_overlap", "not_full_market_price"]].to_numpy()
    y = train["label"].to_numpy()
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=RNG)
    aucs = []
    for tr_idx, va_idx in skf.split(X, y):
        model = GradientBoostingClassifier(n_estimators=150, max_depth=3, learning_rate=0.05, random_state=RNG)
        model.fit(X[tr_idx], y[tr_idx])
        aucs.append(roc_auc_score(y[va_idx], model.predict_proba(X[va_idx])[:, 1]))
    print(f"token-overlap classifier CV AUC: {np.mean(aucs):.3f}", flush=True)

    # Apply to the overlap=2 band.
    review = pd.read_csv(settings.SILVER_DIR / "audit" / "ppr_register_name_review.csv")
    X_review = review[["token_overlap", "not_full_market_price"]].fillna(0).to_numpy()
    model = GradientBoostingClassifier(n_estimators=150, max_depth=3, learning_rate=0.05, random_state=RNG)
    model.fit(X, y)
    review["p_link"] = model.predict_proba(X_review)[:, 1]
    review.to_csv(settings.SILVER_DIR / "ppr_overlap2_scored.csv", index=False)
    for threshold in (0.9, 0.7, 0.5):
        high = review[review["p_link"] >= threshold]
        print(f"overlap=2 p>={threshold}: {len(high)} rows, {high['scheme_id'].nunique()} schemes", flush=True)
