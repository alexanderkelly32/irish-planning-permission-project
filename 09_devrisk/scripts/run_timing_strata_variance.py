"""Runner: strata-variance decomposition for commencement + sale timing.

Where is the timing variance, and which strata carry it? Reports per-stratum
80% interval width + coverage + n. Also checks how much sale variance is
AHB/bulk (non-eligible) sales vs build-to-sell.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

if __name__ == "__main__":
    report: dict = {}

    # ---- commencement strata ----
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    frame = labels.merge(register[["case_key", "PlanningAuthority", "GrantDate", "DevelopmentDescription",
                                   "NumResidentialUnits"]], on="case_key", how="inner")
    frame["grant_dt"] = pd.to_datetime(frame["GrantDate"], utc=True, errors="coerce")
    frame["activation"] = pd.to_numeric(frame["activation_days"], errors="coerce").clip(lower=0)
    comm = frame[frame["activation_linked"].astype(bool)].dropna(subset=["activation", "grant_dt"]).copy()
    comm["era"] = np.where(comm["grant_dt"] < pd.Timestamp("2020-01-01", tz="UTC"), "pre2020",
                           np.where(comm["grant_dt"] < pd.Timestamp("2022-01-01", tz="UTC"), "2020-21", "2022+"))
    units = pd.to_numeric(comm["NumResidentialUnits"], errors="coerce")
    comm["band"] = pd.cut(units, bins=[0, 29, 99, np.inf], labels=["10-29", "30-99", "100+"])
    description = comm["DevelopmentDescription"].fillna("")
    comm["type"] = np.where(description.str.contains("apartment|duplex", case=False, regex=True), "apartments",
                            np.where(description.str.contains(r"\bhouse", case=False, regex=True), "houses", "other"))
    comm["auth_group"] = np.where(comm["PlanningAuthority"].str.contains("Dublin|Dun Laoghaire|Fingal|South Dublin", case=False), "dublin", "other")

    def strata_rows(data: pd.DataFrame, keys: list[str]) -> list[dict]:
        rows = []
        for key in keys:
            for name, part in data.groupby(key, dropna=False):
                if len(part) < 20:
                    continue
                lo, hi = np.quantile(part["activation"], [0.1, 0.9])
                rows.append({
                    "stratum": f"{key}={name}",
                    "n": int(len(part)),
                    "median_days": round(float(part["activation"].median()), 0),
                    "interval_80_width_days": round(float(hi - lo), 0),
                    "empirical_coverage_80": round(float(np.mean(part["activation"].between(lo, hi))), 3),
                })
        return rows

    comm_strata = strata_rows(comm, ["era", "band", "type", "auth_group", "PlanningAuthority"])
    comm_strata.sort(key=lambda r: r["interval_80_width_days"])
    report["commencement_strata"] = {
        "n_schemes": int(len(comm)),
        "tightest_8": comm_strata[:8],
        "widest_8": comm_strata[-8:],
        "interaction_era_band": strata_rows(comm.assign(combo=comm["era"] + " | " + comm["band"].astype(str) + " | " + comm["type"].astype(str)), ["combo"])[:12],
    }

    # ---- sale: AHB/eligible split ----
    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv")
    sold = exit_labels[exit_labels["sales_linked"] > 0].copy()
    report["sale_eligibility"] = {
        "sold_schemes": int(len(sold)),
        "eligible_build_to_sell": int(sold["sales_eligible"].sum()),
        "excluded_ahb_btr": int((~sold["sales_eligible"]).sum()),
    }
    eligible = sold[sold["sales_eligible"]]
    report["sale_strata"] = {
        "eligible_80pct_width_days": round(float(np.nanquantile(
            pd.to_numeric(eligible["time_to_first_sale_from_grant_days"], errors="coerce"), 0.9)
            - np.nanquantile(pd.to_numeric(eligible["time_to_first_sale_from_grant_days"], errors="coerce"), 0.1)), 0),
        "eligible_n": int(len(eligible)),
        "all_80pct_width_days": round(float(np.nanquantile(
            pd.to_numeric(sold["time_to_first_sale_from_grant_days"], errors="coerce"), 0.9)
            - np.nanquantile(pd.to_numeric(sold["time_to_first_sale_from_grant_days"], errors="coerce"), 0.1)), 0),
    }

    out = settings.SILVER_DIR / "timing_strata_variance.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
