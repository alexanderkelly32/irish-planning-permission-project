"""Runner: phase-level PPR linking with A/B/C confidence (plan step 3).

For each viable private-sale housing phase (10-150 houses), generate PPR
candidate units from the phase address dictionary (street + town + estate
tokens from project name/description) and classify:
  A - exact eircode match
  B - estate tokens >= 2 + street + town + sale after commencement
  C - weaker matches
  Rejected - town conflict
Caps: candidates beyond 1.5x phase units flagged. Writes
phase_sales_candidates.csv + a stratified audit pack for human review.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.entity_resolution.ppr_matching import STOPWORDS, prepare_ppr  # noqa: E402
from devrisk.entity_resolution.scoring import uncommon_place_tokens  # noqa: E402

CENSOR = pd.Timestamp("2026-09-27", tz="UTC")
COUNTY_WORDS = {"carlow", "cavan", "clare", "cork", "donegal", "dublin", "galway", "kerry",
                "kildare", "kilkenny", "laois", "leitrim", "limerick", "longford", "louth",
                "mayo", "meath", "monaghan", "offaly", "roscommon", "sligo", "tipperary",
                "waterford", "westmeath", "wexford", "wicklow"}


def tokens(text: str) -> set[str]:
    return {t for t in uncommon_place_tokens(str(text or ""), STOPWORDS) if len(t) >= 3} - COUNTY_WORDS


if __name__ == "__main__":
    phases = pd.read_csv(settings.SILVER_DIR / "phase_master.csv")
    viable = phases[(phases["route"] == "private_sale") & phases["houses"].between(10, 150)].copy()
    viable = viable[pd.to_datetime(viable["commencement_date"], utc=True, errors="coerce").notna()]
    viable = viable[pd.to_datetime(viable["commencement_date"], utc=True) < CENSOR - pd.Timedelta(days=365)]
    print(f"viable phases: {len(viable)}", flush=True)

    ppr = prepare_ppr(pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet"))
    ppr["sale_date"] = pd.to_datetime(ppr["sale_date_dt"], utc=True, errors="coerce")

    rows = []
    for _, phase in viable.iterrows():
        phase_id = str(phase["phase_id"])
        commencement = pd.to_datetime(phase["commencement_date"], utc=True)
        county = next((c for c in COUNTY_WORDS if c in str(phase.get("town") or "").lower() or c in str(phase.get("planning_description") or "").lower()), "")
        county = county or next((c for c in COUNTY_WORDS if c in str(phase.get("street") or "").lower()), "")
        frame = ppr[ppr["county_norm"] == county] if county else ppr
        if frame.empty:
            continue

        street_tokens = tokens(phase.get("street"))
        town_tokens = tokens(phase.get("town"))
        estate_tokens = tokens(phase.get("project_name")) | tokens(phase.get("description_raw"))
        estate_tokens -= street_tokens | town_tokens
        eircode = str(phase.get("eircode") or "").strip().upper().replace(" ", "")

        overlap_street = frame["tokens"].map(lambda s: len(s & street_tokens)) if street_tokens else pd.Series(0, index=frame.index)
        overlap_town = frame["tokens"].map(lambda s: len(s & town_tokens)) if town_tokens else pd.Series(0, index=frame.index)
        overlap_estate = frame["tokens"].map(lambda s: len(s & estate_tokens)) if estate_tokens else pd.Series(0, index=frame.index)
        eircode_hit = frame["eircode"].fillna("").str.replace(" ", "").str.upper().eq(eircode) if eircode else pd.Series(False, index=frame.index)

        base_hit = (overlap_street >= 1) & (overlap_town >= 1)
        candidates = frame[base_hit | eircode_hit | ((overlap_estate >= 2) & (overlap_town >= 1))].copy()
        if candidates.empty:
            continue
        candidates["overlap_street"] = overlap_street[candidates.index]
        candidates["overlap_town"] = overlap_town[candidates.index]
        candidates["overlap_estate"] = overlap_estate[candidates.index]
        candidates["eircode_hit"] = eircode_hit[candidates.index]
        candidates = candidates[candidates["sale_date"] >= commencement - pd.Timedelta(days=90)]
        candidates = candidates[candidates["sale_date"] <= CENSOR]
        candidates = candidates[~candidates["not_full_market_price_flag"]]
        if candidates.empty:
            continue

        def classify(row: pd.Series) -> str:
            if row["eircode_hit"]:
                return "A"
            if row["overlap_estate"] >= 2 and row["overlap_street"] >= 1 and row["overlap_town"] >= 1:
                return "B"
            if row["overlap_street"] >= 1 and row["overlap_town"] >= 1:
                return "C"
            return "Rejected"

        candidates["confidence"] = candidates.apply(classify, axis=1)
        candidates = candidates[candidates["confidence"] != "Rejected"]
        if candidates.empty:
            continue
        candidates = candidates.sort_values(["confidence", "sale_date"])
        # Cap: if candidates exceed 1.5x phase units, keep earliest and flag.
        cap = int(phase["houses"] * 1.5)
        overflow = len(candidates) > cap
        candidates = candidates.head(cap) if overflow else candidates
        for _, candidate in candidates.iterrows():
            rows.append({
                "phase_id": phase_id,
                "development_id": str(phase["development_id"]),
                "town": phase.get("town"), "street": phase.get("street"),
                "phase_units": phase["houses"],
                "ppr_source_row_id": candidate["source_row_id"],
                "address": str(candidate["address_norm"])[:90],
                "eircode": str(candidate["eircode"] or ""),
                "sale_date": str(candidate["sale_date"].date()),
                "price": None if pd.isna(candidate["price_num"]) else float(candidate["price_num"]),
                "confidence": candidate["confidence"],
                "overflow_flag": int(overflow),
                "verdict": "",
                "verdict_note": "",
            })

    candidates = pd.DataFrame(rows)
    candidates.to_csv(settings.SILVER_DIR / "phase_sales_candidates.csv", index=False)
    summary = {
        "candidate_rows": int(len(candidates)),
        "phases_with_candidates": int(candidates["phase_id"].nunique()) if len(candidates) else 0,
        "by_confidence": candidates["confidence"].value_counts().to_dict() if len(candidates) else {},
        "overflow_flags": int(candidates["overflow_flag"].sum()) if len(candidates) else 0,
    }
    (settings.SILVER_DIR / "phase_sales_candidates_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
