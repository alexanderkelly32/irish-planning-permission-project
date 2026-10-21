"""DLR density-band analysis: refusal rates by density, and v4 calibration
per band on recent years.

- build_data provides corrected units + site area for DLR (register lacks them)
- refusal rates by density band (all decided DLR residential, 2015+)
- v4 calibration per band: scored 2024-2025 DLR rows vs observed refusal
Output: silver/validation/dlr_density_bands.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "09_devrisk" / "data" / "silver" / "validation"
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from build_8020_regime_experiment import build_data  # noqa: E402

ARTIFACT = ROOT / "05_policy" / "current" / "model_v4" / "national_residential_v4_full.joblib"
AUTH_NORM = "dunlaoghairerathdowncountycouncil"


def wilson(k, n, z=1.96):
    if n == 0:
        return None, 0.0, 1.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, max(centre - half, 0.0), min(centre + half, 1.0)


def main() -> None:
    data, _tr, _te, _y = build_data()
    norm = lambda s: "".join(c for c in str(s).lower() if c.isalnum())
    data["_an"] = data["PlanningAuthority"].map(norm)
    dlr = data[data["_an"] == AUTH_NORM].copy()
    dlr = dlr[(dlr["target_refused"].isin([0, 1]))]
    dlr["units"] = pd.to_numeric(dlr["units"], errors="coerce")
    dlr["site"] = pd.to_numeric(dlr["AreaofSite"], errors="coerce")
    dlr = dlr[dlr["units"].notna() & (dlr["units"] >= 2) & (dlr["site"].between(200, 1e6))]
    dlr["density"] = dlr["units"] / (dlr["site"] / 1e4)
    dlr["band"] = pd.cut(dlr["density"], [0, 15, 30, 45, 60, 100, 1000],
                         labels=["<15", "15-30", "30-45", "45-60", "60-100", "100+"])
    bands = {}
    for b, g in dlr.groupby("band", observed=True):
        k, n = int(g["target_refused"].sum()), int(len(g))
        p, lo, hi = wilson(k, n)
        bands[str(b)] = {"n": n, "refusal_rate": round(float(p), 4), "ci": [round(lo, 4), round(hi, 4)],
                         "median_density_uha": round(float(g["density"].median()), 1),
                         "years": [int(g["received_date_dt"].dt.year.min()), int(g["received_date_dt"].dt.year.max())]}
    # calibration on 2024-2025
    artifact = joblib.load(ARTIFACT)
    feats = artifact["feature_columns"]
    hold = dlr[dlr["received_date_dt"] >= pd.Timestamp("2024-01-01", tz="UTC")].copy()
    if len(hold) >= 30:
        hold["p"] = artifact["calibrated_base_model"].predict_proba(hold[feats])[:, 1]
        hold["p"] = artifact["isotonic_calibrator"].predict(hold["p"])
        cal = {}
        for b, g in hold.groupby("band", observed=True):
            if len(g) < 10:
                continue
            cal[str(b)] = {"n": int(len(g)), "mean_pred": round(float(g["p"].mean()), 4),
                           "obs_rate": round(float(g["target_refused"].mean()), 4),
                           "delta_pp": round((float(g["p"].mean()) - float(g["target_refused"].mean())) * 100, 2)}
    else:
        cal = {"note": "insufficient 2024-2025 DLR rows with density"}
    report = {"density_bands_all_years": bands, "v4_calibration_2024_2025": cal,
              "n_dlr_with_density": int(len(dlr))}
    (OUT / "dlr_density_bands.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print("n DLR rows with density:", len(dlr))
    for b, v in bands.items():
        print(f"{b}: n={v['n']:>5} rate={v['refusal_rate']*100:5.1f}% [{v['ci'][0]*100:.1f}, {v['ci'][1]*100:.1f}] med {v['median_density_uha']:>5.0f} u/ha")
    print("calibration 2024-2025:", json.dumps(cal, indent=1))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
