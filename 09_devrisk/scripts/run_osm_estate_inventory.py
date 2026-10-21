"""Runner: national estate token inventory + v2 confirmation rerun.

Once the national OSM address index exists: for every estate in the pool,
collect OSM address tokens within 900m of its centroid into an inventory,
then re-run the chronology+OSM confirmation over the pending rows.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from pyproj import Transformer  # noqa: E402

from devrisk import settings  # noqa: E402
from run_phase_ppr_linking import tokens  # noqa: E402

INDEX_PATH = settings.RAW_DIR / "osm_ireland" / "osm_address_index.tsv"
TO_ITM = Transformer.from_crs(4326, 2157, always_xy=True)


if __name__ == "__main__":
    if not INDEX_PATH.exists():
        print(json.dumps({"error": "national index not ready yet"}), flush=True)
        raise SystemExit(0)

    # Load the national index once (streaming would be better; chunked read ok).
    index = pd.read_csv(INDEX_PATH, sep="\t", dtype=str, low_memory=False)
    index["lat"] = pd.to_numeric(index["lat"], errors="coerce")
    index["lon"] = pd.to_numeric(index["lon"], errors="coerce")
    index = index.dropna(subset=["lat", "lon"])
    east, north = TO_ITM.transform(index["lon"].to_numpy(), index["lat"].to_numpy())
    index["itm_e"] = east
    index["itm_n"] = north
    index["text"] = index["street"].fillna("") + " " + index["place"].fillna("") + " " + index["name"].fillna("")
    report = {"index_rows": int(len(index))}

    phases = pd.read_csv(settings.SILVER_DIR / "phase_master.csv")
    estates = phases.dropna(subset=["itm_easting", "itm_northing"]).groupby("development_id").agg(
        centre_e=("itm_easting", "median"), centre_n=("itm_northing", "median")).reset_index()
    estates["centre_e"] = estates["centre_e"].astype(float)
    estates["centre_n"] = estates["centre_n"].astype(float)

    inventory: dict[str, set[str]] = {}
    estates_with_osm = 0
    for _, estate in estates.iterrows():
        distance = np.hypot(index["itm_e"] - estate["centre_e"], index["itm_n"] - estate["centre_n"])
        nearby = index[distance <= 900.0]
        if len(nearby) < 3:
            continue
        token_set: set[str] = set()
        for text in nearby["text"].head(500):
            token_set |= tokens(text)
        inventory[str(estate["development_id"])] = token_set
        estates_with_osm += 1
    report["estates_with_osm_inventory"] = estates_with_osm

    fills = pd.read_csv(settings.SILVER_DIR / "audit_packs" / "manual_fills_pull.csv")
    fills["scheme_id"] = fills["scheme_id"].astype(str)
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    grant_map = dict(zip(cohort["case_key"].astype(str), pd.to_datetime(cohort["grant_date_dt"], utc=True, errors="coerce")))
    verified = pd.read_csv(settings.SILVER_DIR / "scheme_sales_verified.csv", low_memory=False)
    verified["scheme_id"] = verified["scheme_id"].astype(str)
    pending = verified[verified["verification_status"].isin(["pending", "promoted_band"])].copy()
    pending["sale_dt"] = pd.to_datetime(pending["sale_date"], utc=True, errors="coerce")
    pending["days_after_grant"] = (pending["sale_dt"] - pending["scheme_id"].map(grant_map)).dt.days
    chronology_ok = pending["days_after_grant"].between(0, 1826)

    def osm_confirm(row: pd.Series) -> bool:
        token_set = inventory.get(str(row["scheme_id"]), set())
        if not token_set:
            return False
        return len(tokens(str(row["address"])) & token_set) >= 2

    pending["osm_confirmed"] = pending.apply(osm_confirm, axis=1)
    promoted = pending[chronology_ok & pending["osm_confirmed"]].copy()
    report["pending_rows"] = int(len(pending))
    report["chronology_ok"] = int(chronology_ok.sum())
    report["osm_confirmed_rows"] = int(pending["osm_confirmed"].sum())
    report["promoted_rows"] = int(len(promoted))
    report["promoted_schemes"] = int(promoted["scheme_id"].nunique()) if len(promoted) else 0
    promoted.to_csv(settings.SILVER_DIR / "promoted_v2_national_rows.csv", index=False)
    out = settings.SILVER_DIR / "pull_verification_v2_national.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
