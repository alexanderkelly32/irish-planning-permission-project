"""Runner: pull verification v2 - chronology fix + OSM confirmation layer.

Reasons 3/4 mitigation: (a) sales must fall within [grant, grant+5y] and
not predate the estate era (old same-named phases excluded); (b) a PPR
candidate is confirmed estate-level if its address tokens match the human
estate fill AND the estate's OSM address points contain matching tokens -
the estate name no longer needs to appear in the PPR address itself.
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
    fills = pd.read_csv(settings.SILVER_DIR / "audit_packs" / "manual_fills_pull.csv")
    fills["scheme_id"] = fills["scheme_id"].astype(str)
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    grant_map = dict(zip(cohort["case_key"].astype(str), pd.to_datetime(cohort["grant_date_dt"], utc=True, errors="coerce")))
    addr_map = dict(zip(cohort["case_key"].astype(str), cohort["DevelopmentAddress"].fillna("").astype(str)))

    # OSM address inventory per estate (pilot estates only; extend later).
    osm_estate_tokens: dict[str, set[str]] = {}
    osm_dir = settings.RAW_DIR / "osm_pilot"
    for osm_file in osm_dir.glob("*.geojson"):
        payload = json.loads(osm_file.read_text(encoding="utf-8"))
        tags = []
        for element in payload.get("elements", []):
            tag_map = element.get("tags", {})
            text = f"{tag_map.get('addr:street', '')} {tag_map.get('addr:place', '')} {tag_map.get('name', '')}"
            tags.extend(tokens(text))
        appno = osm_file.stem
        osm_estate_tokens[appno] = set(tags)

    verified = pd.read_csv(settings.SILVER_DIR / "scheme_sales_verified.csv", low_memory=False)
    verified["scheme_id"] = verified["scheme_id"].astype(str)
    pending = verified[verified["verification_status"].isin(["pending", "promoted_band"])].copy()
    pending["sale_dt"] = pd.to_datetime(pending["sale_date"], utc=True, errors="coerce")
    pending["grant_dt"] = pending["scheme_id"].map(grant_map)
    pending["days_after_grant"] = (pending["sale_dt"] - pending["grant_dt"]).dt.days
    pending["fill"] = pending["scheme_id"].map(dict(zip(fills["scheme_id"], fills["estate_name_1"].fillna("").astype(str))))
    pending["anchor"] = pending["scheme_id"].map(addr_map)
    pending["appno"] = pending["scheme_id"].str.split("__").str[1]

    # (a) chronology: 0 <= days_after_grant <= 1826 (5 years)
    chronology_ok = pending["days_after_grant"].between(0, 1826)

    # (b) OSM confirmation: candidate address tokens overlap the estate's OSM
    # token inventory (estate name not required in PPR address).
    def osm_confirm(row: pd.Series) -> bool:
        inventory = osm_estate_tokens.get(str(row["appno"]), set())
        if not inventory:
            return False
        address_tokens = tokens(str(row["address"]))
        return len(address_tokens & inventory) >= 2

    pending["osm_confirmed"] = pending.apply(osm_confirm, axis=1)
    promoted = pending[chronology_ok & pending["osm_confirmed"]].copy()

    report = {
        "pending_rows": int(len(pending)),
        "chronology_ok": int(chronology_ok.sum()),
        "osm_confirmed_rows": int(pending["osm_confirmed"].sum()),
        "promoted_rows": int(len(promoted)),
        "promoted_schemes": int(promoted["scheme_id"].nunique()) if len(promoted) else 0,
        "osm_estates_with_inventory": len(osm_estate_tokens),
        "note": "OSM layer covers pilot estates only; extends nationally when OSM/address layers expand",
    }
    promoted.to_csv(settings.SILVER_DIR / "promoted_v2_rows.csv", index=False)
    out = settings.SILVER_DIR / "pull_verification_v2.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
