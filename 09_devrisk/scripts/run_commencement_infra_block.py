"""Runner: commencement + construction tracks - infrastructure features
and block-level completion representation.

1. Commencement production model + infrastructure readiness features
   (FSC/DAC pre-grant) vs current best (devstate v2 + pipeline).
2. Block-level completion model (commencement -> block first CCC from
   ccc_blocks) vs scheme-level completion target.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingRegressor  # noqa: E402

from devrisk import settings  # noqa: E402

RNG = 7


if __name__ == "__main__":
    report: dict = {}
    infra = pd.read_csv(settings.SILVER_DIR / "infrastructure_readiness_features.csv")
    infra = infra.drop_duplicates("case_key")

    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = register[["case_key", "GrantDate", "NumResidentialUnits", "DevelopmentDescription", "AreaofSite"]].drop_duplicates("case_key")
    constraints = pd.read_csv(settings.SILVER_DIR / "timing_constraint_features.csv")
    applicants = pd.read_csv(settings.SILVER_DIR / "applicant_track_record_features.csv")
    devstate_v2 = pd.read_csv(settings.SILVER_DIR / "developer_state_v2_features.csv")
    pipeline = pd.read_csv(settings.SILVER_DIR / "pipeline_state_features.csv")

    comm = labels.merge(reg, on="case_key", how="inner")
    comm = comm.merge(constraints, on="case_key", how="left").merge(applicants, on="case_key", how="left")
    comm = comm.merge(devstate_v2, on="case_key", how="left").merge(pipeline, on="case_key", how="left")
    comm = comm.merge(infra, on="case_key", how="left")
    comm["grant_dt"] = pd.to_datetime(comm["GrantDate"], utc=True, errors="coerce")
    comm["activation"] = pd.to_numeric(comm["activation_days"], errors="coerce").clip(lower=0)
    comm = comm[comm["activation_linked"].astype(str).str.lower() == "true"].dropna(subset=["activation", "grant_dt"])
    comm["grant_year"] = comm["grant_dt"].dt.year
    u = pd.to_numeric(comm["NumResidentialUnits"], errors="coerce")
    comm["log_units"] = np.log1p(u.fillna(0))
    comm["type_apartment"] = comm["DevelopmentDescription"].fillna("").str.contains("apartment|duplex", case=False, regex=True).astype(int)
    comm_train = comm[comm["grant_dt"] < pd.Timestamp("2022-01-01", tz="UTC")]
    comm_test = comm[comm["grant_dt"] >= pd.Timestamp("2022-01-01", tz="UTC")]

    BASE = ["log_units", "type_apartment", "grant_year", "prior_auth_activation_rate",
            "applicant_prior_median_activation", "has_applicant"]
    DEV = [c for c in comm.columns if c.startswith("dev_") and c not in BASE]
    PIPE = [c for c in comm.columns if c.endswith("_progression_ratio") or c.endswith("_granted_not_commenced_units")]
    INFRA = ["fsc_count_total", "fsc_pre_grant", "fsc_first_submit_days_from_grant",
             "fsc_first_grant_days_from_grant", "dac_count_total"]

    def run(feats):
        model = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=250, max_depth=3,
                                          learning_rate=0.05, min_samples_leaf=15, random_state=RNG)
        model.fit(comm_train[feats].fillna(0.0), comm_train["activation"])
        pred = np.maximum(model.predict(comm_test[feats].fillna(0.0)), 1.0)
        y = comm_test["activation"].to_numpy()
        return {"mae": round(float(np.mean(np.abs(y - pred))), 0),
                "pm180": round(float(np.mean(np.abs(y - pred) <= 180)), 3),
                "pm365": round(float(np.mean(np.abs(y - pred) <= 365)), 3),
                "n": int(len(y))}

    report["commencement"] = {
        "base": run(BASE),
        "base_plus_devstate": run(BASE + DEV),
        "base_plus_devstate_pipeline": run(BASE + DEV + PIPE),
        "base_plus_devstate_pipeline_infra": run(BASE + DEV + PIPE + [c for c in INFRA if c in comm.columns]),
    }

    # ---- Block-level completion vs scheme-level ----
    blocks = pd.read_csv(settings.SILVER_DIR / "ccc_blocks.csv")
    labels_pool = labels[["case_key", "activation_days", "activation_linked"]]
    block_comm = blocks.merge(labels_pool, left_on="scheme_id", right_on="case_key", how="inner")
    block_comm = block_comm[block_comm["activation_linked"].astype(str).str.lower() == "true"]
    block_comm["commencement_dt"] = None
    # commencement date for the block's scheme from bcms
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    links = pd.read_csv(settings.SILVER_DIR / "bcms_links_all_granted.csv")
    overlay = settings.SILVER_DIR / "audit" / "bcms_verdict_overlay.csv"
    if overlay.exists():
        links = pd.concat([links, pd.read_csv(overlay).reindex(columns=links.columns)], ignore_index=True)
    confirmed = links[links["confidence_band"] == "confirmed"]
    first_comm = confirmed.merge(bcms[["bcms_event_id", "commencement_date_dt"]], on="bcms_event_id", how="inner") \
        .dropna(subset=["commencement_date_dt"]).groupby("scheme_id")["commencement_date_dt"].min()
    block_comm["commencement_dt"] = block_comm["scheme_id"].astype(str).map(first_comm)
    block_comm["commencement_dt"] = pd.to_datetime(block_comm["commencement_dt"], utc=True, errors="coerce")
    block_comm["first_ccc_dt"] = pd.to_datetime(block_comm["first_ccc"], utc=True, errors="coerce")
    block_comm["comm_to_ccc"] = (block_comm["first_ccc_dt"] - block_comm["commencement_dt"]).dt.days
    block_comm = block_comm[block_comm["comm_to_ccc"].between(0, 3000)]
    report["block_completion"] = {
        "n_blocks": int(len(block_comm)),
        "median_days": round(float(block_comm["comm_to_ccc"].median()), 0),
        "iqr_days": round(float(np.percentile(block_comm["comm_to_ccc"], 75) - np.percentile(block_comm["comm_to_ccc"], 25)), 0),
        "vs_scheme_level_median_403d": None,
    }

    out = settings.SILVER_DIR / "commencement_infra_block_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
