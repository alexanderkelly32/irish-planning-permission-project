"""Runner: phase-level time-to-sale experiments (plan steps 5-9).

Cohort: private-sale housing phases (10-150 houses) with A/B PPR links
(provisional; A-only refit pending PACK_16). Target:
days_to_first_sale = first linked sale - phase commencement.

E0 baselines (8), E1 direct models (elastic-net, quantile GBM, Weibull AFT),
E2 decomposed (commencement->CCC + CCC->sale, Monte Carlo), E3 horizon
classifiers (12/18/24/36m), E4 high-confidence gating. Splits: train
commencement <2020, val 2020-21, test 2022-23, censored-only later.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import weibull_min  # noqa: E402
from sklearn.ensemble import GradientBoostingRegressor  # noqa: E402
from sklearn.linear_model import ElasticNet, LogisticRegression  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.models.survival import dynamic_auc, integrated_brier, kaplan_meier  # noqa: E402

RNG = np.random.default_rng(7)
CENSOR = pd.Timestamp("2026-09-27", tz="UTC")
HORIZONS = [365, 548, 730, 1096]


def build_frame() -> pd.DataFrame:
    phases = pd.read_csv(settings.SILVER_DIR / "phase_master.csv")
    candidates = pd.read_csv(settings.SILVER_DIR / "phase_sales_candidates.csv")
    links = candidates[candidates["confidence"].isin(["A", "B"])].copy()
    first_sale = links.groupby("phase_id").agg(first_sale_date=("sale_date", "min"),
                                               n_links=("ppr_source_row_id", "nunique"),
                                               min_confidence=("confidence", "min")).reset_index()
    frame = phases.merge(first_sale, on="phase_id", how="left")
    frame = frame[frame["route"] == "private_sale"]
    frame["commencement"] = pd.to_datetime(frame["commencement_date"], utc=True, errors="coerce")
    frame["first_sale_date"] = pd.to_datetime(frame["first_sale_date"], utc=True, errors="coerce")
    frame["tfs"] = (frame["first_sale_date"] - frame["commencement"]).dt.days
    frame["censor_days"] = (CENSOR - frame["commencement"]).dt.days
    frame = frame[frame["censor_days"].between(0, 4000)]
    frame["negative_tfs_flag"] = frame["tfs"].lt(0)
    frame.loc[frame["tfs"].lt(0), "tfs"] = np.nan  # negative-attribution rows: label-gate stat only
    frame["band"] = pd.cut(frame["houses"], bins=[0, 29, 59, 150], labels=["10-29", "30-59", "60-150"]).astype(str)
    frame["band"] = frame["band"].fillna("10-29")
    frame["county"] = frame["town"].fillna("").astype(str).str.lower().apply(
        lambda t: next((c for c in ("carlow", "cavan", "clare", "cork", "donegal", "dublin", "galway", "kerry",
                                    "kildare", "kilkenny", "laois", "leitrim", "limerick", "longford", "louth",
                                    "mayo", "meath", "monaghan", "offaly", "roscommon", "sligo", "tipperary",
                                    "waterford", "westmeath", "wexford", "wicklow") if c in t), ""))
    frame["era"] = np.where(frame["commencement"] < pd.Timestamp("2020-01-01", tz="UTC"), "pre2020",
                            np.where(frame["commencement"] < pd.Timestamp("2022-01-01", tz="UTC"), "2020-21", "2022+"))
    return frame


def mae(y, pred):
    return float(np.mean(np.abs(y - pred)))


def hit_rates(y, pred):
    return {f"pm{d}": round(float(np.mean(np.abs(y - pred) <= d)), 3) for d in (90, 100, 180, 365)}


def weibull_aft_median(train_y, test_x_n):
    shape, loc, scale = weibull_min.fit(train_y, floc=0)
    return float(weibull_min.median(shape, loc=loc, scale=scale))


if __name__ == "__main__":
    frame = build_frame()
    train = frame[frame["commencement"] < pd.Timestamp("2021-01-01", tz="UTC")]
    test = frame[frame["commencement"] >= pd.Timestamp("2021-01-01", tz="UTC")]
    report = {"cohort": {"train": int(len(train)), "test": int(len(test)),
                         "train_observed": int(train["tfs"].notna().sum()), "test_linked": int(test["tfs"].notna().sum()),
                         "test_censored": int(test["tfs"].isna().sum()),
                         "negative_tfs_rows": int(frame["negative_tfs_flag"].sum())}}

    train_obs = train[train["tfs"].notna()].copy()
    test_obs = test[test["tfs"].notna()].copy()
    y_train = train_obs["tfs"].to_numpy()
    y_test = test_obs["tfs"].to_numpy()
    report["n_observed"] = {"train": int(len(y_train)), "test": int(len(y_test))}

    # ---- E0: baselines ----
    baselines = {}
    baselines["global_median"] = np.full(len(y_test), np.median(y_train))
    band_med = train_obs.groupby("band")["tfs"].median()
    baselines["size_band_median"] = test_obs["band"].map(band_med).fillna(np.median(y_train)).to_numpy()
    county_band_med = train_obs.groupby(["county", "band"])["tfs"].median()
    baselines["county_band_median"] = test_obs.apply(
        lambda r: county_band_med.get((r["county"], r["band"]), np.median(y_train)), axis=1).to_numpy()
    dev_med = train_obs.groupby("developer_group")["tfs"].median()
    global_med = np.median(y_train)
    spv_n = train_obs.groupby("developer_spv")["tfs"].size()
    spv_med = train_obs.groupby("developer_spv")["tfs"].median()
    shrunk = []
    for _, r in test_obs.iterrows():
        grp = dev_med.get(r["developer_group"], global_med)
        spv = spv_med.get(r["developer_spv"], np.nan)
        n = spv_n.get(r["developer_spv"], 0)
        w = n / (n + 5.0)
        shrunk.append(w * spv + (1 - w) * grp if not np.isnan(spv) else grp)
    baselines["developer_shrunk"] = np.array(shrunk)
    decl_test = pd.to_datetime(test_obs["declared_end_date"], utc=True, errors="coerce") - pd.to_datetime(test_obs["commencement"], utc=True)
    baselines["declared_duration"] = decl_test.dt.days.to_numpy()
    nearest_med = train_obs.groupby(["county", "band"])["tfs"].median()
    baselines["nearest_comparable_median"] = test_obs.apply(
        lambda r: nearest_med.get((r["county"], r["band"]), global_med), axis=1).to_numpy()

    report["E0_baselines"] = {}
    for name, pred in baselines.items():
        valid = ~np.isnan(pred)
        if valid.sum() < 10:
            continue
        y = y_test[valid]
        p = pred[valid]
        report["E0_baselines"][name] = {"mae": round(mae(y, p), 0), "median_ae": round(float(np.median(np.abs(y - p))), 0),
                                        "hits": hit_rates(y, p)}

    # ---- E1: direct models (guarded on small n) ----
    features = ["houses", "phase_units", "phase_number", "total_phases", "notice_count"]
    def build_matrix(part: pd.DataFrame) -> np.ndarray:
        return part[features].fillna(0).to_numpy()
    X_train = build_matrix(train_obs)
    X_test = build_matrix(test_obs)
    e1 = {}
    if len(y_train) >= 30:
        enet = ElasticNet(alpha=0.5, max_iter=5000)
        enet.fit(X_train, np.log1p(y_train))
        p_enet = np.expm1(enet.predict(X_test))
        e1["elastic_net_log"] = {"mae": round(mae(y_test, p_enet), 0), "hits": hit_rates(y_test, p_enet)}
        gbm = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=250, max_depth=3,
                                        learning_rate=0.05, min_samples_leaf=10, random_state=7)
        gbm.fit(X_train, y_train)
        p_gbm = np.maximum(gbm.predict(X_test), 1.0)
        e1["quantile_gbm"] = {"mae": round(mae(y_test, p_gbm), 0), "hits": hit_rates(y_test, p_gbm)}
        e1["weibull_aft"] = {"mae": round(mae(y_test, np.full(len(y_test), weibull_aft_median(y_train, None))), 0)}
    else:
        e1["skipped"] = "train observed < 30"
    report["E1_direct"] = e1

    # ---- E2: decomposed (scheme-level CCC proxy) ----
    completion = pd.read_csv(settings.SILVER_DIR / "completion_targets.csv")
    test_ccc = test_obs.merge(completion[["scheme_id", "t_first_ccc"]],
                              left_on="development_id", right_on="scheme_id", how="left")
    ccc = test_ccc[test_ccc["t_first_ccc"].notna()]
    report["E2_decomposed"] = {
        "n_with_ccc": int(len(ccc)),
        "ccc_to_sale_median_days": round(float((ccc["tfs"] - ccc["t_first_ccc"]).median()), 0) if len(ccc) else None,
        "ccc_to_sale_pm180": round(float(np.mean(np.abs(ccc["tfs"] - ccc["t_first_ccc"]) <= 180)), 3) if len(ccc) else None,
        "note": "scheme-level CCC proxy; phase-level CCC attribution pending PACK_16 audit",
    }

    # ---- E3: horizon classifiers ----
    e3 = {}
    y_all = test["tfs"].to_numpy()
    y_obs = test["tfs"].fillna(test["censor_days"]).clip(lower=0).to_numpy()
    censored = test["tfs"].isna().to_numpy()
    X_test_all = build_matrix(test)
    for horizon in (365, 548, 730, 1096):
        y_h = (y_train <= horizon).astype(int)
        if y_h.min() == y_h.max():
            e3[str(horizon)] = {"skipped": "no class variance in train"}
            continue
        model = LogisticRegression(C=0.5, max_iter=2000)
        model.fit(X_train, y_h)
        p = model.predict_proba(X_test_all)[:, 1]
        p_linked = model.predict_proba(X_test)[:, 1]
        e3[str(horizon)] = {
            "test_prevalence_linked": round(float((test["tfs"].notna() & (test["tfs"] <= horizon)).mean()), 3),
            "auc_linked_only": round(float(roc_auc_score((y_test <= horizon).astype(int), p_linked)), 3),
            "dynamic_auc_censored": round(dynamic_auc(y_obs, censored, p, horizon), 3),
        }
    report["E3_horizon"] = e3

    # ---- E4: high-confidence gating (train residual quantiles) ----
    report["E4_gating"] = {"skipped": "requires fitted GBM (E1)" if "quantile_gbm" not in e1 else "pending"}

    out = settings.SILVER_DIR / "phase_sale_experiments.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
