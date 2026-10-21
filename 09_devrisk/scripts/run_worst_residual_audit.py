"""Runner: worst-residual audit packs (sale + commencement top-50 errors).

Trains the production models on corrected labels, computes per-scheme
absolute errors, exports the top 50 for each target with classification
columns (bad_label / bad_join / unusual_project / censored / wrong_entity
/ wrong_phase) for manual review.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingRegressor  # noqa: E402
from sklearn.linear_model import ElasticNet  # noqa: E402

from devrisk import settings  # noqa: E402
from run_dev_sale_ladder import build_cohort  # noqa: E402

RNG = 7


if __name__ == "__main__":
    # ---- Sale residuals ----
    sale = build_cohort()
    sale = sale[sale["sales_eligible"].fillna(True)]
    sale_train = sale[sale["grant_year"] < 2022]
    sale_test = sale[sale["grant_year"] >= 2022]
    SALE_FEATS = ["log_units", "type_apartment", "type_house", "grant_year", "grant_month",
                  "price_level", "volume_12m", "momentum", "applicant_prior_median_tfs", "has_applicant"]
    sale_feats = [c for c in SALE_FEATS if c in sale.columns]
    enet = ElasticNet(alpha=0.5, max_iter=5000)
    y_tr = sale_train["sale_days"].to_numpy(dtype=float)
    finite = np.isfinite(y_tr) & (y_tr > -1)
    enet.fit(sale_train[sale_feats].fillna(0.0).to_numpy()[finite], np.log1p(y_tr[finite]))
    p_sale = np.expm1(enet.predict(sale_test[sale_feats].fillna(0.0)))
    y_sale = sale_test["sale_days"].to_numpy(dtype=float)
    sale_test = sale_test.copy()
    sale_test["predicted"] = p_sale
    sale_test["abs_error"] = np.abs(y_sale - p_sale)
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    addr = dict(zip(register["case_key"].astype(str), register["DevelopmentAddress"].fillna("")))
    desc = dict(zip(register["case_key"].astype(str), register["DevelopmentDescription"].fillna("")))
    sale_top = sale_test.nlargest(50, "abs_error")
    sale_pack = pd.DataFrame({
        "case_key": sale_top["case_key"].astype(str),
        "address": sale_top["case_key"].astype(str).map(addr).str.slice(0, 90),
        "description": sale_top["case_key"].astype(str).map(desc).str.slice(0, 100),
        "grant_year": sale_top["grant_year"],
        "actual_days": y_sale[np.argsort(-sale_test["abs_error"].to_numpy())[:50]],
        "predicted_days": sale_top["predicted"].round(0),
        "abs_error_days": sale_top["abs_error"].round(0),
        "classification": "",
        "note": "",
    })

    # ---- Commencement residuals ----
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    constraints = pd.read_csv(settings.SILVER_DIR / "timing_constraint_features.csv")
    applicants = pd.read_csv(settings.SILVER_DIR / "applicant_track_record_features.csv")
    devstate_v2 = pd.read_csv(settings.SILVER_DIR / "developer_state_v2_features.csv")
    pipeline = pd.read_csv(settings.SILVER_DIR / "pipeline_state_features.csv")
    comm = labels.merge(register[["case_key", "GrantDate", "NumResidentialUnits", "DevelopmentDescription", "AreaofSite"]].drop_duplicates("case_key"), on="case_key", how="inner")
    comm = comm.merge(constraints, on="case_key", how="left").merge(applicants, on="case_key", how="left")
    comm = comm.merge(devstate_v2, on="case_key", how="left").merge(pipeline, on="case_key", how="left")
    comm["grant_dt"] = pd.to_datetime(comm["GrantDate"], utc=True, errors="coerce")
    comm["activation"] = pd.to_numeric(comm["activation_days"], errors="coerce").clip(lower=0)
    comm = comm[comm["activation_linked"].astype(str).str.lower() == "true"].dropna(subset=["activation", "grant_dt"])
    comm["grant_year"] = comm["grant_dt"].dt.year
    u = pd.to_numeric(comm["NumResidentialUnits"], errors="coerce")
    comm["log_units"] = np.log1p(u.fillna(0))
    comm["type_apartment"] = comm["DevelopmentDescription"].fillna("").str.contains("apartment|duplex", case=False, regex=True).astype(int)
    comm_train = comm[comm["grant_dt"] < pd.Timestamp("2022-01-01", tz="UTC")]
    comm_test = comm[comm["grant_dt"] >= pd.Timestamp("2022-01-01", tz="UTC")]
    COMM_FEATS = ["log_units", "type_apartment", "grant_year", "prior_auth_activation_rate",
                  "applicant_prior_median_activation", "has_applicant",
                  "dev_live_unit_load", "dev_units_completed_24m", "dev_recency_weighted_activation",
                  "dev_x_authority_median_activation", "dev_x_county_median_activation",
                  "3km_progression_ratio", "5km_progression_ratio"]
    comm_feats = [c for c in COMM_FEATS if c in comm.columns]
    model = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=250, max_depth=3,
                                      learning_rate=0.05, min_samples_leaf=15, random_state=RNG)
    model.fit(comm_train[comm_feats].fillna(0.0), comm_train["activation"])
    p_comm = np.maximum(model.predict(comm_test[comm_feats].fillna(0.0)), 1.0)
    y_comm = comm_test["activation"].to_numpy()
    comm_test = comm_test.copy()
    comm_test["predicted"] = p_comm
    comm_test["abs_error"] = np.abs(y_comm - p_comm)
    comm_top = comm_test.nlargest(50, "abs_error")
    comm_pack = pd.DataFrame({
        "case_key": comm_top["case_key"].astype(str),
        "address": comm_top["case_key"].astype(str).map(addr).str.slice(0, 90),
        "description": comm_top["case_key"].astype(str).map(desc).str.slice(0, 100),
        "grant_year": comm_top["grant_year"],
        "actual_days": y_comm[np.argsort(-comm_test["abs_error"].to_numpy())[:50]],
        "predicted_days": comm_top["predicted"].round(0),
        "abs_error_days": comm_top["abs_error"].round(0),
        "classification": "",
        "note": "",
    })

    # ---- Pack ----
    pack_dir = settings.SILVER_DIR / "audit_packs"
    zip_path = pack_dir / "PACK_23_worst_residuals.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, frame in (("sale_top50_errors.csv", sale_pack), ("commencement_top50_errors.csv", comm_pack)):
            csv_path = settings.SILVER_DIR / "audit" / name
            frame.to_csv(csv_path, index=False)
            archive.write(csv_path, arcname=name)
        archive.writestr("INSTRUCTIONS.txt", (
            "PACK 23: worst-residual audit (corrected labels).\n"
            "Top-50 absolute errors for sale and commencement.\n"
            "classification per row:\n"
            "  bad_label / bad_join / unusual_project / censored /\n"
            "  wrong_entity / wrong_phase\n"
            "RETURN: into the 'returned' folder.\n"
        ))
    print(f"PACK_23 -> {zip_path} (sale {len(sale_pack)}, commencement {len(comm_pack)})")
