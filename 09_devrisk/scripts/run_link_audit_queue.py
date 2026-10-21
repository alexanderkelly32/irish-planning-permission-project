"""Runner: human-audit queues for BCMS and PPR link expansion.

BCMS: for mature granted schemes still unmatched by reference, generate
name/address-based candidates (uncommon estate-token agreement + units +
chronology + distance) and export the strongest ones for adjudication.

PPR: expanded candidate rules (routing-key + estate token, town + uncommon
token) beyond the confirmed path, exported for adjudication.

Verdicts: confirmed | probable | rejected (+ note). Imported verdicts fold
into the confirmed link sets at the next label rebuild.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.entity_resolution.ppr_matching import prepare_ppr  # noqa: E402
from devrisk.entity_resolution.scoring import address_tokens, token_similarity, uncommon_place_tokens  # noqa: E402
from devrisk.entity_resolution.ppr_matching import STOPWORDS  # noqa: E402

AUDIT_DIR = settings.SILVER_DIR / "audit"


def _uncommon_tokens(text: str) -> set[str]:
    return uncommon_place_tokens(text, STOPWORDS)


def build_bcms_name_candidates(unmatched: pd.DataFrame, bcms: pd.DataFrame) -> pd.DataFrame:
    """Top spatial+name candidates for unmatched mature schemes (probable band)."""
    rows = []
    for _, scheme in unmatched.iterrows():
        scheme_id = str(scheme["case_key"])
        s_east = pd.to_numeric(pd.Series([scheme.get("ITMEasting")]), errors="coerce").iloc[0]
        s_north = pd.to_numeric(pd.Series([scheme.get("ITMNorthing")]), errors="coerce").iloc[0]
        if pd.isna(s_east) or pd.isna(s_north):
            continue
        scheme_address = str(scheme.get("DevelopmentAddress") or "")
        scheme_description = str(scheme.get("DevelopmentDescription") or "")
        scheme_tokens = address_tokens(scheme_address) | address_tokens(scheme_description)
        scheme_uncommon = _uncommon_tokens(scheme_address) | _uncommon_tokens(scheme_description)
        units = pd.to_numeric(pd.Series([scheme.get("NumResidentialUnits")]), errors="coerce").iloc[0]
        grant = pd.Timestamp(scheme["grant_date_dt"])

        east = pd.to_numeric(bcms["itm_easting"], errors="coerce")
        north = pd.to_numeric(bcms["itm_northing"], errors="coerce")
        dist = np.hypot(east - s_east, north - s_north)
        nearby = bcms[dist <= 800].copy()
        if nearby.empty:
            continue
        nearby["distance_metres"] = dist[dist <= 800].round(0)
        nearby["token_sim"] = nearby["address_full"].fillna("").astype(str).map(
            lambda text: token_similarity(scheme_address, text)
        )
        nearby["uncommon_overlap"] = nearby["address_full"].fillna("").astype(str).map(
            lambda text: len(_uncommon_tokens(text) & scheme_uncommon)
        )
        nearby["name_overlap"] = nearby["project_name"].fillna("").astype(str).map(
            lambda text: len(_uncommon_tokens(text) & scheme_uncommon)
        )
        nearby = nearby[(nearby["uncommon_overlap"] >= 1) | (nearby["name_overlap"] >= 1)]
        if nearby.empty:
            continue
        nearby = nearby.sort_values(["uncommon_overlap", "name_overlap", "distance_metres"], ascending=[False, False, True]).head(3)
        for _, candidate in nearby.iterrows():
            commenced = pd.to_datetime(candidate["commencement_date_dt"], utc=True, errors="coerce")
            chronology = "unknown"
            if pd.notna(commenced):
                chronology = "after_grant" if commenced >= grant else "before_grant"
            rows.append({
                "queue": "bcms",
                "scheme_id": scheme_id,
                "scheme_address": scheme_address[:80],
                "scheme_units": None if pd.isna(units) else float(units),
                "grant_date": str(grant.date()),
                "bcms_event_id": candidate["bcms_event_id"],
                "bcms_address": str(candidate["address_full"])[:80],
                "bcms_project_name": str(candidate["project_name"])[:60],
                "bcms_ref": str(candidate["planning_reference"]),
                "bcms_units": None if pd.isna(candidate["dwellings_total"]) else float(candidate["dwellings_total"]),
                "bcms_commencement": str(commenced.date()) if pd.notna(commenced) else "",
                "distance_metres": round(float(candidate["distance_metres"]), 0),
                "uncommon_token_overlap": int(candidate["uncommon_overlap"]),
                "name_token_overlap": int(candidate["name_overlap"]),
                "chronology": chronology,
                "verdict": "",
                "verdict_note": "",
            })
    return pd.DataFrame(rows)


def build_ppr_expanded_candidates(cohort: pd.DataFrame, ppr: pd.DataFrame, existing_confirmed: set[str]) -> pd.DataFrame:
    """Expanded PPR candidates for schemes without confirmed sales links."""
    ppr_prepared = prepare_ppr(ppr)
    rows = []
    count = 0
    for _, scheme in cohort.iterrows():
        scheme_id = str(scheme["case_key"])
        if scheme_id in existing_confirmed:
            continue
        if count >= 150:
            break
        address = str(scheme.get("DevelopmentAddress") or "")
        tokens = address_tokens(address)
        uncommon = _uncommon_tokens(address)
        county = _county_from_authority(scheme.get("PlanningAuthority"))
        frame = ppr_prepared[ppr_prepared["county_norm"] == county] if county else ppr_prepared
        if frame.empty or not tokens:
            continue
        overlap = frame["uncommon_tokens"].map(lambda s: len(s & uncommon))
        candidates = frame[overlap >= 1]
        if candidates.empty:
            continue
        count += 1
        grant = pd.Timestamp(scheme["grant_date_dt"])
        candidates = candidates.copy()
        candidates["uncommon_overlap"] = overlap[overlap >= 1]
        candidates["addr_sim"] = candidates["address_norm"].map(lambda text: token_similarity(address, text))
        sale_dt = pd.to_datetime(candidates["sale_date_dt"], utc=True, errors="coerce")
        candidates["chronology_ok"] = (sale_dt >= grant).fillna(False).astype(int)
        top = candidates.sort_values(["uncommon_overlap", "addr_sim"], ascending=False).head(3)
        for _, candidate in top.iterrows():
            rows.append({
                "queue": "ppr",
                "scheme_id": scheme_id,
                "scheme_address": address[:80],
                "grant_date": str(grant.date()),
                "ppr_source_row_id": candidate["source_row_id"],
                "ppr_address": str(candidate["address_norm"])[:80],
                "sale_date": str(candidate["sale_date_dt"])[:10],
                "price": None if pd.isna(candidate["price_num"]) else float(candidate["price_num"]),
                "uncommon_token_overlap": int(candidate["uncommon_overlap"]),
                "address_similarity": round(float(candidate["addr_sim"]), 3),
                "sale_after_grant": int(candidate["chronology_ok"]),
                "verdict": "",
                "verdict_note": "",
            })
    return pd.DataFrame(rows)


def _county_from_authority(authority: object) -> str:
    text = str(authority or "").lower()
    for county in ("carlow", "cavan", "clare", "cork", "donegal", "dublin", "galway", "kerry",
                   "kildare", "kilkenny", "laois", "leitrim", "limerick", "longford", "louth",
                   "mayo", "meath", "monaghan", "offaly", "roscommon", "sligo", "tipperary",
                   "waterford", "westmeath", "wexford", "wicklow"):
        if county in text:
            return county
    return ""


if __name__ == "__main__":
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    bcms_links = pd.read_csv(settings.SILVER_DIR / "bcms_links_all_granted.csv")
    ppr = pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet")
    ppr_links = pd.read_csv(settings.SILVER_DIR / "ppr_links_all_granted.csv")

    mature = cohort[cohort["grant_year"].between(2016, 2022)]
    confirmed_bcms = set(bcms_links[bcms_links["confidence_band"] == "confirmed"]["scheme_id"])
    unmatched = mature[~mature["case_key"].astype(str).isin(confirmed_bcms)]
    print(f"unmatched mature schemes for BCMS name-matching: {len(unmatched)}", flush=True)

    bcms_queue = build_bcms_name_candidates(unmatched, bcms)
    confirmed_ppr = set(ppr_links[ppr_links["confidence_band"] == "confirmed"]["scheme_id"])
    ppr_queue = build_ppr_expanded_candidates(cohort, ppr, confirmed_ppr)
    print(f"bcms queue rows: {len(bcms_queue)}; ppr queue rows: {len(ppr_queue)}", flush=True)

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    if len(bcms_queue) > 200:
        bcms_queue = bcms_queue.sample(n=200, random_state=7)
    bcms_queue.to_csv(AUDIT_DIR / "audit_bcms_name_links.csv", index=False)
    ppr_queue.to_csv(AUDIT_DIR / "audit_ppr_expanded_links.csv", index=False)
    print(json.dumps({
        "bcms_queue_rows": int(len(bcms_queue)),
        "ppr_queue_rows": int(len(ppr_queue)),
        "bcms_queue_columns": list(bcms_queue.columns),
        "ppr_queue_columns": list(ppr_queue.columns),
    }, indent=2))
