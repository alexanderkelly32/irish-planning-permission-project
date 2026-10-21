"""Confirmatory pass part 2: 2D cell stability at n thresholds; compound
population matching (P(resubmit) re-derived on the Sprint 2 pair cohort);
fresh-era re-runs of mutation univariate deltas + rescue plan + clean/path
products; batch summary table with survival verdicts.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "report" / "confirmatory"
SNAP = pd.Timestamp("2026-10-01")


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * np.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return max(centre - margin, 0.0), min(centre + margin, 1.0)


def main() -> None:
    out = {"cells_stability": {}, "compound_population_match": {}, "batch": {}}

    # ---- 1b: 2D cell stability at n thresholds ----
    sub = pd.read_csv(SILVER / "report" / "zero_day" / "reference_class_test.csv")
    sub = sub.dropna(subset=["nn_refusal_rate"])
    sub["p_decile"] = pd.qcut(sub["p_ref"], 8, labels=False, duplicates="drop")
    sub["type"] = np.where(sub["f_apartment"] == 1, "apartment", "house")
    sub["auth_group"] = sub["PlanningAuthority"].map(
        lambda a: "Dublin" if "Dublin" in a or "Dun Laoghaire" in a or "Fingal" in a or "South Dublin" in a
        else ("Cork" if "Cork" in a else ("large" if a in
              ("Kildare County Council", "Meath County Council", "Wicklow County Council",
               "Galway City Council", "Galway County Council", "Limerick County Council",
               "Waterford City and County Council") else "other")))
    for n_thresh in (15, 20, 25, 50):
        cells = []
        for (dec, ag, tp), g in sub.groupby(["p_decile", "auth_group", "type"], observed=True):
            if len(g) < n_thresh:
                continue
            k, n = int(g["y"].sum()), int(len(g))
            global_rate = sub[sub["p_decile"] == dec]["y"].mean()
            cells.append({"p_decile": int(dec), "auth_group": ag, "type": tp, "n": n,
                          "cell_rate": round(k / n, 4),
                          "delta_vs_decile_pp": round((k / n - global_rate) * 100, 2)})
        cdf = pd.DataFrame(cells)
        out["cells_stability"][f"n>={n_thresh}"] = {
            "n_cells": int(len(cdf)),
            "max_abs_delta_pp": round(float(cdf["delta_vs_decile_pp"].abs().max()), 2) if len(cdf) else None,
            "sd_delta_pp": round(float(cdf["delta_vs_decile_pp"].std()), 2) if len(cdf) else None,
            "dublin_apartment_low_decile_median_delta_pp": round(
                float(cdf[(cdf["auth_group"] == "Dublin") & (cdf["type"] == "apartment") &
                          (cdf["p_decile"] <= 2)]["delta_vs_decile_pp"].median()), 2)
            if len(cdf[(cdf["auth_group"] == "Dublin") & (cdf["type"] == "apartment") & (cdf["p_decile"] <= 2)]) else None,
        }

    # ---- 1c: compound population match ----
    # P(resubmit) re-derived on the Sprint 2 cohort (all-size sites, same
    # 150m KD-tree clustering used for the rescue pairs)
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "PlanningAuthority", "ITMEasting", "ITMNorthing",
                                   "ReceivedDate", "Decision"])
    reg = reg.drop_duplicates("case_key")
    reg = reg.dropna(subset=["ITMEasting", "ITMNorthing", "ReceivedDate"])
    reg["recv"] = pd.to_datetime(reg["ReceivedDate"], utc=True, errors="coerce").dt.tz_localize(None)
    dec = reg["Decision"].fillna("").str.lower()
    reg = reg[dec.str.contains("refus|grant", regex=True)].dropna(subset=["recv"])
    reg = reg.sort_values("recv")
    rows = []
    for authority, g in reg.groupby("PlanningAuthority"):
        if len(g) < 2:
            continue
        coords = g[["ITMEasting", "ITMNorthing"]].to_numpy()
        tree = cKDTree(coords)
        parent = list(range(len(g)))
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
        for a, b in tree.query_pairs(r=150.0, output_type="ndarray"):
            union(int(a), int(b))
        g = g.copy().reset_index(drop=True)
        g["site_id"] = authority + "|" + pd.Series([find(i) for i in range(len(g))]).astype(str)
        rows.append(g)
    sites = pd.concat(rows, ignore_index=True)
    sites["dec_l"] = sites["Decision"].fillna("").str.lower()
    refused = sites[sites["dec_l"].str.contains("refus", regex=True)].copy()
    refused["recv"] = pd.to_datetime(refused["ReceivedDate"], utc=True, errors="coerce").dt.tz_localize(None)
    refused_obs = refused[refused["recv"] <= SNAP - pd.Timedelta(days=4 * 365)]
    resub = []
    for _, r in refused_obs.iterrows():
        later = sites[(sites["site_id"] == r["site_id"]) & (sites["recv"] > r["recv"])]
        resub.append(int(len(later) > 0))
    n_all, k_all = len(resub), sum(resub)
    lo, hi = wilson(n_all - k_all, n_all)
    out["compound_population_match"] = {
        "sprint2_cohort_abandonment_rate": round((n_all - k_all) / n_all, 3) if n_all else None,
        "ci": [round(lo, 3), round(hi, 3)] if n_all else None,
        "n_refused": n_all,
        "sprint3_cohort_abandonment_rate": 0.292,
        "verdict": "matched" if abs((n_all - k_all) / n_all - 0.292) < 0.03 else "mismatched - use sprint2-cohort rate for the compound",
    }

    # ---- fresh-era re-runs ----
    pairs = pd.read_csv(SILVER / "sprint2" / "refusal_grant_pairs.csv")
    tr_p = pairs[pairs["year_1"] < 2019]
    te_p = pairs[pairs["year_1"].between(2019, 2020)]
    out["batch"]["mutation_univariate_fresh_era"] = {
        "n_train": int(len(tr_p)), "n_test": int(len(te_p)),
        "units_reduced_grant_minus_refuse": round(float(
            te_p[te_p["decision_2"] == "grant"]["units_reduced"].mean() -
            te_p[te_p["decision_2"] == "refuse"]["units_reduced"].mean()), 3) if len(te_p) > 50 else None,
        "desc_ratio_grant": round(float(te_p[te_p["decision_2"] == "grant"]["desc_len_ratio"].mean()), 3) if len(te_p) > 50 else None,
        "desc_ratio_refuse": round(float(te_p[te_p["decision_2"] == "refuse"]["desc_len_ratio"].mean()), 3) if len(te_p) > 50 else None,
    }
    # rescue on fresh era
    if len(tr_p) >= 100 and len(te_p) >= 50:
        med_u = tr_p[tr_p["decision_2"] == "grant"]["units_2"].median()
        te_p = te_p.copy()
        te_p["r1"] = (te_p["units_reduced"] == 1) | (te_p["units_2"].fillna(0) <= med_u)
        te_p["r2"] = (te_p["type_change"] == 0)
        te_p["r3"] = (te_p["desc_len_ratio"] <= 1.3)
        te_p["r4"] = (te_p["fam_access_roads_added"] + te_p["fam_drainage_uisce_added"] +
                      te_p["fam_parking_added"] + te_p["fam_height_storeys_added"] +
                      te_p["fam_ecology_added"]) == 0
        te_p["n_m"] = te_p[["r1", "r2", "r3", "r4"]].sum(axis=1)
        rescue_fresh = {str(k): round(float(sub["decision_2"].map({"grant": 1, "refuse": 0}).mean()), 3)
                        for k, sub in te_p.groupby("n_m")}
        out["batch"]["rescue_fresh_era"] = rescue_fresh

    (OUT / "confirmatory_part2.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str)[:4500])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
