"""Runner: survival pipeline audit (8 checks).

The commencement hazard experiment returned td-AUC 0.00-0.01 and c-index
0.48. Checks: sign inversion, event coding, synthetic-data sanity,
KM/intercept-only baselines, censoring-window errors, duplication, and
proper censoring-aware evaluation (incident/dynamic AUC with KM IPCW).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.models.survival import kaplan_meier  # noqa: E402

CENSOR = pd.Timestamp("2026-09-27", tz="UTC")
HORIZONS = [365, 730, 1096]


def km_ipcw_weights(y_obs: np.ndarray, censored: np.ndarray, horizon: float) -> np.ndarray:
    """Inverse-probability-of-censoring weights via KM on the censoring
    distribution (censoring = event, per standard practice)."""
    km = kaplan_meier(y_obs[censored], np.ones(int(censored.sum()), dtype=int))
    surv = km[km["t"] <= horizon]["survival"]
    g = float(surv.iloc[-1]) if len(surv) else 1.0
    weights = np.ones(len(y_obs))
    at_risk = (y_obs >= horizon) | (~censored & (y_obs <= horizon))
    weights[censored & (y_obs < horizon)] = 0.0  # censored before horizon: not evaluable
    weights = np.where((y_obs <= horizon) & (~censored), 1.0 / max(g, 1e-9), weights)
    return weights


def dynamic_auc(y_obs: np.ndarray, censored: np.ndarray, score: np.ndarray, horizon: float) -> float:
    """Incident/dynamic AUC at a horizon, IPCW-weighted."""
    weights = km_ipcw_weights(y_obs, censored, horizon)
    evaluable = weights > 0
    if evaluable.sum() < 10:
        return np.nan
    y_h = np.where(censored, 0, y_obs <= horizon)
    y_h = y_h[evaluable]
    weights_e = weights[evaluable]
    score_e = score[evaluable]
    if y_h.min() == y_h.max():
        return np.nan
    order = np.argsort(score_e)
    y_sorted = y_h[order]
    w_sorted = weights_e[order]
    total_pos = w_sorted[y_sorted == 1].sum()
    total_neg = w_sorted[y_sorted == 0].sum()
    if total_pos == 0 or total_neg == 0:
        return np.nan
    cum_neg = np.cumsum(w_sorted * (y_sorted == 0))
    auc = float((w_sorted * (y_sorted == 1) * cum_neg).sum() / (total_pos * total_neg))
    return auc


def synthetic_check() -> dict:
    """Synthetic survival data with a known one-feature relationship."""
    rng = np.random.default_rng(7)
    n = 400
    x = rng.normal(size=n)
    true_scale = np.exp(0.5 * x)
    event_time = rng.weibull(1.0, size=n) * true_scale * 400.0
    censor_time = rng.uniform(100, 3000, size=n)
    y_obs = np.minimum(event_time, censor_time)
    censored = event_time > censor_time
    # true relationship: larger x -> shorter time (scale larger -> weibull scaled up -> LONGER).
    # event_time = weibull * scale, so larger x -> longer time -> score should rank INVERSE to x.
    return {
        "n": n, "events": int((~censored).sum()),
        "auc_score_minus_x_365": round(dynamic_auc(y_obs, censored, -x, 365.0), 3),
        "auc_score_plus_x_365": round(dynamic_auc(y_obs, censored, x, 365.0), 3),
    }


def load_commencement_data() -> pd.DataFrame:
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    frame = labels.merge(register[["case_key", "PlanningAuthority", "GrantDate", "DevelopmentDescription",
                                   "NumResidentialUnits", "AreaofSite"]], on="case_key", how="inner")
    frame["grant_dt"] = pd.to_datetime(frame["GrantDate"], utc=True, errors="coerce")
    frame["activation"] = pd.to_numeric(frame["activation_days"], errors="coerce").clip(lower=0)
    frame = frame.dropna(subset=["grant_dt"])
    frame = frame[frame["grant_dt"] < CENSOR - pd.Timedelta(days=180)]
    frame["y_obs"] = np.where(frame["activation"].notna(), frame["activation"],
                              (CENSOR - frame["grant_dt"]).dt.days)
    frame["censored"] = frame["activation"].isna()
    return frame


if __name__ == "__main__":
    report: dict = {}

    # Check 4: synthetic data with known relationship.
    report["synthetic"] = synthetic_check()

    # Checks 1-3, 5-8 on the real commencement data.
    data = load_commencement_data()
    train = data[data["grant_dt"] < pd.Timestamp("2020-01-01", tz="UTC")]
    test = data[data["grant_dt"] >= pd.Timestamp("2020-01-01", tz="UTC")]
    report["data"] = {
        "train": {"n": int(len(train)), "events": int((~train["censored"]).sum())},
        "test": {"n": int(len(test)), "events": int((~test["censored"]).sum())},
        "duplicate_case_keys": int(data["case_key"].duplicated().sum()),
        "negative_y_obs": int((data["y_obs"] < 0).sum()),
        "censor_before_observed_activation": int(((~data["censored"]) & (data["y_obs"] > (CENSOR - data["grant_dt"]).dt.days)).sum()),
    }

    # Intercept-only hazard (person-period) baseline -> per-scheme incidence.
    def person_periods(part: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for _, scheme in part.iterrows():
            duration = min(float(scheme["y_obs"]), 2000.0)
            for start in np.arange(0.0, duration, 30.0):
                end = min(start + 30.0, duration)
                y = int((~scheme["censored"]) and scheme["y_obs"] <= start + 30.0)
                rows.append({"scheme_id": scheme["case_key"], "interval_start": start, "y": y})
                if y:
                    break
        return pd.DataFrame(rows)

    pp_train = person_periods(train)
    pp_test = person_periods(test)
    intercept = LogisticRegression(C=1e9, max_iter=2000, solver="liblinear")
    intercept.fit(np.ones((len(pp_train), 1)), pp_train["y"])
    pp_test = pp_test.copy()
    pp_test["hazard"] = intercept.predict_proba(np.ones((len(pp_test), 1)))[:, 1]

    def incidence_map(pp: pd.DataFrame, horizon: float) -> pd.Series:
        def prob(group: pd.DataFrame) -> float:
            incidence, survival = 0.0, 1.0
            for _, row in group.sort_values("interval_start").iterrows():
                if row["interval_start"] >= horizon:
                    break
                incidence += survival * row["hazard"]
                survival *= (1.0 - row["hazard"])
            return float(incidence)
        return pp.groupby("scheme_id").apply(prob, include_groups=False)

    km = kaplan_meier(train["y_obs"].to_numpy(), (~train["censored"]).astype(int).to_numpy())
    report["baselines"] = {}
    for horizon in HORIZONS:
        y_obs = test["y_obs"].to_numpy()
        censored = test["censored"].to_numpy()
        score = test["case_key"].map(incidence_map(pp_test, horizon)).fillna(0.0).to_numpy()
        km_p = float(1.0 - km[km["t"] <= horizon]["survival"].iloc[-1]) if len(km[km["t"] <= horizon]) else 0.0
        report["baselines"][str(horizon)] = {
            "km_prob": round(km_p, 4),
            "intercept_hazard_dynAUC": round(dynamic_auc(y_obs, censored, score, horizon), 3),
            "intercept_hazard_dynAUC_flipped": round(dynamic_auc(y_obs, censored, -score, horizon), 3),
            "observed_event_rate": round(float((~censored & (y_obs <= horizon)).mean()), 4),
        }

    # Check 6: schemes whose observation window is shorter than the horizon
    # (censored before horizon) - they are excluded by IPCW, count them.
    for horizon in HORIZONS:
        short_window = int(((test["y_obs"] < horizon) & test["censored"]).sum())
        report.setdefault("censored_before_horizon", {})[str(horizon)] = short_window

    out = settings.SILVER_DIR / "survival_audit.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
