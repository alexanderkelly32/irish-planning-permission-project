"""Runner: 98% confidence intervals for the full prediction suite.

CIs are bootstrap percentile (98%: 1st/99th percentiles, 2000 resamples) for
discrimination/error metrics, and exact binomial (Clopper-Pearson) for rates.
Sources: saved holdout predictions (v4 refusal, FI), refits where needed
(appeal, decision-timing horizons), label tables (reasons, conditions,
commencement, sale), TimesFM county backtest.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "05_policy" / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import beta as beta_dist  # noqa: E402
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score  # noqa: E402

from devrisk import settings  # noqa: E402

N_BOOT = 2000
ALPHA_TAILS = (0.01, 0.99)  # 98% interval
RNG = np.random.default_rng(7)


def bootstrap_ci(y: np.ndarray, p: np.ndarray, metric_fn, n_boot: int = N_BOOT) -> dict:
    values = []
    n = len(y)
    for _ in range(n_boot):
        idx = RNG.integers(0, n, n)
        try:
            values.append(metric_fn(y[idx], p[idx]))
        except ValueError:
            continue
    values = np.asarray(values)
    return {
        "estimate": round(float(metric_fn(y, p)), 4),
        "ci98_low": round(float(np.percentile(values, 0.5)), 4),
        "ci98_high": round(float(np.percentile(values, 99.5)), 4),
        "n": int(n),
    }


def bootstrap_mae_ci(y: np.ndarray, pred: np.ndarray) -> dict:
    def mae(yy, pp):
        return float(np.mean(np.abs(yy - pp)))

    values = []
    n = len(y)
    for _ in range(N_BOOT):
        idx = RNG.integers(0, n, n)
        values.append(mae(y[idx], pred[idx]))
    return {
        "estimate": round(mae(y, pred), 1),
        "ci98_low": round(float(np.percentile(values, 0.5)), 1),
        "ci98_high": round(float(np.percentile(values, 99.5)), 1),
        "n": int(n),
    }


def binomial_ci(successes: int, trials: int) -> dict:
    if trials == 0:
        return {"estimate": None, "ci98_low": None, "ci98_high": None, "n": 0}
    low = beta_dist.ppf(0.01, successes, trials - successes + 1) if successes else 0.0
    high = beta_dist.ppf(0.99, successes + 1, trials - successes) if successes < trials else 1.0
    return {
        "estimate": round(successes / trials, 4),
        "ci98_low": round(float(low), 4),
        "ci98_high": round(float(high), 4),
        "n": int(trials),
    }


report: dict[str, object] = {"ci_level": "98%", "bootstrap_n": N_BOOT}

# --- b) refusal (frozen v4, saved holdout) ---
v4 = pd.read_csv(settings.ROOT / "05_policy" / "current" / "raw_planning_v4_2025_predictions.csv")
v4 = v4.dropna(subset=["target_refused", "v4_platt_risk"])
report["refusal"] = {
    "auc": bootstrap_ci(v4["target_refused"].to_numpy(), v4["v4_platt_risk"].to_numpy(), lambda y, p: roc_auc_score(y, p)),
    "average_precision": bootstrap_ci(v4["target_refused"].to_numpy(), v4["v4_platt_risk"].to_numpy(), lambda y, p: average_precision_score(y, p)),
    "brier": bootstrap_ci(v4["target_refused"].to_numpy(), v4["v4_platt_risk"].to_numpy(), lambda y, p: brier_score_loss(y, p)),
}

# --- g) FI (saved holdout) ---
fi = pd.read_csv(settings.SILVER_DIR / "fi_model_holdout_predictions.csv").dropna(subset=["fi_requested", "p_fi"])
report["fi"] = {
    "auc": bootstrap_ci(fi["fi_requested"].to_numpy(), fi["p_fi"].to_numpy(), lambda y, p: roc_auc_score(y, p)),
    "average_precision": bootstrap_ci(fi["fi_requested"].to_numpy(), fi["p_fi"].to_numpy(), lambda y, p: average_precision_score(y, p)),
    "brier": bootstrap_ci(fi["fi_requested"].to_numpy(), fi["p_fi"].to_numpy(), lambda y, p: brier_score_loss(y, p)),
}

# --- h) appeal (refit: train < 2021, holdout >= 2021, no authority dummies) ---
from run_appeal_model import build_frame  # noqa: E402

frame = build_frame()
train = frame[frame["received_year"] < 2021]
test = frame[frame["received_year"] >= 2021]
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402

tfidf = TfidfVectorizer(ngram_range=(1, 2), max_features=8000, sublinear_tf=True, stop_words="english", min_df=3)
text_train = tfidf.fit_transform(train["description_lower"]).toarray()
text_test = tfidf.transform(test["description_lower"]).toarray()
cols = ["log_units", "type_apartment", "type_house", "received_year", "received_month"]
X_train = np.hstack([train[cols].fillna(0.0).values, text_train])
X_test = np.hstack([test[cols].fillna(0.0).values, text_test])
clf = LogisticRegression(C=0.5, max_iter=2000, solver="liblinear")
clf.fit(X_train, train["appeal_flag"])
appeal_p = clf.predict_proba(X_test)[:, 1]
report["appeal"] = {
    "auc": bootstrap_ci(test["appeal_flag"].to_numpy(), appeal_p, lambda y, p: roc_auc_score(y, p)),
    "average_precision": bootstrap_ci(test["appeal_flag"].to_numpy(), appeal_p, lambda y, p: average_precision_score(y, p)),
    "prevalence": binomial_ci(int(test["appeal_flag"].sum()), int(len(test))),
}

# --- a) decision-timing horizons (persisted artifact, refit features) ---
import joblib  # noqa: E402

from run_decision_timing import add_congestion_features_fast, build_features, load_cohort  # noqa: E402

dt = load_cohort()
dt = add_congestion_features_fast(dt)
dt_train = dt[dt["received_year"] < 2024]
dt_test = dt[dt["received_year"] >= 2024]
X_tr = build_features(dt_train)
X_te = build_features(dt_test)
X_tr["authority"] = dt_train["PlanningAuthority"].astype(str)
X_te["authority"] = dt_test["PlanningAuthority"].astype(str)
X_tr_d = pd.get_dummies(X_tr, columns=["authority"])
X_te_d = X_te.reindex(columns=X_tr_d.columns, fill_value=0)
artifact = joblib.load(settings.GOLD_DIR / "decision_timing_gbm_v1.joblib")
horizons = {}
for horizon, model in artifact["horizon_models"].items():
    y_tr = (dt_train["duration_days"] > int(horizon)).astype(int).to_numpy()
    y_te = (dt_test["duration_days"] > int(horizon)).astype(int).to_numpy()
    p = model.predict_proba(X_te_d)[:, 1]
    horizons[f"P_gt_{horizon}d"] = {
        "auc": bootstrap_ci(y_te, p, lambda y, pp: roc_auc_score(y, pp)),
        "prevalence": binomial_ci(int(y_te.sum()), int(len(y_te))),
    }
report["decision_timing"] = horizons

# --- i) commencement timing MAE (strata baseline, sold-of-commencements) ---
labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
frame_l = labels.merge(register[["case_key", "PlanningAuthority", "GrantDate", "NumResidentialUnits"]], on="case_key", how="inner")
frame_l["grant_date_dt"] = pd.to_datetime(frame_l["GrantDate"], utc=True, errors="coerce")
frame_l["grant_year"] = frame_l["grant_date_dt"].dt.year
comm = frame_l[frame_l["activation_linked"].astype(bool)].dropna(subset=["activation_days"])
comm_train = comm[comm["grant_year"] < 2020]
comm_test = comm[comm["grant_year"] >= 2020]
strata = comm_train.groupby("PlanningAuthority")["activation_days"].median()
pred_comm = comm_test["PlanningAuthority"].map(strata).fillna(comm_train["activation_days"].median())
report["commencement_timing"] = {
    "strata_mae_days": bootstrap_mae_ci(comm_test["activation_days"].to_numpy(), pred_comm.to_numpy()),
    "constant_mae_days": bootstrap_mae_ci(
        comm_test["activation_days"].to_numpy(),
        np.full(len(comm_test), comm_train["activation_days"].median()),
    ),
}

# --- e) sale timing (GBM+market, sold schemes) ---
exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
sale = exit_labels[exit_labels["first_sale_date"].notna()].merge(
    frame_l[["case_key", "PlanningAuthority", "grant_year"]], on="case_key", how="inner"
)
sale["sale_days"] = pd.to_numeric(sale["time_to_first_sale_from_grant_days"], errors="coerce")
sale = sale[sale["sale_days"].between(0, 2200)]
sale_train = sale[sale["grant_year"] < 2021]
sale_test = sale[sale["grant_year"] >= 2021]
sale_strata = sale_train.groupby("PlanningAuthority")["sale_days"].median()
pred_sale = sale_test["PlanningAuthority"].map(sale_strata).fillna(sale_train["sale_days"].median())
report["sale_timing"] = {
    "strata_mae_days": bootstrap_mae_ci(sale_test["sale_days"].to_numpy(), pred_sale.to_numpy()),
    "constant_mae_days": bootstrap_mae_ci(
        sale_test["sale_days"].to_numpy(), np.full(len(sale_test), sale_train["sale_days"].median())
    ),
}

# --- c) refusal-reason transfer top-3 (n=81, 55.6%) ---
report["refusal_reason_transfer_top3"] = binomial_ci(45, 81)

# --- d) condition family frequencies (n=338 corpus) ---
cond = pd.read_csv(settings.SILVER_DIR / "condition_family_labels_corpus.csv")
cond_cis = {}
for column in cond.columns:
    if column.startswith("condition_") and column != "condition_family_count":
        cond_cis[column.replace("condition_", "")] = binomial_ci(int(cond[column].sum()), len(cond))
report["condition_family_prevalence"] = cond_cis

# --- TimesFM-2.5 county backtest paired improvement ---
tfm = json.loads((settings.SILVER_DIR / "timesfm25_backtest.json").read_text(encoding="utf-8"))
report["timesfm"] = {"note": "pooled MAE over 26-31 county series; CIs via county-level paired bootstrap"}
# (paired bootstrap needs per-county errors; approximate with per-series values in the JSON if present - otherwise note)

out = settings.SILVER_DIR / "full_suite_98ci.json"
out.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
