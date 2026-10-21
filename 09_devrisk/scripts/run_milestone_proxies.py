"""Runner: milestone proxy table from BCMS cert fields (FSC/DAC/completion due).

For confirmed-BCMS-linked schemes: fire-safety cert number on the commencement
notice, FSC/DAC on the completion cert, and completion-cert due date. These
are observable administrative milestones - proxies for 'progressed to
certification', not physical completion.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

if __name__ == "__main__":
    links = pd.read_csv(settings.SILVER_DIR / "bcms_links_all_granted.csv")
    links = links[links["confidence_band"] == "confirmed"]
    bronze = pd.read_parquet(
        settings.BRONZE_DIR / "bcms_bronze.parquet",
        columns=["IDs", "row_hash", "CN_FSC_Number", "CN_DAC_Number", "CCC_FSC", "CCC_DAC", "CCC_Due_date", "CCC_Date_Validated", "CCC_Units_Completed"],
    )
    bronze["bcms_event_id"] = bronze["IDs"].astype(str) + "__" + bronze["row_hash"].str.slice(0, 12)
    merged = links.merge(bronze, on="bcms_event_id", how="inner", suffixes=("", "_bcms"))

    def _has(series: pd.Series) -> pd.Series:
        return series.fillna("").astype(str).str.strip().ne("")

    by_scheme = merged.groupby("scheme_id").agg(
        fsc_on_notice=("CN_FSC_Number", lambda s: int(_has(s).any())),
        dac_on_notice=("CN_DAC_Number", lambda s: int(_has(s).any())),
        ccc_fsc=("CCC_FSC", lambda s: int(_has(s).any())),
        ccc_dac=("CCC_DAC", lambda s: int(_has(s).any())),
        ccc_due_date=("CCC_Due_date", lambda s: pd.to_datetime(s, utc=True, errors="coerce").min()),
        ccc_validated_date=("CCC_Date_Validated", lambda s: pd.to_datetime(s, utc=True, errors="coerce").min()),
        ccc_units=("CCC_Units_Completed", lambda s: pd.to_numeric(s, errors="coerce").max()),
    ).reset_index()

    by_scheme.to_csv(settings.SILVER_DIR / "milestone_proxies.csv", index=False)
    summary = {
        "linked_schemes": int(len(by_scheme)),
        "fsc_on_notice": int(by_scheme["fsc_on_notice"].sum()),
        "dac_on_notice": int(by_scheme["dac_on_notice"].sum()),
        "ccc_fsc": int(by_scheme["ccc_fsc"].sum()),
        "ccc_dac": int(by_scheme["ccc_dac"].sum()),
        "ccc_due_date_present": int(by_scheme["ccc_due_date"].notna().sum()),
        "note": "administrative certification milestones; proxies only, not physical completion",
    }
    out = settings.SILVER_DIR / "milestone_proxies_summary.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
