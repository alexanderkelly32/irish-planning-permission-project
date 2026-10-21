"""Runner: AlphaEarth state model + timeline ablation (learned-sensor design).

1. State labels from BCMS/CCC: greenfield / site_works / active /
   substantially_built / completed / stalled, per site-year.
2. State classifier (GBM) on AE features; state-probability curves around
   commencement/CCC; satellite-detected commencement year (first sustained
   change) -> inferred labels for BCMS-unlinked schemes (flagged inferred).
3. Timeline ablation: commencement + sale models with/without AE features
   (state probabilities, months-since-satellite-commencement, change
   intensity, heterogeneity), OOS MAE / +-180 / +-365 / calibration.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

from devrisk import settings  # noqa: E402

RNG = np.random.default_rng(7)


def load_site_years() -> pd.DataFrame:
    frame = pd.read_csv(settings.RAW_DIR / "alphaearth" / "alphaearth_features.csv")
    frame = frame.drop_duplicates(subset=["development_id", "year"], keep="last")
    return frame


def assign_state(row: pd.Series, commencement_year, ccc_year) -> str:
    year = int(row["year"])
    change = float(row.get("change_median") or 0.0)
    frac = float(row.get("frac_pixels_large_change") or 0.0)
    ccc_isna = pd.isna(ccc_year)
    comm_isna = pd.isna(commencement_year)
    if not ccc_isna and year >= int(ccc_year):
        return "completed" if change < 0.05 else "stable_completed"
    if not comm_isna and year >= int(commencement_year):
        if change < 0.03 and frac < 0.05:
            return "stalled_after_works"
        if change > 0.1:
            return "active_construction"
        return "substantially_built"
    if not comm_isna and year == int(commencement_year) - 1 and (change > 0.1 or frac > 0.1):
        return "site_works"
    return "undeveloped_greenfield"


if __name__ == "__main__":
    site_years = load_site_years()
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = register[["case_key", "GrantDate", "NumResidentialUnits"]].drop_duplicates("case_key")
    completion = pd.read_csv(settings.SILVER_DIR / "completion_targets.csv")
    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv")

    base = labels.merge(reg, on="case_key", how="inner")
    base["grant_dt"] = pd.to_datetime(base["GrantDate"], utc=True, errors="coerce")
    base["grant_year"] = base["grant_dt"].dt.year
    base["activation"] = pd.to_numeric(base["activation_days"], errors="coerce").clip(lower=0)
    base["commencement_year"] = base["grant_year"] + (base["activation"] / 365.0).round().astype("Int64")
    base = base.merge(completion[["scheme_id", "t_first_ccc"]], left_on="case_key", right_on="scheme_id", how="left").drop(columns=["scheme_id"])
    base["ccc_year"] = base["commencement_year"] + (base["t_first_ccc"] / 365.0).round().astype("Int64")
    base = base.merge(exit_labels[["scheme_id", "sales_linked", "time_to_first_sale_from_grant_days"]].rename(columns={"scheme_id": "case_key"}),
                      on="case_key", how="left", suffixes=("", "_exit"))

    merged = base.merge(site_years, left_on=["case_key", "grant_year"], right_on=["development_id", "year"], how="inner")
    merged["state"] = merged.apply(
        lambda r: assign_state(r, r["commencement_year"], r["ccc_year"]), axis=1)

    # ---- State classifier ----
    FEATURES = [c for c in ("band_std_mean", "band_std_sum", "edge_mean_norm", "buffer_mean_norm",
                            "change_mean", "change_median", "change_p90", "heterogeneity",
                            "frac_pixels_large_change", "contrast", "site_mean_norm") if c in merged.columns]
    labelled = merged.dropna(subset=FEATURES).copy()
    classes = sorted(set(labelled["state"]))
    report = {"state_class_counts": labelled["state"].value_counts().to_dict()}

    train = labelled[labelled["grant_year"] < 2021]
    test = labelled[labelled["grant_year"] >= 2021]
    model = GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=7)
    model.fit(train[FEATURES].fillna(0.0), train["state"])
    pred = model.predict_proba(test[FEATURES].fillna(0.0))
    state_accuracy = float(np.mean(np.argmax(pred, axis=1) == test["state"].map({c: i for i, c in enumerate(classes)})))
    report["state_classifier"] = {"n_train": int(len(train)), "n_test": int(len(test)),
                                  "accuracy": round(state_accuracy, 3),
                                  "baseline_majority": round(float(test["state"].value_counts(normalize=True).iloc[0]), 3)}

    # State probability around commencement (does P(active/built) rise?)
    test_probs = pd.DataFrame(pred, columns=classes)
    test_probs["commencement_year"] = test["commencement_year"].to_numpy()
    test_probs["year"] = test["year"].to_numpy()
    test_probs["year_rel_commencement"] = test_probs["year"] - test_probs["commencement_year"]
    build_cols = [c for c in ("active_construction", "substantially_built") if c in classes]
    curve = test_probs.groupby("year_rel_commencement")[build_cols].mean() if build_cols else pd.DataFrame()
    report["state_probability_curve_around_commencement"] = {
        str(k): {c: round(float(v[c]), 3) for c in build_cols} for k, v in curve.iterrows()
    }

    # Satellite-detected commencement: first year with frac_pixels_large_change >= 0.1
    site_years_sorted = site_years.sort_values("year")
    first_change = site_years_sorted[site_years_sorted["frac_pixels_large_change"].fillna(0) >= 0.1] \
        .groupby("development_id")["year"].min().rename("sat_commencement_year")
    base = base.merge(first_change, left_on="case_key", right_index=True, how="left")
    base["sat_commencement_year"] = pd.to_numeric(base["sat_commencement_year"], errors="coerce")
    unlinked = base[base["activation_linked"].astype(str).str.lower() != "true"]
    inferred = unlinked[unlinked["sat_commencement_year"].notna()]
    report["inferred_commencement_labels"] = {
        "unlinked_schemes": int(len(unlinked)),
        "inferred_from_satellite": int(len(inferred)),
        "flagged_inferred_not_observed": True,
    }

    # ---- Timeline ablation ----
    ae_snapshot = site_years.groupby("development_id").agg(
        sat_change_median=("change_median", "median"),
        sat_heterogeneity=("heterogeneity", "median"),
        sat_frac_large=("frac_pixels_large_change", "max"),
    ).reset_index()
    base = base.merge(ae_snapshot, left_on="case_key", right_on="development_id", how="left")
    units = pd.to_numeric(base["NumResidentialUnits"], errors="coerce")
    base["log_units"] = np.log1p(units.fillna(0))

    comm = base[base["activation"].notna()].copy()
    comm_train = comm[comm["grant_year"] < 2021]
    comm_test = comm[comm["grant_year"] >= 2021]
    base_feats = ["log_units"]
    ae_feats = [c for c in ("sat_change_median", "sat_heterogeneity", "sat_frac_large") if c in base.columns]

    def run_ablation(train_part, test_part, target_col, feats):
        y_tr = train_part[target_col].to_numpy()
        y_te = test_part[target_col].to_numpy()
        model = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=200, max_depth=3,
                                          learning_rate=0.05, min_samples_leaf=10, random_state=7)
        model.fit(train_part[feats].fillna(0.0), y_tr)
        pred = np.maximum(model.predict(test_part[feats].fillna(0.0)), 1.0)
        mae = float(np.mean(np.abs(y_te - pred)))
        hits = {f"pm{d}": round(float(np.mean(np.abs(y_te - pred) <= d)), 3) for d in (180, 365)}
        return {"mae": round(mae, 0), **hits}

    report["ablation_commencement"] = {
        "base": run_ablation(comm_train, comm_test, "activation", base_feats),
        "base_plus_ae": run_ablation(comm_train, comm_test, "activation", base_feats + ae_feats),
    }
    sold = base[pd.to_numeric(base["sales_linked"], errors="coerce").gt(0)].dropna(subset=["time_to_first_sale_from_grant_days"])
    sold_train = sold[sold["grant_year"] < 2021]
    sold_test = sold[sold["grant_year"] >= 2021]
    report["ablation_sale"] = {
        "base": run_ablation(sold_train, sold_test, "time_to_first_sale_from_grant_days", base_feats),
        "base_plus_ae": run_ablation(sold_train, sold_test, "time_to_first_sale_from_grant_days", base_feats + ae_feats),
    }

    out = settings.SILVER_DIR / "alphaearth_state_ablation.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
