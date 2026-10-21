"""Condition-model predictions for the customer report (section 6).

Pre-commencement + financial condition probabilities from the
rolling-origin-validated model (AUC 0.71-0.77 / 0.63-0.69), with the
accuracy range and national prevalence CI stated inline. Corpus covers
2020+ granted schemes; for earlier schemes the prediction carries an
era caveat.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from devrisk import settings  # noqa: E402

TEXT_INDICATORS = ["demolition", "protected structure", "brownfield", "infill",
                   "creche", "retail", "extension", "change of use", "apartment"]


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * np.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return max(centre - margin, 0.0), min(centre + margin, 1.0)


def _fit_features(base: pd.DataFrame):
    desc = base["DevelopmentDescription"].fillna("").str.lower()
    feats = pd.DataFrame({"log_units": np.log1p(pd.to_numeric(base["units"], errors="coerce").fillna(1)),
                          "type_apartment": desc.str.contains("apartment|duplex", regex=True).astype(int),
                          "desc_len": desc.str.len()})
    for ind in TEXT_INDICATORS:
        feats[f"desc_{ind.replace(' ', '_')}"] = desc.str.contains(ind, regex=False).astype(int)
    auth = pd.get_dummies(base["authority"], prefix="a").astype(int)
    return pd.concat([feats, auth], axis=1)


def condition_predictions(development_description: str, units, authority: str, grant_year: int) -> dict:
    corpus = pd.read_csv(settings.SILVER_DIR / "conditions" / "condition_corpus.csv").drop_duplicates("case_key")
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "DevelopmentDescription"]).drop_duplicates("case_key")
    corpus = corpus.merge(reg, on="case_key", how="left")
    corpus["y_pre"] = (corpus["n_precommencement"] > 0).astype(int)
    corpus["y_fin"] = (corpus["n_financial"] > 0).astype(int)
    X = _fit_features(corpus)
    row = pd.DataFrame([{"DevelopmentDescription": development_description or "",
                         "units": units if units else 1, "authority": authority}])
    X_row = _fit_features(row).reindex(columns=X.columns).fillna(0.0)
    out = {
        "model": "pre-commencement + financial condition predictors",
        "accuracy": "rolling-origin AUC 0.714/0.765/0.747 (pre-commencement); 0.633-0.688 (financial)",
        "n_corpus": int(len(corpus)),
        "corpus_window": "2020+ granted schemes",
    }
    k_pre, n = int(corpus["y_pre"].sum()), len(corpus)
    lo, hi = wilson(k_pre, n)
    out["national_prevalence_precommencement"] = {"rate": round(k_pre / n, 3), "ci": [round(lo, 3), round(hi, 3)]}
    k_fin = int(corpus["y_fin"].sum())
    lo2, hi2 = wilson(k_fin, n)
    out["national_prevalence_financial"] = {"rate": round(k_fin / n, 3), "ci": [round(lo2, 3), round(hi2, 3)]}
    for target, key in [("y_pre", "p_precommencement"), ("y_fin", "p_financial")]:
        m = LogisticRegression(max_iter=3000, C=0.5)
        m.fit(X, corpus[target])
        out[key] = round(float(m.predict_proba(X_row)[:, 1][0]), 3)
    out["era_caveat"] = (f"scheme granted {grant_year}; the condition corpus covers 2020+ - "
                         f"prediction carries an era caveat") if grant_year < 2020 else None
    return out
