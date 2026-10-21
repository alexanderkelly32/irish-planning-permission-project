"""Blend experiment (reviewer protocol): combine model ranking with
authority-level calibration.

Protocol:
  - Frozen v4-full scores 2024+2025 holdout (calibrated track).
  - TRAIN period: received in 2024. Fit authority priors (authority mean on
    2024, fallback national), choose blend weight w (grid) and decision
    threshold t (grid) by max expected utility (grant +1, refusal -2,
    abstain 0). FREEZE both.
  - EVAL period: received in 2025. No re-optimisation.
  - Policies: always-proceed, authority-only, model-only, blend.
  - Paired bootstrap CIs on utility differences.
  - Segments: overall + GE10.
Output: silver/validation/blend_experiment.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "09_devrisk" / "data" / "silver" / "validation"
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from build_8020_regime_experiment import build_data  # noqa: E402

ARTIFACT = ROOT / "05_policy" / "current" / "model_v4" / "national_residential_v4_full.joblib"
LOSS = 2.0
THEORETICAL_THRESHOLD = 1 / 3


def utility(y, p, t, loss=LOSS):
    proceed = p < t
    return float(np.mean(np.where(proceed, 1 - y * (1 + loss), 0)))


def fit_policy(y, p_candidates, loss=LOSS):
    """Choose threshold (and weight if candidates given) by max utility."""
    best = {}
    ts = np.linspace(0.05, 0.60, 120)
    if isinstance(p_candidates, dict):
        best_u, best_t, best_w = -np.inf, None, None
        for w, p in p_candidates.items():
            for t in ts:
                u = utility(y, p, t, loss)
                if u > best_u:
                    best_u, best_t, best_w = u, float(t), w
        return {"utility": round(best_u, 4), "threshold": best_t, "weight": best_w}
    best_u, best_t = -np.inf, None
    for t in ts:
        u = utility(y, p_candidates, t, loss)
        if u > best_u:
            best_u, best_t = u, float(t)
    return {"utility": round(best_u, 4), "threshold": best_t}


def bootstrap_compare(y, p_map, rng, n_boot=1000):
    """Paired bootstrap utilities + pairwise differences for frozen policies."""
    idx = np.arange(len(y))
    utils = {k: [] for k in p_map}
    diffs = {}
    pairs = list(p_map.keys())
    for a in pairs:
        for b in pairs:
            if a < b:
                diffs[f"{a}_vs_{b}"] = []
    for _ in range(n_boot):
        i = rng.integers(0, len(y), len(y))
        ys = y[i]
        for k, (p, t) in p_map.items():
            utils[k].append(utility(ys, p[i], t))
        vals = {k: utility(ys, p_map[k][0][i], p_map[k][1]) for k in p_map}
        for a in pairs:
            for b in pairs:
                if a < b:
                    diffs[f"{a}_vs_{b}"].append(vals[a] - vals[b])
    out = {k: {"mean": round(float(np.mean(v)), 4),
               "ci95": [round(float(np.quantile(v, 0.025)), 4), round(float(np.quantile(v, 0.975)), 4)]}
           for k, v in utils.items()}
    for k, v in diffs.items():
        out[k] = {"mean": round(float(np.mean(v)), 4),
                  "ci95": [round(float(np.quantile(v, 0.025)), 4), round(float(np.quantile(v, 0.975)), 4)],
                  "p_diff_gt0": round(float(np.mean(np.array(v) > 0)), 3)}
    return out


def run_segment(name, train, eval_, rng):
    rep = {"train_n": int(len(train)), "eval_n": int(len(eval_)),
           "train_refusal": round(float(train["y"].mean()), 4),
           "eval_refusal": round(float(eval_["y"].mean()), 4),
           "theoretical_optimal_threshold": round(THEORETICAL_THRESHOLD, 3)}
    if len(eval_) < 30 or len(train) < 30:
        rep["skipped"] = "segment too small"
        return rep
    # authority priors from train only
    auth_mean = train.groupby("PlanningAuthority")["y"].mean()
    natl = float(train["y"].mean())
    eval_prior = eval_["PlanningAuthority"].map(auth_mean).fillna(natl).to_numpy()
    train_prior = train["PlanningAuthority"].map(auth_mean).fillna(natl).to_numpy()
    p_model_t = train["p"].to_numpy()
    p_model_e = eval_["p"].to_numpy()
    y_t = train["y"].to_numpy()
    y_e = eval_["y"].to_numpy()

    # choose blend weight + threshold on train
    blend_candidates = {round(w, 2): w * p_model_t + (1 - w) * train_prior for w in np.arange(0, 1.05, 0.05)}
    blend_fit = fit_policy(y_t, blend_candidates)
    model_fit = fit_policy(y_t, p_model_t)
    auth_fit = fit_policy(y_t, train_prior)
    rep["train_fits"] = {"model": model_fit, "authority": auth_fit, "blend": blend_fit}
    rep["train_aucs"] = {
        "model": round(float(roc_auc_score(y_t, p_model_t)), 3),
        "authority_prior": round(float(roc_auc_score(y_t, train_prior)), 3),
        "blend": round(float(roc_auc_score(y_t, blend_fit["weight"] * p_model_t + (1 - blend_fit["weight"]) * train_prior)), 3)}

    w = blend_fit["weight"]
    p_map = {
        "always_proceed": (np.zeros(len(y_e)), 2.0),
        "authority_only": (eval_prior, auth_fit["threshold"]),
        "model_only": (p_model_e, model_fit["threshold"]),
        "blend": (w * p_model_e + (1 - w) * eval_prior, blend_fit["threshold"]),
    }
    rep["eval_bootstrap"] = bootstrap_compare(y_e, p_map, rng)
    return rep


def main() -> None:
    data, _tr, _te, _y = build_data()
    artifact = joblib.load(ARTIFACT)
    feats = artifact["feature_columns"]
    hold = data[data["received_date_dt"] >= pd.Timestamp("2024-01-01", tz="UTC")].copy()
    print("scoring holdout n=", len(hold), flush=True)
    hold["p"] = artifact["calibrated_base_model"].predict_proba(hold[feats])[:, 1]
    hold["p"] = artifact["isotonic_calibrator"].predict(hold["p"])
    hold["y"] = hold["target_refused"].astype(int)
    hold["year"] = hold["received_date_dt"].dt.year
    train = hold[hold["year"] == 2024]
    eval_ = hold[hold["year"] == 2025]
    ge10 = hold["application_bucket"] == "10+ units"
    rng = np.random.default_rng(11)
    report = {"protocol": "fit blend weight + thresholds on 2024; frozen; evaluate 2025",
              "utility_payoffs": {"grant": 1, "refusal": -1 - LOSS, "abstain": 0},
              "theoretical_optimal_threshold": round(THEORETICAL_THRESHOLD, 3),
              "overall": run_segment("overall", train, eval_, rng),
              "ge10": run_segment("ge10", train[ge10], eval_[ge10], rng)}
    (OUT / "blend_experiment.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    for k in ("overall", "ge10"):
        seg = report[k]
        print(json.dumps({k: {kk: seg[kk] for kk in ("train_n", "eval_n", "train_refusal", "eval_refusal", "train_fits", "train_aucs")}}, indent=1))
        if "eval_bootstrap" in seg:
            print(json.dumps({f"{k}_eval": seg["eval_bootstrap"]}, indent=1))
    print("saved ->", OUT / "blend_experiment.json")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
