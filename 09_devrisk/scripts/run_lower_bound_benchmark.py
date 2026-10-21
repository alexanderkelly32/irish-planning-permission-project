"""Runner: initial-model lower-bound benchmark for timing outcomes.

Outcomes:
  - decision:   submission -> local decision (register durations)
  - commencement: final grant -> first confirmed commencement (BCMS links)
  - completion: commencement -> completion certificate (BCMS CCC)
  - first_sale: final grant -> first confirmed PPR sale

Model ladder (each outcome, temporal holdout):
  M0 constant quantiles  -> hard lower bound any real model must beat
  M1 strata quantiles    (authority x anchor-year x size band, fallbacks)
  M2 current best where it exists (GBM for decision; none promoted yet for
     commencement/completion/sale)

Metrics: pinball loss at P20/P50/P80, MAE at median, % within +/-30 and
+/-90 days, horizon classification (AUC + calibration) where feasible.
Censored outcomes (commencement/completion) are benchmarked on the
event-observed subset, flagged as conditional-on-event.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import brier_score_loss, roc_auc_score  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.models.pain_features import bootstrap_auc  # noqa: E402

QUANTILES = (0.2, 0.5, 0.8)


def pinball(y: np.ndarray, pred: np.ndarray, tau: float) -> float:
    diff = y - pred
    return float(np.mean(np.where(diff >= 0, tau * diff, (tau - 1) * diff)))


def within_band(y: np.ndarray, pred: np.ndarray, days: float) -> float:
    return float(np.mean(np.abs(y - pred) <= days))


def strata_quantiles(train: pd.DataFrame, test: pd.DataFrame, keys: list[str], anchor_col: str) -> pd.DataFrame:
    """Strata quantiles with a proper fallback chain: full keys -> authority -> overall."""
    out = test.copy()
    overall = {q: float(train[anchor_col].quantile(q)) for q in QUANTILES}
    for q in QUANTILES:
        out[f"pred_q{int(q * 100)}"] = np.nan

    for level_keys in (keys, keys[:1], []):
        group_keys = [k for k in level_keys if k in train.columns and k in test.columns]
        if not group_keys:
            continue
        strata = train.groupby(group_keys, observed=True)[anchor_col].quantile(list(QUANTILES)).unstack()
        strata = strata.rename(columns={quantile: f"next_q{int(quantile * 100)}" for quantile in QUANTILES})
        partial = out.merge(strata.reset_index(), on=group_keys, how="left")
        for q in QUANTILES:
            pred_col = f"pred_q{int(q * 100)}"
            next_col = f"next_q{int(q * 100)}"
            missing = out[pred_col].isna().to_numpy()
            out[pred_col] = np.where(missing, partial[next_col].to_numpy(), out[pred_col].to_numpy())
    for q in QUANTILES:
        out[f"pred_q{int(q * 100)}"] = out[f"pred_q{int(q * 100)}"].fillna(overall[q])
    return out


def evaluate_outcome(
    frame: pd.DataFrame,
    *,
    name: str,
    duration_col: str,
    date_col: str,
    split_col: str,
    split_before: int,
    size_band_col: str | None,
    horizon_days: int | None = None,
    conditional_note: str | None = None,
) -> dict:
    work = frame.dropna(subset=[duration_col, date_col]).copy()
    work["anchor_year"] = work[date_col].dt.year
    work = work[work[duration_col] >= 0]
    train = work[work[split_col] < split_before]
    test = work[work[split_col] >= split_before]
    if len(train) < 30 or len(test) < 20:
        return {"outcome": name, "status": "insufficient_data", "n_train": int(len(train)), "n_test": int(len(test))}

    y_train = train[duration_col].to_numpy()
    y_test = test[duration_col].to_numpy()

    result: dict = {
        "outcome": name,
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "split": f"{split_col} < {split_before} train, >= {split_before} holdout",
        "test_median_days": round(float(np.median(y_test)), 1),
        "test_p20_p80_days": [round(float(np.quantile(y_test, 0.2)), 1), round(float(np.quantile(y_test, 0.8)), 1)],
    }
    if conditional_note:
        result["note"] = conditional_note

    constant = {q: float(np.quantile(y_train, q)) for q in QUANTILES}
    strata_frame = strata_quantiles(train, test, ["PlanningAuthority", "anchor_year"] + ([size_band_col] if size_band_col else []), duration_col)
    for label, get_pred in (
        ("constant", lambda q: np.full(len(y_test), constant[q])),
        ("strata", lambda q: strata_frame[f"pred_q{int(q * 100)}"].to_numpy()),
    ):
        result[f"{label}_pinball"] = {f"p{int(q * 100)}": round(pinball(y_test, get_pred(q), q), 1) for q in QUANTILES}
        median_pred = get_pred(0.5)
        result[f"{label}_mae"] = round(float(np.mean(np.abs(y_test - median_pred))), 1)
        result[f"{label}_pct_within_30d"] = round(within_band(y_test, median_pred, 30) * 100, 1)
        result[f"{label}_pct_within_90d"] = round(within_band(y_test, median_pred, 90) * 100, 1)

    if horizon_days:
        y_train_h = (y_train > horizon_days).astype(int)
        y_test_h = (y_test > horizon_days).astype(int)
        if y_train_h.sum() >= 10 and y_test_h.sum() >= 5:
            strata_rate = strata_frame.groupby(["PlanningAuthority"])[duration_col].apply(lambda s: (s > horizon_days).mean()) if False else None
            base_rate = float(y_train_h.mean())
            brier_base = float(brier_score_loss(y_test_h, np.full(len(y_test_h), base_rate)))
            from sklearn.linear_model import LogisticRegression

            feats = pd.DataFrame({
                "auth": test["PlanningAuthority"].astype(str),
                "anchor_year": test["anchor_year"].astype(float),
            })
            feats_train = pd.DataFrame({"auth": train["PlanningAuthority"].astype(str), "anchor_year": train["anchor_year"].astype(float)})
            feats_d = pd.get_dummies(feats, columns=["auth"])
            feats_train_d = pd.get_dummies(feats_train, columns=["auth"])
            feats_d = feats_d.reindex(columns=feats_train_d.columns, fill_value=0)
            clf = LogisticRegression(C=1.0, max_iter=2000, solver="liblinear")
            clf.fit(feats_train_d, y_train_h)
            p = np.clip(clf.predict_proba(feats_d)[:, 1], 1e-6, 1 - 1e-6)
            lo, hi = bootstrap_auc(y_test_h, p, seed=0)
            result[f"horizon_{horizon_days}d"] = {
                "train_prevalence": round(base_rate, 4),
                "test_prevalence": round(float(y_test_h.mean()), 4),
                "base_rate_brier": round(brier_base, 4),
                "logistic_brier": round(float(brier_score_loss(y_test_h, p)), 4),
                "roc_auc": round(float(roc_auc_score(y_test_h, p)), 4),
                "auc_ci_low": round(lo, 4),
                "auc_ci_high": round(hi, 4),
            }
    return result


if __name__ == "__main__":
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv").rename(columns={"scheme_id": "case_key"})

    frame = labels.merge(register[["case_key", "PlanningAuthority", "NumResidentialUnits", "ReceivedDate", "DecisionDate", "GrantDate"]], on="case_key", how="inner")
    frame["received_year"] = pd.to_datetime(frame["ReceivedDate"], utc=True, errors="coerce").dt.year
    frame["grant_date_dt"] = pd.to_datetime(frame["GrantDate"], utc=True, errors="coerce")
    frame["grant_year"] = frame["grant_date_dt"].dt.year
    frame["decision_duration"] = (pd.to_datetime(frame["DecisionDate"], utc=True, errors="coerce") - pd.to_datetime(frame["ReceivedDate"], utc=True, errors="coerce")).dt.days
    units = pd.to_numeric(frame["NumResidentialUnits"], errors="coerce")
    frame["size_band"] = pd.cut(units, bins=[-np.inf, 29, 99, 249, np.inf], labels=["10-29", "30-99", "100-249", "250+"])

    # Activation: commencements observed only (conditional benchmark).
    activation = frame[frame["activation_linked"].astype(bool)].copy()
    activation["activation_date_dt"] = activation["grant_date_dt"] + pd.to_timedelta(activation["activation_days"].fillna(0), unit="D")

    # Completion: among commenced, completion observed only.
    completion = frame[frame["activation_linked"].astype(bool) & frame["completion_linked"].astype(bool)].copy()
    completion["commencement_year"] = (pd.to_datetime(completion["GrantDate"], utc=True, errors="coerce") + pd.to_timedelta(completion["activation_days"].fillna(0), unit="D")).dt.year

    # First sale: among schemes with confirmed PPR first sale.
    sale = exit_labels[exit_labels["first_sale_date"].notna()].copy()
    sale = sale.merge(frame[["case_key", "PlanningAuthority", "NumResidentialUnits", "GrantDate", "grant_year"]], on="case_key", how="inner")
    sale["grant_date_dt"] = pd.to_datetime(sale["GrantDate"], utc=True, errors="coerce")
    sale["size_band"] = pd.cut(pd.to_numeric(sale["NumResidentialUnits"], errors="coerce"), bins=[-np.inf, 29, 99, 249, np.inf], labels=["10-29", "30-99", "100-249", "250+"])

    results = []
    frame["received_date_dt"] = pd.to_datetime(frame["ReceivedDate"], utc=True, errors="coerce")

    # Decision: use the full GE10 register cohort (not just the pain pool).
    ge10 = register.copy()
    ge10["received_date_dt"] = pd.to_datetime(ge10["ReceivedDate"], utc=True, errors="coerce")
    ge10["decision_date_dt"] = pd.to_datetime(ge10["DecisionDate"], utc=True, errors="coerce")
    ge10["decision_duration"] = (ge10["decision_date_dt"] - ge10["received_date_dt"]).dt.days
    ge10_units = pd.to_numeric(ge10["NumResidentialUnits"], errors="coerce")
    ge10 = ge10[ge10_units.ge(10) & ge10["decision_duration"].between(0, 1095)]
    ge10["received_year"] = ge10["received_date_dt"].dt.year
    ge10["size_band"] = pd.cut(ge10_units[ge10.index], bins=[-np.inf, 29, 99, 249, np.inf], labels=["10-29", "30-99", "100-249", "250+"])
    results.append(evaluate_outcome(
        ge10, name="time_to_decision", duration_col="decision_duration",
        date_col="received_date_dt", split_col="received_year", split_before=2024,
        size_band_col="size_band", horizon_days=183,
    ))
    results.append(evaluate_outcome(
        activation, name="time_to_commencement", duration_col="activation_days",
        date_col="grant_date_dt", split_col="grant_year", split_before=2020,
        size_band_col="size_band", horizon_days=730,
        conditional_note="conditional on confirmed commencement (BCMS-linked subset only)",
    ))
    completion["commencement_date_dt"] = pd.to_datetime(completion["GrantDate"], utc=True, errors="coerce") + pd.to_timedelta(completion["activation_days"].fillna(0), unit="D")
    results.append(evaluate_outcome(
        completion, name="time_to_completion", duration_col="completion_days",
        date_col="commencement_date_dt", split_col="grant_year", split_before=2020,
        size_band_col="size_band", horizon_days=1096,
        conditional_note="conditional on confirmed commencement AND completion (completed subset)",
    ))
    sale["grant_date_dt"] = pd.to_datetime(sale["GrantDate"], utc=True, errors="coerce")
    results.append(evaluate_outcome(
        sale, name="time_to_first_sale", duration_col="time_to_first_sale_from_grant_days",
        date_col="grant_date_dt", split_col="grant_year", split_before=2020,
        size_band_col="size_band", horizon_days=730,
        conditional_note="conditional on confirmed PPR first sale (sold subset)",
    ))

    report = {"as_of": "2026-09-28", "lower_bound_framing": "constant quantiles = floor any model must beat; strata = current default; decision GBM = current best", "outcomes": results}
    out = settings.SILVER_DIR / "lower_bound_benchmark.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
