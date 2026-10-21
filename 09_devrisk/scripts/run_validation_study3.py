"""Validation Study 3: housing-supply backtest.

Predicted vs actual completions for schemes granted 2019-2021:
  predicted first-CCC = grant_date + predicted_commencement + 403d completion
  predicted_commencement = authority median grant->commencement (fitted
  pre-2019 only) - a time-safe chain of the promoted timing models.
  Baselines: constant median grant->CCC (pre-2019), authority median (pre-2019).
  Actuals: first CCC from ccc_blocks; units from register + corrected units.

Metrics: scheme-level MAE; units-weighted predicted vs actual completions
by year (2020-2024), national and by authority.
Output: silver/validation/study3_supply.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SILVER = ROOT / "09_devrisk" / "data" / "silver"
OUT = SILVER / "validation"
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / "09_devrisk"))
from devrisk import settings  # noqa: E402

TRAIN_CUT = pd.Timestamp("2019-01-01")
BACKTEST_YEARS = (2019, 2020, 2021)
COMPLETION_DAYS = 403.0


def main() -> None:
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "PlanningAuthority", "NumResidentialUnits", "GrantDate"])
    reg = reg.drop_duplicates("case_key")
    reg["grant"] = pd.to_datetime(reg["GrantDate"], utc=True, errors="coerce").dt.tz_localize(None)
    reg["units"] = pd.to_numeric(reg["NumResidentialUnits"], errors="coerce")
    # corrected units
    corrected = pd.read_csv(ROOT / "02_development" / "current" / "ground_source_units_corrected.csv", low_memory=False)
    norm = lambda s: "".join(c for c in str(s).lower() if c.isalnum())
    cmap = {norm(k): v for k, v in zip(corrected["case_key"].astype(str),
                                       pd.to_numeric(corrected["units_corrected"], errors="coerce")) if pd.notna(v)}
    reg["units"] = reg["units"].fillna(reg["case_key"].map(lambda k: cmap.get(norm(k))))

    links = pd.read_csv(SILVER / "bcms_links_all_granted.csv", dtype=str)
    links["comm"] = pd.to_datetime(links["commencement_date"], utc=True, errors="coerce").dt.tz_localize(None)
    comm = (links.dropna(subset=["comm"]).groupby("scheme_id")["comm"].min()
            .rename("actual_comm").reset_index().rename(columns={"scheme_id": "case_key"}))
    ccc = pd.read_csv(SILVER / "ccc_blocks.csv", dtype=str)
    ccc["first_ccc"] = pd.to_datetime(ccc["first_ccc"], utc=True, errors="coerce").dt.tz_localize(None)
    ccc1 = (ccc.dropna(subset=["first_ccc"]).groupby("scheme_id")["first_ccc"].min()
            .rename("actual_ccc").reset_index().rename(columns={"scheme_id": "case_key"}))

    cohort = reg[reg["grant"].dt.year.isin(BACKTEST_YEARS) & reg["units"].notna() & (reg["units"] >= 5)].copy()
    cohort = cohort.merge(comm, on="case_key", how="left").merge(ccc1, on="case_key", how="left")
    n_granted = int(len(cohort))
    cohort = cohort.dropna(subset=["actual_ccc"])
    base = reg.merge(comm, on="case_key", how="left").merge(ccc1, on="case_key", how="left")
    base["g2c"] = (base["actual_comm"] - base["grant"]).dt.days
    base["g2f"] = (base["actual_ccc"] - base["grant"]).dt.days
    rows = []
    for y in BACKTEST_YEARS:
        fit = base[(base["grant"].dt.year < y) & (base["grant"].dt.year >= 2008)]
        const_med = float(fit["g2f"].median()) if fit["g2f"].notna().any() else 700.0
        global_g2c = float(fit["g2c"].median()) if fit["g2c"].notna().any() else 433.0
        auth_g2c = {a: float(g["g2c"].median()) for a, g in fit.dropna(subset=["g2c"]).groupby("PlanningAuthority") if len(g) >= 10}
        auth_g2f = {a: float(g["g2f"].median()) for a, g in fit.dropna(subset=["g2f"]).groupby("PlanningAuthority") if len(g) >= 10}
        sub = cohort[cohort["grant"].dt.year == y].copy()
        sub["pred_const"] = sub["grant"] + pd.to_timedelta(const_med, unit="D")
        sub["pred_auth"] = sub.apply(lambda r: r["grant"] + pd.to_timedelta(
            auth_g2f.get(r["PlanningAuthority"], const_med), unit="D"), axis=1)
        sub["pred_chain"] = sub.apply(lambda r: r["grant"] + pd.to_timedelta(
            auth_g2c.get(r["PlanningAuthority"], global_g2c) + COMPLETION_DAYS, unit="D"), axis=1)
        rows.append(sub)
    cohort = pd.concat(rows, ignore_index=True)
    errs = {name: float(np.median((cohort[f"pred_{name}"] - cohort["actual_ccc"]).dt.days.abs()))
            for name in ("const", "auth", "chain")}
    report = {"n_granted_with_units": n_granted, "n_schemes_with_first_ccc": int(len(cohort)),
              "n_units_total": round(float(cohort["units"].sum())),
              "grant_years": BACKTEST_YEARS,
              "actuals_source": "first CCC (ccc_blocks), commencement (bcms_links)",
              "chain": "grant + authority median commencement (expanding-window fit, n>=10 else global) + 403d completion",
              "median_abs_error_days": errs,
              "completion_constant": COMPLETION_DAYS,
              "coverage_note": f"linked cohort only; {int(comm['case_key'].nunique())} schemes with commencement, {int(ccc1['case_key'].nunique())} with first CCC",
              "censoring_note": "cohort restricted to schemes with an observed first CCC by 2026 - slow completers of 2021 grants may be missing, understating actual units in 2023-2024"}
    # units-weighted annual backtest
    rows = []
    for name in ("const", "auth", "chain"):
        pred = cohort[["pred_" + name, "units"]].rename(columns={"pred_" + name: "dt"})
        act = cohort[["actual_ccc", "units"]].rename(columns={"actual_ccc": "dt"})
        for y in range(2020, 2025):
            p = pred[pred["dt"].dt.year == y]["units"].sum()
            a = act[act["dt"].dt.year == y]["units"].sum()
            rows.append({"model": name, "year": y, "predicted_units": float(p), "actual_units": float(a)})
    ann = pd.DataFrame(rows)
    report["annual_units"] = {m: ann[ann["model"] == m][["year", "predicted_units", "actual_units"]]
                              .to_dict(orient="records") for m in ("const", "auth", "chain")}
    # per-authority error (chain vs const)
    per_auth = []
    for auth, g in cohort.groupby("PlanningAuthority"):
        if len(g) >= 5:
            per_auth.append({"authority": auth, "n": int(len(g)),
                             "chain_mae_days": float(np.median((g["pred_chain"] - g["actual_ccc"]).dt.days.abs())),
                             "const_mae_days": float(np.median((g["pred_const"] - g["actual_ccc"]).dt.days.abs()))})
    report["by_authority"] = sorted(per_auth, key=lambda r: -r["n"])
    (OUT / "study3_supply.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"n_schemes": report["n_schemes_with_first_ccc"], "median_abs_error_days": errs}, indent=1))
    for m in ("const", "chain"):
        print(m, json.dumps(report["annual_units"][m]))
    print("saved ->", OUT / "study3_supply.json")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
