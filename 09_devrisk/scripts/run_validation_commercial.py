"""Commercial validation: target segments, reliability, decision value.

Answers the reviewer's three challenges on the untouched 2025 holdout
(raw_planning_v4_2025_predictions.csv, n=15,221):
  C1 target-population validity: GE10 (bucket '10+ units'), 50+, 100+ units
  C2 calibration: decile reliability overall, by authority, bucket, quarter
  C3 decision value: screening-threshold expected utility, model vs priors

Output: silver/validation/commercial_validation.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "09_devrisk" / "data" / "silver" / "validation"
OUT.mkdir(parents=True, exist_ok=True)
CUR = ROOT / "05_policy" / "current"

sys.path.insert(0, str(ROOT / "09_devrisk"))
from devrisk import settings  # noqa: E402


def brier(y, p):
    return float(np.mean((np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2))


def auc_ci(y, p, rng, n_boot=500):
    y = np.asarray(y)
    p = np.asarray(p)
    scores = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        if len(np.unique(y[idx])) < 2:
            continue
        scores.append(roc_auc_score(y[idx], p[idx]))
    return round(float(np.quantile(scores, 0.025)), 3), round(float(np.quantile(scores, 0.975)), 3)


def decision_value(y, p_model, p_prior, loss_mult, rng, n_grid=200):
    """Expected utility of walk-away screening under model vs prior."""
    ts = np.linspace(0.05, 0.5, n_grid)
    best = {}
    for name, p in (("model", p_model), ("prior", p_prior)):
        utils = []
        for t in ts:
            proceed = p < t
            u = float(np.mean(np.where(proceed, 1 - y * (1 + loss_mult), 0)))
            utils.append((u, t))
        u, t = max(utils, key=lambda x: x[0])
        best[name] = {"best_utility_per_scheme": round(u, 4), "threshold": round(float(t), 3),
                      "share_proceeding": round(float((p < t).mean()), 3)}
    return best


def main() -> None:
    d = pd.read_csv(CUR / "raw_planning_v4_2025_predictions.csv", low_memory=False)
    d["p"] = pd.to_numeric(d["v4_platt_risk"], errors="coerce")
    d["y"] = pd.to_numeric(d["target_refused"], errors="coerce")
    d["q"] = pd.to_datetime(d["received_date_dt"], utc=True, errors="coerce").dt.to_period("Q").astype(str)
    d = d.dropna(subset=["p", "y"])
    # units joins for 50+/100+ within GE10
    def norm(s):
        return "".join(c for c in str(s).lower() if c.isalnum())
    units_map = {}
    for path in ("ground_source_units_corrected.csv", "holdout_units_extracted.csv", "ge10_units_reextracted.csv"):
        f = pd.read_csv(ROOT / "02_development" / "current" / path, low_memory=False)
        col = [c for c in f.columns if "unit" in c.lower()]
        if not col:
            continue
        ucol = col[0]
        for k, v in zip(f["case_key"].astype(str), pd.to_numeric(f[ucol], errors="coerce")):
            if pd.notna(v):
                units_map[norm(k)] = v
    d["units"] = d["case_key"].map(lambda k: units_map.get(norm(k)))
    report = {"holdout": {"n": int(len(d)), "refusal_rate": round(float(d["y"].mean()), 4),
                          "n_ge10_by_bucket": int((d["application_bucket"] == "10+ units").sum()),
                          "n_with_units": int(d["units"].notna().sum())}}

    rng = np.random.default_rng(7)
    segments = {}
    ge10 = d[d["application_bucket"] == "10+ units"]
    masks = {"ge10_plus": d["application_bucket"] == "10+ units",
             "units_50_plus": d["units"] >= 50,
             "units_100_plus": d["units"] >= 100}
    for name, mask in masks.items():
        seg = d[mask]
        if len(seg) < 10:
            continue
        prior = seg["y"].mean()
        auth_prior = seg.groupby("PlanningAuthority")["y"].transform("mean")
        segments[name] = {
            "n": int(len(seg)), "refusal_rate": round(float(seg["y"].mean()), 4),
            "model_auc": round(float(roc_auc_score(seg["y"], seg["p"])), 3) if seg["y"].nunique() == 2 else None,
            "model_brier": round(brier(seg["y"], seg["p"]), 4),
            "national_prior_brier": round(brier(seg["y"], prior), 4),
            "authority_prior_brier": round(brier(seg["y"], auth_prior), 4),
            "brier_improvement_vs_prior_pp": round((brier(seg["y"], prior) - brier(seg["y"], seg["p"])) * 100, 2),
            "auc_ci95": auc_ci(seg["y"].to_numpy(), seg["p"].to_numpy(), rng) if seg["y"].nunique() == 2 else None,
        }
    # units distribution inside GE10
    if ge10["units"].notna().sum() >= 5:
        report["ge10_units_distribution"] = {
            "n_known": int(ge10["units"].notna().sum()),
            "median": float(ge10["units"].median()), "p25": float(ge10["units"].quantile(0.25)),
            "p75": float(ge10["units"].quantile(0.75)), "max": float(ge10["units"].max())}
    report["segments"] = segments

    # C2 reliability: decile curves
    def rel(g, name):
        g = g.copy()
        if len(g) < 100:
            return None
        g["decile"] = pd.qcut(g["p"], 10, labels=False, duplicates="drop")
        return {name: {"n": int(len(g)),
                       "curve": [{"decile": int(k), "n": int(len(gg)), "mean_pred": round(float(gg["p"].mean()), 4),
                                  "obs_rate": round(float(gg["y"].mean()), 4)}
                                 for k, gg in g.groupby("decile")]}}
    reliability = rel(d, "overall")
    for auth, g in d.groupby("PlanningAuthority"):
        r = rel(g, auth)
        if r:
            reliability.update(r)
    for bucket, g in d.groupby("application_bucket"):
        r = rel(g, bucket)
        if r:
            reliability.update(r)
    for q, g in d.groupby("q"):
        r = rel(g, q)
        if r:
            reliability.update(r)
    report["reliability"] = reliability

    # calibration stats overall
    d["decile"] = pd.qcut(d["p"], 10, labels=False, duplicates="drop")
    curve = [{"decile": int(k), "mean_pred": round(float(gg["p"].mean()), 4),
              "obs_rate": round(float(gg["y"].mean()), 4), "n": int(len(gg))}
             for k, gg in d.groupby("decile")]
    report["overall_calibration"] = {"max_decile_delta_pp": round(
        float(max(abs(c["obs_rate"] - c["mean_pred"]) for c in curve) * 100), 2), "curve": curve}

    # C3 decision value on the GE10 segment and overall
    for name, seg in (("ge10", ge10), ("overall", d)):
        prior = seg["y"].mean()
        dv = decision_value(seg["y"].to_numpy(), seg["p"].to_numpy(),
                            np.full(len(seg), prior), loss_mult=2.0, rng=rng)
        report[f"decision_value_{name}"] = dv
    (OUT / "commercial_validation.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"n": report["holdout"]["n"], "n_ge10_by_bucket": report["holdout"]["n_ge10_by_bucket"]}, indent=1))
    print(json.dumps(report["segments"], indent=1))
    if "ge10_units_distribution" in report:
        print(json.dumps(report["ge10_units_distribution"], indent=1))
    print(json.dumps(report["overall_calibration"]["max_decile_delta_pp"]))
    print(json.dumps({k: v for k, v in report.items() if k.startswith("decision_value")}, indent=1))
    print("saved ->", OUT / "commercial_validation.json")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
