"""Conditions predictor: provisional shadow freeze (not production output).

Pre-commencement-condition model (logistic, train grant<2022) frozen into
the shadow log for all corpus schemes as of 2026-10-01. Promotion only
after another temporal/rolling-origin validation confirms AUC ~0.71.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402
from devrisk.shadow import log_prediction  # noqa: E402

SILVER = settings.SILVER_DIR
SNAP = "2026-10-01T00:00:00+00:00"
TEXT_INDICATORS = ["demolition", "protected structure", "brownfield", "infill",
                   "creche", "retail", "extension", "change of use", "apartment"]


def main() -> None:
    corpus = pd.read_csv(SILVER / "conditions" / "condition_corpus.csv").drop_duplicates("case_key")
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                               columns=["case_key", "DevelopmentDescription", "NumResidentialUnits"])
    register = register.drop_duplicates("case_key")
    base = corpus.merge(register, on="case_key", how="left")
    base["units"] = pd.to_numeric(base["NumResidentialUnits"], errors="coerce").fillna(1)
    base["log_units"] = np.log1p(base["units"])
    desc = base["DevelopmentDescription"].fillna("").str.lower()
    for ind in TEXT_INDICATORS:
        base[f"desc_{ind.replace(' ', '_')}"] = desc.str.contains(ind, regex=False).astype(int)
    base["desc_len"] = desc.str.len()
    base["type_apartment"] = desc.str.contains("apartment|duplex", regex=True).astype(int)
    base["y"] = (base["n_precommencement"] > 0).astype(int)
    auth_dummies = pd.get_dummies(base["authority"], prefix="auth").astype(int)
    feats = ["log_units", "type_apartment", "desc_len"] + \
            [f"desc_{i.replace(' ', '_')}" for i in TEXT_INDICATORS]
    train = base[base["grant_year"] < 2022]
    model = LogisticRegression(max_iter=3000, C=0.5)
    X_tr = pd.concat([train[feats].fillna(0.0), auth_dummies.loc[train.index]], axis=1)
    model.fit(X_tr, train["y"])

    X_all = pd.concat([base[feats].fillna(0.0), auth_dummies.loc[base.index]], axis=1)
    X_all = X_all.reindex(columns=X_tr.columns).fillna(0.0).astype(float)
    probs = model.predict_proba(X_all)[:, 1]
    seeded = 0
    for (_, r), p in zip(base.iterrows(), probs):
        try:
            log_prediction(case_key=r["case_key"], model_version="conditions_precomm_v0",
                           state_at_prediction="pre_submission",
                           target_transition="any_precommencement_condition",
                           prediction={"probability_pct": round(float(p) * 100, 1),
                                       "provisional": True,
                                       "basis": "logistic, train grant<2022, test AUC 0.714 (single split)"},
                           features_snapshot={"authority": r["authority"], "units": r["units"],
                                              "grant_year": int(r["grant_year"])},
                           source="conditions_provisional", timestamp=SNAP)
            seeded += 1
        except ValueError:
            continue
    print("seeded conditions shadow predictions:", seeded)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
