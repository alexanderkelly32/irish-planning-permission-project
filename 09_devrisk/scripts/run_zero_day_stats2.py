"""Zero-day stats part 2: ultimate-success probability + abandonment base
rate + drafting-association table + static authority/type baselines.
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
OUT = SILVER / "report" / "zero_day"
OUT.mkdir(parents=True, exist_ok=True)
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
    out = {}

    # ---- abandonment-after-refusal ----
    sites = pd.read_csv(SILVER / "sprint3" / "site_apps.csv", dtype=str)
    sites["recv"] = pd.to_datetime(sites["recv"], errors="coerce")
    sites["decision"] = sites["Decision"].fillna("").str.lower()
    refused = sites[sites["decision"].str.contains("refus")]
    obs_window = SNAP - pd.Timedelta(days=4 * 365)
    refused_obs = refused[refused["recv"] <= obs_window]
    resub = {}
    for _, r in refused_obs.iterrows():
        later = sites[(sites["site_id"] == r["site_id"]) & (sites["recv"] > r["recv"])]
        resub[r["case_key"]] = int(len(later) > 0)
    n = len(refused_obs)
    k_resub = sum(resub.values())
    lo, hi = wilson(n - k_resub, n)
    out["abandonment"] = {
        "n_refused_with_4y_observation": n,
        "n_never_resubmitted": n - k_resub,
        "abandonment_rate": round((n - k_resub) / n, 3) if n else None,
        "ci_low": round(lo, 3) if n else None, "ci_high": round(hi, 3) if n else None,
        "caveat": "same-parcel resubmission within 4 years, from KD-tree site clusters"}

    # ---- ultimate-success compound ----
    p_grant = 1 - 0.164  # median-ish refusal p from part 1 frame; used as illustration parameter
    p_resub = k_resub / n if n else 0.5
    p_convert_grid = {0: 0.0, 1: 0.017, 2: 0.056, 3: 0.187, 4: 0.249}
    rng = np.random.default_rng(7)
    rows = []
    for p_ref in (0.06, 0.12, 0.20, 0.35):
        for n_m in (1, 2, 3, 4):
            p_conv = p_convert_grid[n_m]
            ultimate = (1 - p_ref) + p_ref * p_resub * p_conv
            draws = []
            for _ in range(2000):
                pg = rng.beta(1 + (1 - p_ref) * 100, 1 + p_ref * 100)
                pr = rng.beta(1 + k_resub, 1 + (n - k_resub))
                pc = rng.beta(1 + p_conv * 200, 1 + (1 - p_conv) * 200)
                draws.append(pg + (1 - pg) * pr * pc)
            draws = np.array(draws)
            rows.append({"predicted_refusal_p": p_ref, "rescue_matches_assumed": n_m,
                         "ultimate_success_p": round(float(ultimate), 3),
                         "ci_low": round(float(np.quantile(draws, 0.025)), 3),
                         "ci_high": round(float(np.quantile(draws, 0.975)), 3),
                         "gain_over_grant_only_pp": round(float((ultimate - (1 - p_ref)) * 100), 2)})
    out["ultimate_success"] = {"method": "P(grant first) + P(refused)*P(resubmit)*P(convert|matched recommendations); intervals propagated by beta draws",
                               "grid": rows}

    # ---- drafting-association table (zero-day framing of mutation deltas) ----
    pairs = pd.read_csv(SILVER / "sprint2" / "refusal_grant_pairs.csv")
    drafts = {
        "units_reduced_vs_refused_version": {
            "stat": "resubmitted applications that reduced unit count converted more often",
            "converted": float(pairs[pairs["decision_2"] == "grant"]["units_reduced"].mean()),
            "not_converted": float(pairs[pairs["decision_2"] == "refuse"]["units_reduced"].mean())},
        "trimmed_description": {
            "stat": "resubmissions that kept descriptions similar/short converted more often",
            "converted_share_lt1.3": float((pairs[pairs["decision_2"] == "grant"]["desc_len_ratio"] <= 1.3).mean()),
            "not_converted_share_lt1.3": float((pairs[pairs["decision_2"] == "refuse"]["desc_len_ratio"] <= 1.3).mean())},
        "kept_same_route": {
            "stat": "resubmissions keeping the same application route converted more often",
            "converted": 1 - float(pairs[pairs["decision_2"] == "grant"]["type_change"].mean()),
            "not_converted": 1 - float(pairs[pairs["decision_2"] == "refuse"]["type_change"].mean())},
        "no_new_technical_language": {
            "stat": "adding new access/drainage/parking language was anti-associated with conversion",
            "converted": float(pairs[pairs["decision_2"] == "grant"]["fam_access_roads_added"].mean()),
            "not_converted": float(pairs[pairs["decision_2"] == "refuse"]["fam_access_roads_added"].mean())},
    }
    out["drafting_associations"] = drafts

    # ---- static authority/type baselines ----
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "PlanningAuthority", "DevelopmentDescription",
                                   "NumResidentialUnits", "Decision", "ReceivedDate"])
    reg = reg.drop_duplicates("case_key")
    dec = reg["Decision"].fillna("").str.lower()
    reg["y"] = dec.str.contains("refus").astype(int)
    reg = reg[dec.str.contains("refus|grant", regex=True)]
    reg["type"] = np.where(reg["DevelopmentDescription"].fillna("").str.lower()
                           .str.contains("apartment|duplex", regex=True), "apartment", "house")
    reg["recv_year"] = pd.to_datetime(reg["ReceivedDate"], utc=True, errors="coerce").dt.year
    reg = reg[reg["recv_year"] >= 2015]
    national = {}
    baselines = []
    for (auth, tp), g in reg.groupby(["PlanningAuthority", "type"]):
        k, n = int(g["y"].sum()), int(len(g))
        lo, hi = wilson(k, n)
        nat = reg[reg["type"] == tp]["y"].mean()
        baselines.append({"authority": auth, "type": tp, "n": n,
                          "refusal_rate": round(k / n, 4), "ci_low": round(lo, 4),
                          "ci_high": round(hi, 4),
                          "delta_vs_national_pp": round((k / n - nat) * 100, 2)})
    bdf = pd.DataFrame(baselines).sort_values("delta_vs_national_pp")
    bdf.to_csv(OUT / "authority_type_baselines.csv", index=False)
    out["static_baselines"] = {"n_authority_type_cells": int(len(bdf)),
                               "range_delta_pp": [round(float(bdf["delta_vs_national_pp"].min()), 2),
                                                  round(float(bdf["delta_vs_national_pp"].max()), 2)],
                               "top_5_harshest": bdf.head(5)[["authority", "type", "n", "refusal_rate", "delta_vs_national_pp"]].to_dict(orient="records"),
                               "top_5_most_permissive": bdf.tail(5)[["authority", "type", "n", "refusal_rate", "delta_vs_national_pp"]].to_dict(orient="records")}
    (OUT / "zero_day_part2_report.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str)[:4500])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
