"""Runner: re-test the sale-affected historical ablations on CORRECTED labels.

Experiments whose conclusions were learned against the contaminated sale
target get exactly one re-test: market context, developer family,
decomposition, gating, lineage/pipeline/devstate/team families, and the
full ladder. Same protocols as before, corrected labels only.
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
from sklearn.linear_model import ElasticNet  # noqa: E402

from devrisk import settings  # noqa: E402
from run_dev_sale_ladder import build_cohort  # noqa: E402

RNG = 7


if __name__ == "__main__":
    sale = build_cohort()
    sale = sale[sale["sales_eligible"].fillna(True)]
    for name in ("site_lineage_features", "pipeline_state_features", "developer_state_v2_features", "consultant_team_features", "local_absorption_features"):
        path = settings.SILVER_DIR / f"{name}.csv"
        if path.exists():
            sale = sale.merge(pd.read_csv(path), on="case_key", how="left")
    sale_train = sale[sale["grant_year"] < 2021]
    sale_test = sale[sale["grant_year"] >= 2021]
    y_tr = sale_train["sale_days"].to_numpy(dtype=float)
    y_te = sale_test["sale_days"].to_numpy(dtype=float)
    finite = np.isfinite(y_tr) & (y_tr > -1)

    SALE_BASE = ["log_units", "type_apartment", "type_house", "grant_year", "grant_month",
                 "applicant_prior_median_tfs", "has_applicant"]

    def run(feats):
        model = ElasticNet(alpha=0.5, max_iter=5000)
        model.fit(sale_train[feats].fillna(0.0).to_numpy()[finite], np.log1p(y_tr[finite]))
        pred = np.expm1(model.predict(sale_test[feats].fillna(0.0).to_numpy()))
        mask = np.isfinite(y_te)
        return round(float(np.mean(np.abs(y_te[mask] - pred[mask]))), 0)

    market = ["price_level", "volume_12m", "momentum"]
    dev = ["applicant_prior_n", "applicant_prior_grant_rate"]
    lineage_cols = [c for c in sale.columns if c in ("prior_refusals_same_parcel", "n_prior_same_parcel", "prior_grants_same_parcel")]
    pipeline_cols = [c for c in sale.columns if c.endswith("_progression_ratio") or c.endswith("_granted_not_commenced_units")]
    devstate_cols = [c for c in sale.columns if c.startswith("dev_")]
    team_cols = [c for c in sale.columns if c.startswith("consultant_")]
    absorption_cols = [c for c in sale.columns if c.endswith("_competing_newbuild_units") or c.endswith("_ccc_flow_12m") or c.endswith("_sales_12m")]

    report = {
        "base": run(SALE_BASE),
        "plus_market": run(SALE_BASE + market),
        "plus_developer": run(SALE_BASE + dev),
        "plus_lineage": run(SALE_BASE + lineage_cols),
        "plus_pipeline": run(SALE_BASE + pipeline_cols),
        "plus_devstate": run(SALE_BASE + devstate_cols),
        "plus_team": run(SALE_BASE + team_cols),
        "plus_absorption": run(SALE_BASE + absorption_cols),
    }

    # Decomposition (commencement->CCC->sale) on corrected labels.
    comm = sale.dropna(subset=["activation_days", "t_first_ccc", "sale_days"]) if "activation_days" in sale.columns else pd.DataFrame()
    if "t_first_ccc" not in sale.columns:
        completion = pd.read_csv(settings.SILVER_DIR / "completion_targets.csv")
        sale = sale.merge(completion[["scheme_id", "t_first_ccc"]], left_on="case_key", right_on="scheme_id", how="left").drop(columns=["scheme_id"])
        labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
        sale = sale.merge(labels[["case_key", "activation_days"]], on="case_key", how="left")
    decomp = sale[sale["grant_year"] >= 2021].dropna(subset=["activation_days", "t_first_ccc", "sale_days"])
    if len(decomp) >= 10:
        ccc_to_sale = (decomp["sale_days"] - decomp["activation_days"] - decomp["t_first_ccc"]).clip(lower=0)
        report["decomposed_ccc_to_sale_median"] = round(float(ccc_to_sale.median()), 0)
        report["decomposed_n"] = int(len(decomp))

    out = settings.SILVER_DIR / "sale_relabeled_retests.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
