"""Preliminary gates on the 41-site monthly Sentinel data.

Gate 1: does imagery separate commenced from never-commenced sites?
Gate 2: first sustained change vs BCMS start date (+-90d share).
Gate 3: imagery features at construction onset vs CCC within 12m.
Small n - preliminary only; the full 100-site cohort follows.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "imagery"


def main() -> None:
    frame = pd.read_csv(OUT / "sentinel_monthly.csv")
    frame["ym_dt"] = pd.to_datetime(frame["ym"] + "-01")
    frame = frame.sort_values(["development_id", "ym_dt"])
    cohort = pd.read_csv(OUT / "feasibility_50.csv", dtype=str)
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "GrantDate"])
    reg = reg.drop_duplicates("case_key")
    reg["grant"] = pd.to_datetime(reg["GrantDate"], utc=True, errors="coerce").dt.tz_localize(None)
    labels = pd.read_csv(SILVER / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    labels = labels[labels["activation_linked"].astype(str).str.lower() == "true"]
    labels = labels.merge(reg, on="case_key", how="left")
    labels["comm"] = labels["grant"] + pd.to_timedelta(pd.to_numeric(labels["activation_days"], errors="coerce"), unit="D")
    ccc = pd.read_csv(SILVER / "ccc_blocks.csv", dtype=str)
    ccc["first_ccc"] = pd.to_datetime(ccc["first_ccc"], utc=True, errors="coerce").dt.tz_localize(None)
    report = {"n_sites": int(frame["development_id"].nunique())}

    # per-site imagery features relative to pre-construction (first 12 months)
    site_feats = []
    for pid, g in frame.groupby("development_id"):
        g = g.sort_values("ym_dt")
        base = g.head(12)
        post = g.iloc[12:]
        if len(base) < 6 or len(post) < 6:
            continue
        comm = labels.loc[labels["case_key"] == pid, "comm"]
        first_ccc = ccc.loc[ccc["scheme_id"] == pid, "first_ccc"].min()
        site_feats.append({
            "development_id": pid,
            "d_ndbi": float(post["s2_ndbi"].mean() - base["s2_ndbi"].mean()),
            "d_ndvi": float(post["s2_ndvi"].mean() - base["s2_ndvi"].mean()),
            "d_vh": float(post["s1_vh"].mean() - base["s1_vh"].mean()),
            "d_vv": float(post["s1_vv"].mean() - base["s1_vv"].mean()),
            "ndbi_std": float(post["s2_ndbi"].std()),
            "commenced": int(len(comm) > 0 and pd.notna(comm.iloc[0])),
            "comm_dt": comm.iloc[0] if len(comm) > 0 and pd.notna(comm.iloc[0]) else pd.NaT,
            "first_ccc": first_ccc,
        })
    sf = pd.DataFrame(site_feats)
    sf.to_csv(OUT / "site_imagery_features_prelim.csv", index=False)
    report["n_sites_with_features"] = int(len(sf))

    # Gate 1: commenced vs not
    if sf["commenced"].nunique() == 2 and sf["commenced"].sum() >= 8:
        X = sf[["d_ndbi", "d_ndvi", "d_vh", "d_vv", "ndbi_std"]].fillna(0)
        m = GradientBoostingClassifier(n_estimators=200, max_depth=2, random_state=7)
        m.fit(X, sf["commenced"])
        report["gate1_active_vs_inactive"] = {
            "n_commenced": int(sf["commenced"].sum()),
            "auc_insample": round(float(roc_auc_score(sf["commenced"], m.predict_proba(X)[:, 1])), 3),
            "mean_d_ndbi_commenced": round(float(sf[sf["commenced"] == 1]["d_ndbi"].mean()), 3),
            "mean_d_ndbi_not": round(float(sf[sf["commenced"] == 0]["d_ndbi"].mean()), 3),
            "mean_d_vh_commenced": round(float(sf[sf["commenced"] == 1]["d_vh"].mean()), 2),
            "mean_d_vh_not": round(float(sf[sf["commenced"] == 0]["d_vh"].mean()), 2),
        }

    # Gate 2: first sustained change vs BCMS start
    dates = []
    for pid, g in frame.groupby("development_id"):
        row = sf[sf["development_id"] == pid]
        if row.empty or pd.isna(row["comm_dt"].iloc[0]):
            continue
        comm = row["comm_dt"].iloc[0]
        g = g.sort_values("ym_dt")
        g["d3_ndbi"] = g["s2_ndbi"].diff(3)
        g["d3_vh"] = g["s1_vh"].diff(3)
        hit = None
        for i in range(6, len(g) - 1):
            if (abs(g["d3_ndbi"].iloc[i]) > 0.03 or abs(g["d3_vh"].iloc[i]) > 1.0) and \
               (abs(g["d3_ndbi"].iloc[i + 1]) > 0.03 or abs(g["d3_vh"].iloc[i + 1]) > 1.0):
                hit = g["ym_dt"].iloc[i]
                break
        if hit is not None:
            dates.append({"development_id": pid, "detected": hit,
                          "comm": comm, "delta_days": (hit - comm).days})
    dd = pd.DataFrame(dates)
    if len(dd):
        report["gate2_start_dating"] = {
            "n": int(len(dd)),
            "pct_within_90d": round(float((dd["delta_days"].abs() <= 90).mean() * 100), 1),
            "median_delta_days": round(float(dd["delta_days"].median()), 1),
            "pct_detected_at_all": round(float(len(dd) / max(sf["commenced"].sum(), 1) * 100), 1),
        }

    # Gate 3: first 6m of construction imagery -> CCC within 12m of comm
    rows3 = []
    for pid, g in frame.groupby("development_id"):
        row = sf[sf["development_id"] == pid]
        if row.empty or pd.isna(row["comm_dt"].iloc[0]) or pd.isna(row["first_ccc"].iloc[0]):
            continue
        comm = row["comm_dt"].iloc[0]
        ccc0 = row["first_ccc"].iloc[0]
        early = g[(g["ym_dt"] >= comm) & (g["ym_dt"] <= comm + pd.Timedelta(days=180))]
        if len(early) < 3:
            continue
        rows3.append({"development_id": pid,
                      "early_d_vh": float(early["s1_vh"].iloc[-1] - early["s1_vh"].iloc[0]),
                      "early_d_ndbi": float(early["s2_ndbi"].iloc[-1] - early["s2_ndbi"].iloc[0]),
                      "ccc_within_12m": int((ccc0 - comm).days <= 365)})
    r3 = pd.DataFrame(rows3)
    if len(r3) >= 10 and r3["ccc_within_12m"].nunique() == 2:
        X3 = r3[["early_d_vh", "early_d_ndbi"]].fillna(0)
        m3 = GradientBoostingClassifier(n_estimators=200, max_depth=2, random_state=7)
        m3.fit(X3, r3["ccc_within_12m"])
        report["gate3_ccc_12m"] = {
            "n": int(len(r3)), "prevalence": round(float(r3["ccc_within_12m"].mean()), 3),
            "auc_insample": round(float(roc_auc_score(r3["ccc_within_12m"], m3.predict_proba(X3)[:, 1])), 3)}
    (OUT / "prelim_gates.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
