"""Calibration sprint: state-conditional distributions under temporal drift.

Estimator variants (time-safe, replay protocol, 5y source window):
V0 completed-only empirical quantiles (current product estimator)
V1 conformal-adjusted quantiles (calibrate quantile expansion factor on
   the preceding era, apply on the next era)
V2 era-weighted empirical (exponential recency weights)
V3 censored-KM with capped censoring (cap 730d - dormant tail guard)

Judged on OUT-OF-TIME interval coverage (target within ~5pp of nominal)
and interval width, per era.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "calibration"
OUT.mkdir(parents=True, exist_ok=True)
SNAP = pd.Timestamp("2026-10-01")

PAIRS = [("final_grant", "notice_filed"), ("final_grant", "commenced"),
         ("notice_filed", "commenced"), ("commenced", "first_ccc"),
         ("commenced", "pct25"), ("first_ccc", "pct25"), ("pct25", "pct50"),
         ("pct50", "pct75"), ("pct75", "final_ccc"), ("first_ccc", "final_ccc"),
         ("final_ccc", "first_sale"), ("pct25", "final_ccc"),
         ("commenced", "final_ccc")]

ERAS = [(2018, 2019), (2020, 2021), (2022, 2023), (2024, 2026)]


def emp_quantiles(d, levels=(0.025, 0.05, 0.10, 0.25, 0.75, 0.90, 0.95, 0.975)):
    return {f"q{int(l * 1000)}": float(np.quantile(d, l)) for l in levels}


def km_survival(dur, cen, cap=None):
    cen = cen.copy()
    if cap is not None:
        cen = np.minimum(cen, cap)
    all_t = np.unique(np.concatenate([dur, cen]))
    surv, out_t, out_s = 1.0, [], []
    for d in all_t:
        risk = int((dur[dur >= d].size + cen[cen >= d].size))
        ev = int((dur == d).sum())
        if risk <= 0:
            continue
        surv *= (1 - ev / risk)
        out_t.append(d)
        out_s.append(surv)
    return np.array(out_t), np.array(out_s)


def km_quantiles(t_arr, s_arr, levels=(0.05, 0.10, 0.25, 0.75, 0.90, 0.95)):
    out = {}
    for l in levels:
        target_s = 1 - l
        idx = np.searchsorted(s_arr, target_s, side="right") - 1
        if idx < 0:
            out[f"q{int(l * 1000)}"] = float(t_arr[0])
        elif idx >= len(t_arr):
            out[f"q{int(l * 1000)}"] = float(t_arr[-1])
        else:
            out[f"q{int(l * 1000)}"] = float(t_arr[idx])
    return out


def main() -> None:
    states = pd.read_csv(SILVER / "state_machine" / "states.csv")
    states["entered"] = pd.to_datetime(states["entered"], errors="coerce")
    states = states[states["entered"] <= SNAP]

    pair_rows = {}
    for src, dst in PAIRS:
        a = states[states["state"] == src][["case_key", "entered"]].rename(columns={"entered": "a"})
        b = states[states["state"] == dst][["case_key", "entered"]].rename(columns={"entered": "b"})
        m = a.merge(b, on="case_key", how="inner")
        m = m[(m["b"] >= m["a"]) & (m["b"] - m["a"] <= pd.Timedelta(days=4000))]
        pair_rows[(src, dst)] = (m["a"].to_numpy(), m["b"].to_numpy())

    cohort = pd.read_csv(SILVER / "replay" / "golden_cohort.csv", dtype=str)
    selected = set(cohort[cohort["selected"] == "True"]["case_key"])
    clean = pd.read_csv(SILVER / "dq" / "labels_clean.csv", dtype=str)
    clean_keys = set(clean["case_key"]) | selected
    outcomes = []
    for (src, dst), (a_arr, b_arr) in pair_rows.items():
        used = states[(states["state"] == src) & (states["case_key"].isin(clean_keys))]
        for _, r in used.iterrows():
            t = r["entered"]
            key = r["case_key"]
            f = states[(states["case_key"] == key) & (states["entered"] > t)]
            if f.empty or f.iloc[0]["state"] != dst:
                continue
            actual = f.iloc[0]["entered"]
            actual_dur = (actual - t).days
            window_start = np.datetime64(t - pd.Timedelta(days=5 * 365))
            mask = (a_arr <= np.datetime64(t)) & (a_arr >= window_start)
            a, b = a_arr[mask], b_arr[mask]
            completed = b <= np.datetime64(t)
            d = (b[completed] - a[completed]) / np.timedelta64(1, "D")
            if len(d) < 10:
                continue
            year = t.year
            q = emp_quantiles(d)
            ages = (np.datetime64(t) - a[completed]) / np.timedelta64(1, "D")
            w = np.exp(-ages / 730.0)
            idx = np.argsort(d)
            ds, ws = d[idx], w[idx]
            cw = np.cumsum(ws) / ws.sum()
            q2 = {f"q{int(l * 1000)}": float(ds[min(np.searchsorted(cw, l), len(ds) - 1)]) for l in
                  (0.025, 0.05, 0.10, 0.25, 0.75, 0.90, 0.95, 0.975)}
            cen = np.where(~completed, np.minimum(
                (np.datetime64(t) - a) / np.timedelta64(1, "D"), 730.0), np.nan)
            t_arr, s_arr = km_survival(d, cen[~completed])
            q3 = km_quantiles(t_arr, s_arr) if len(t_arr) else {}
            row = {"case_key": key, "pair": f"{src}->{dst}", "snapshot_dt": t,
                   "era": year, "actual_dur": actual_dur,
                   "cdf": json.dumps([round(float(np.quantile(d, l)), 1) for l in np.arange(0.0, 1.01, 0.01)])}
            row.update({f"v0_{k}": v for k, v in q.items()})
            row.update({f"v2_{k}": v for k, v in q2.items()})
            row.update({f"v3_{k}": v for k, v in q3.items()})
            outcomes.append(row)
    frame = pd.DataFrame(outcomes)
    if frame.empty:
        print(json.dumps({"error": "no outcomes"}))
        return

    def cov_of(sub, variant, nominal):
        lo_key = f"{variant}_q{250 if nominal == '50' else (100 if nominal == '80' else 50)}"
        hi_key = f"{variant}_q{750 if nominal == '50' else (900 if nominal == '80' else 950)}"
        if lo_key not in sub.columns or hi_key not in sub.columns:
            return np.nan
        return float(((sub["actual_dur"] >= sub[lo_key]) & (sub["actual_dur"] <= sub[hi_key])).mean() * 100)

    report = {"n_outcomes": int(len(frame)), "by_era": {}}
    for era_idx, (y0, y1) in enumerate(ERAS):
        era = frame[(frame["era"] >= y0) & (frame["era"] <= y1)]
        if len(era) < 20:
            continue
        entry = {"n": int(len(era)), "median_actual": round(float(era["actual_dur"].median()), 1)}
        for nominal in ("50", "80", "90"):
            e = {"v0_empirical": round(cov_of(era, "v0", nominal), 1),
                 "v2_weighted": round(cov_of(era, "v2", nominal), 1),
                 "v3_km_capped": round(cov_of(era, "v3", nominal), 1),
                 "nominal": int(nominal)}
            if era_idx > 0:
                prev = frame[(frame["era"] >= ERAS[era_idx - 1][0]) & (frame["era"] <= ERAS[era_idx - 1][1])]
                base = {"50": (0.25, 0.75), "80": (0.10, 0.90), "90": (0.05, 0.95)}[nominal]
                if len(prev) >= 30:
                    cdfs = prev["cdf"].map(lambda s: np.array(json.loads(s)))
                    best_c, best_diff = 0.5, 1e9
                    for c in np.arange(0.0, 0.50, 0.005):
                        lo_l = max(base[0] - c, 0.0)
                        hi_l = min(base[1] + c, 1.0)
                        lo = np.array([cdf[min(int(lo_l * 100), 100)] for cdf in cdfs])
                        hi = np.array([cdf[min(int(hi_l * 100), 100)] for cdf in cdfs])
                        cov = ((prev["actual_dur"].to_numpy() >= lo) &
                               (prev["actual_dur"].to_numpy() <= hi)).mean()
                        diff = abs(cov - int(nominal) / 100)
                        if diff < best_diff:
                            best_c, best_diff = c, diff
                    lo_l = max(base[0] - best_c, 0.0)
                    hi_l = min(base[1] + best_c, 1.0)
                    cdfs_era = era["cdf"].map(lambda s: np.array(json.loads(s)))
                    lo = np.array([cdf[min(int(lo_l * 100), 100)] for cdf in cdfs_era])
                    hi = np.array([cdf[min(int(hi_l * 100), 100)] for cdf in cdfs_era])
                    e["v1_conformal"] = round(float(((era["actual_dur"].to_numpy() >= lo) &
                                                    (era["actual_dur"].to_numpy() <= hi)).mean() * 100), 1)
                    e["v1_expansion_c"] = round(float(best_c), 3)
                    e["v1_lo_level"] = round(lo_l, 3)
                    e["v1_hi_level"] = round(hi_l, 3)
            entry[f"cov{nominal}"] = e
        report["by_era"][f"{y0}-{y1}"] = entry
    frame.to_csv(OUT / "calibration_outcomes.csv", index=False)
    (OUT / "calibration_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
