"""Stage-2 imagery analysis: seasonal-adjusted, ring-normalised site-state features.

Input: silver/imagery/sentinel_monthly_v3.csv (all 100 sites, 2018-2026)
Produces per site-month:
  - seasonal anomaly: value - same-calendar-month site median (fitted 2019-2020
    reference years ONLY, to avoid leaking construction periods)
  - ring-relative: site - ring (surroundings control)
  - change flags: frac_chg vs baseline/prev thresholds
  - first sustained change detection (2 consecutive months above threshold,
    ring-relative) -> compare to BCMS commencement and first CCC (gate 2)

Then the three gates:
  G1 active vs inactive separation (commenced vs never, ring-relative changes)
  G2 physical-start dating vs BCMS commencement (+-90d share)
  G3 first-CCC within 12m of commencement vs early-construction imagery
Output: silver/imagery/stage2_features.csv + stage2_gates.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
SILVER = ROOT / "09_devrisk" / "data" / "silver"
IMAGERY = SILVER / "imagery"
OUT = IMAGERY


def main() -> None:
    frame = pd.read_csv(IMAGERY / "sentinel_monthly_v3.csv")
    frame["ym_dt"] = pd.to_datetime(frame["ym"] + "-01")
    frame["month"] = frame["ym_dt"].dt.month
    frame["year"] = frame["ym_dt"].dt.year
    frame = frame.sort_values(["development_id", "ym_dt"]).reset_index(drop=True)
    n_sites = int(frame["development_id"].nunique())
    n_months = int(frame["ym"].nunique())

    # seasonal reference: same-month median across 2019-2020 (pre-construction
    # for most schemes; held out of later anomalies)
    ref = frame[frame["year"].isin([2019, 2020])].groupby(
        ["development_id", "month"])[["s2_ndbi", "s2_ndvi", "s1_vh", "s1_vv"]].median()
    merged = frame.set_index(["development_id", "month"]).join(
        ref, rsuffix="_ref")
    for col in ("s2_ndbi", "s2_ndvi", "s1_vh", "s1_vv"):
        merged[f"{col}_anom"] = merged[col] - merged[f"{col}_ref"]
    merged["ndbi_ring"] = merged["s2_ndbi"] - merged["ring_ndbi"]
    merged["ndvi_ring"] = merged["s2_ndvi"] - merged["ring_ndvi"]
    merged["vh_ring"] = merged["s1_vh"] - merged["ring_vh"]
    merged = merged.reset_index()
    merged["ndbi_ring_anom"] = merged.groupby(["development_id", "month"])["ndbi_ring"].transform(
        lambda s: s - s.median())

    # labels
    cohort = pd.read_csv(IMAGERY / "feasibility_100.csv", dtype=str)
    labels = cohort[["case_key", "comm_dt", "first_ccc"]].rename(columns={"case_key": "development_id"})
    labels["comm_dt"] = pd.to_datetime(labels["comm_dt"], utc=True, errors="coerce").dt.tz_localize(None)
    labels["first_ccc"] = pd.to_datetime(labels["first_ccc"], utc=True, errors="coerce").dt.tz_localize(None)
    merged = merged.merge(labels, on="development_id", how="left")

    # G2: first sustained change (2 consecutive months, ring-relative anomaly)
    thr_ndbi = 0.03
    thr_vh = 1.0
    rows = []
    for pid, g in merged.groupby("development_id"):
        row = labels[labels["development_id"] == pid]
        if row.empty or pd.isna(row["comm_dt"].iloc[0]):
            continue
        comm = row["comm_dt"].iloc[0]
        g = g.sort_values("ym_dt").reset_index(drop=True)
        g = g.assign(sig=((g["ndbi_ring_anom"].abs() > thr_ndbi) | (g["vh_ring"].abs() > thr_vh)).astype(bool))
        g["sus"] = g["sig"] & g["sig"].shift(1).fillna(False)
        post = g[(g["ym_dt"] >= comm - pd.Timedelta(days=180)) & (g["ym_dt"] <= comm + pd.Timedelta(days=900))]
        hit = post[post["sus"]]
        if len(hit):
            rows.append({"development_id": pid, "detected": hit["ym_dt"].iloc[0],
                         "comm": comm, "delta_days": (hit["ym_dt"].iloc[0] - comm).days,
                         "pre_comm_hit": (hit["ym_dt"].iloc[0] < comm - pd.Timedelta(days=30))})
    dd = pd.DataFrame(rows)
    gates = {"n_sites": n_sites, "n_months": n_months}
    if len(dd):
        gates["G2_start_dating"] = {
            "n_detected": int(len(dd)),
            "pct_within_90d": round(float((dd["delta_days"].abs() <= 90).mean() * 100), 1),
            "median_delta_days": round(float(dd["delta_days"].median()), 1),
            "pct_pre_comm_hits": round(float(dd["pre_comm_hit"].mean() * 100), 1)}

    # G1: commenced vs never-commenced, features = ring-relative changes over
    # the series (post minus reference)
    site_feats = []
    for pid, g in merged.groupby("development_id"):
        g = g.sort_values("ym_dt")
        base = g[g["year"].isin([2019, 2020])]
        post = g[g["year"] >= 2021]
        row = labels[labels["development_id"] == pid]
        if len(base) < 8 or len(post) < 8:
            continue
        site_feats.append({
            "development_id": pid,
            "d_ndbi_ring": float(post["ndbi_ring"].mean() - base["ndbi_ring"].mean()),
            "d_ndvi_ring": float(post["ndvi_ring"].mean() - base["ndvi_ring"].mean()),
            "d_vh_ring": float(post["vh_ring"].mean() - base["vh_ring"].mean()),
            "d_ndbi_anom": float(post["s2_ndbi_anom"].mean() - base["s2_ndbi_anom"].mean()),
            "d_vh_anom": float(post["s1_vh_anom"].mean() - base["s1_vh_anom"].mean()),
            "max_frac_chg_ndbi": float(post["frac_chg_ndbi_base"].max()),
            "max_frac_chg_vh": float(post["frac_chg_vh_base"].max()),
            "commenced": int(pd.notna(row["comm_dt"].iloc[0])) if len(row) else 0})
    sf = pd.DataFrame(site_feats)
    sf.to_csv(OUT / "stage2_site_features.csv", index=False)
    if len(sf) == 0:
        (OUT / "stage2_gates.json").write_text(json.dumps(gates, indent=1, default=str), encoding="utf-8")
        print(json.dumps(gates, indent=1))
        return
    if sf["commenced"].nunique() == 2 and sf["commenced"].sum() >= 8:
        X = sf[["d_ndbi_ring", "d_ndvi_ring", "d_vh_ring", "d_ndbi_anom", "d_vh_anom",
                "max_frac_chg_ndbi", "max_frac_chg_vh"]].fillna(0)
        m = GradientBoostingClassifier(n_estimators=200, max_depth=2, random_state=7)
        m.fit(X, sf["commenced"])
        gates["G1_active_vs_inactive"] = {
            "n": int(len(sf)), "n_commenced": int(sf["commenced"].sum()),
            "auc_insample": round(float(roc_auc_score(sf["commenced"], m.predict_proba(X)[:, 1])), 3),
            "mean_d_ndbi_ring_commenced": round(float(sf[sf["commenced"] == 1]["d_ndbi_ring"].mean()), 4),
            "mean_d_ndbi_ring_not": round(float(sf[sf["commenced"] == 0]["d_ndbi_ring"].mean()), 4),
            "mean_d_vh_ring_commenced": round(float(sf[sf["commenced"] == 1]["d_vh_ring"].mean()), 2),
            "mean_d_vh_ring_not": round(float(sf[sf["commenced"] == 0]["d_vh_ring"].mean()), 2)}

    # G3: early-construction imagery (first 6m post-commencement) vs CCC<=12m
    rows3 = []
    for pid, g in merged.groupby("development_id"):
        row = labels[labels["development_id"] == pid]
        if row.empty or pd.isna(row["comm_dt"].iloc[0]) or pd.isna(row["first_ccc"].iloc[0]):
            continue
        comm = row["comm_dt"].iloc[0]
        ccc0 = row["first_ccc"].iloc[0]
        early = g[(g["ym_dt"] >= comm) & (g["ym_dt"] <= comm + pd.Timedelta(days=180))]
        if len(early) < 3:
            continue
        rows3.append({"development_id": pid,
                      "early_d_vh_ring": float(early["vh_ring"].iloc[-1] - early["vh_ring"].iloc[0]),
                      "early_d_ndbi_ring": float(early["ndbi_ring"].iloc[-1] - early["ndbi_ring"].iloc[0]),
                      "early_frac_chg_max": float(early["frac_chg_ndbi_prev"].max()),
                      "ccc_within_12m": int((ccc0 - comm).days <= 365)})
    r3 = pd.DataFrame(rows3)
    if len(r3) >= 10 and r3["ccc_within_12m"].nunique() == 2:
        X3 = r3[["early_d_vh_ring", "early_d_ndbi_ring", "early_frac_chg_max"]].fillna(0)
        m3 = GradientBoostingClassifier(n_estimators=200, max_depth=2, random_state=7)
        m3.fit(X3, r3["ccc_within_12m"])
        gates["G3_ccc_12m"] = {
            "n": int(len(r3)), "prevalence": round(float(r3["ccc_within_12m"].mean()), 3),
            "auc_insample": round(float(roc_auc_score(r3["ccc_within_12m"], m3.predict_proba(X3)[:, 1])), 3)}
    (OUT / "stage2_gates.json").write_text(json.dumps(gates, indent=1, default=str), encoding="utf-8")
    merged.to_csv(OUT / "stage2_features.csv", index=False)
    print(json.dumps(gates, indent=1))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
