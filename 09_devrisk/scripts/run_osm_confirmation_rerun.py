"""Runner: OSM-confirmation rerun with the per-estate inventories.

Builds estate token inventories from the Overpass per-estate files
(734 estates with addresses), applies the chronology filter + OSM
confirmation to the 60k pending rows, promotes the confirmed subset.
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
from run_phase_ppr_linking import tokens  # noqa: E402

if __name__ == "__main__":
    osm_dir = settings.RAW_DIR / "osm_estates"
    inventory: dict[str, set[str]] = {}
    for osm_file in osm_dir.glob("*.geojson"):
        payload = json.loads(osm_file.read_text(encoding="utf-8"))
        token_set: set[str] = set()
        for element in payload.get("elements", []):
            tag_map = element.get("tags", {})
            text = f"{tag_map.get('addr:street', '')} {tag_map.get('addr:place', '')} {tag_map.get('name', '')}"
            token_set |= tokens(text)
        appno = osm_file.stem
        inventory[appno] = token_set

    verified = pd.read_csv(settings.SILVER_DIR / "scheme_sales_verified.csv", low_memory=False)
    verified["scheme_id"] = verified["scheme_id"].astype(str)
    pending = verified[verified["verification_status"].isin(["pending", "promoted_band"])].copy()
    pending["sale_dt"] = pd.to_datetime(pending["sale_date"], utc=True, errors="coerce")
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    grant_map = dict(zip(cohort["case_key"].astype(str), pd.to_datetime(cohort["grant_date_dt"], utc=True, errors="coerce")))
    pending["days_after_grant"] = (pending["sale_dt"] - pending["scheme_id"].map(grant_map)).dt.days
    pending["appno"] = pending["scheme_id"].str.split("__").str[1]

    chronology_ok = pending["days_after_grant"].between(0, 1826)

    def osm_confirm(row: pd.Series) -> bool:
        token_set = inventory.get(str(row["appno"]), set())
        if not token_set:
            return False
        return len(tokens(str(row["address"])) & token_set) >= 2

    pending["osm_confirmed"] = pending.apply(osm_confirm, axis=1)
    promoted = pending[chronology_ok & pending["osm_confirmed"]].copy()

    report = {
        "estates_with_inventory": len(inventory),
        "pending_rows": int(len(pending)),
        "chronology_ok": int(chronology_ok.sum()),
        "osm_confirmed_rows": int(pending["osm_confirmed"].sum()),
        "promoted_rows": int(len(promoted)),
        "promoted_schemes": int(promoted["scheme_id"].nunique()) if len(promoted) else 0,
    }
    promoted.to_csv(settings.SILVER_DIR / "promoted_v3_osm_rows.csv", index=False)
    out = settings.SILVER_DIR / "pull_verification_v3_osm.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
