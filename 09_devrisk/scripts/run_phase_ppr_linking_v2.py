"""Runner: phase PPR linking v2 - human-confirmed estate names.

The v1 dictionary (raw project_name/description tokens) gave 6.3% precision
on the B band (PACK_16). v2 builds the estate dictionary from HUMAN-CONFIRMED
sources: PACK_1/14 workbook estate names + BCMS-notice-name auto-matches +
verified PPR addresses (estate tokens). Then links phases with the same
A/B/C rules but a clean dictionary. Requires the same audit gate afterwards.
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
from run_phase_ppr_linking import COUNTY_WORDS  # noqa: E402

CENSOR = pd.Timestamp("2026-09-27", tz="UTC")


def tokens(text: str) -> set[str]:
    return {t for t in uncommon_place_tokens(str(text or ""), STOPWORDS) if len(t) >= 3} - COUNTY_WORDS


def build_estate_dict() -> dict[str, set[str]]:
    estate: dict[str, set[str]] = {}
    workbook = pd.read_csv(settings.SILVER_DIR / "audit_packs" / "sales_workbook.csv")
    filled = workbook[workbook[["estate_name_1", "estate_name_2", "estate_name_3"]].fillna("").astype(str).apply(
        lambda row: row.str.strip().ne("").any(), axis=1)]
    for _, row in filled.iterrows():
        names = [str(row.get(f"estate_name_{i}") or "").strip() for i in (1, 2, 3) if str(row.get(f"estate_name_{i}") or "").strip()]
        estate.setdefault(str(row["scheme_id"]), set()).update(*[tokens(n) for n in names])
    notice = pd.read_csv(settings.SILVER_DIR / "scheme_sales_bcms_notice_auto.csv")
    for scheme_id, group in notice.groupby("scheme_id"):
        estate.setdefault(str(scheme_id), set()).update(*[tokens(n) for n in group["bcms_name"].dropna().astype(str)])
    verified = pd.read_csv(settings.SILVER_DIR / "scheme_sales_verified.csv")
    verified["scheme_id"] = verified["scheme_id"].astype(str)
    for scheme_id, group in verified.groupby("scheme_id"):
        for address in group["address"].dropna().astype(str):
            estate.setdefault(scheme_id, set()).update(tokens(address))
    return estate


if __name__ == "__main__":
    phases = pd.read_csv(settings.SILVER_DIR / "phase_master.csv")
    viable = phases[(phases["route"] == "private_sale") & phases["houses"].between(10, 150)].copy()
    viable = viable[pd.to_datetime(viable["commencement_date"], utc=True, errors="coerce").notna()]
    viable = viable[pd.to_datetime(viable["commencement_date"], utc=True) < CENSOR - pd.Timedelta(days=365)]
    estate_dict = build_estate_dict()
    print(f"estate dictionary: {len(estate_dict)} schemes; viable phases: {len(viable)}", flush=True)

    ppr = prepare_ppr(pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet"))
    ppr["sale_date"] = pd.to_datetime(ppr["sale_date_dt"], utc=True, errors="coerce")

    rows = []
    for _, phase in viable.iterrows():
        phase_id = str(phase["phase_id"])
        development_id = str(phase["development_id"])
        estate_tokens = estate_dict.get(development_id, set())
        if not estate_tokens:
            continue
        commencement = pd.to_datetime(phase["commencement_date"], utc=True)
        county = next((c for c in COUNTY_WORDS if c in str(phase.get("town") or "").lower() or c in str(phase.get("street") or "").lower()), "")
        frame = ppr[ppr["county_norm"] == county] if county else ppr
        if frame.empty:
            continue
        street_tokens = tokens(phase.get("street"))
        town_tokens = tokens(phase.get("town"))
        estate_hits = frame["tokens"].map(lambda s: len(s & estate_tokens))
        town_hits = frame["tokens"].map(lambda s: len(s & town_tokens)) if town_tokens else pd.Series(0, index=frame.index)
        street_hits = frame["tokens"].map(lambda s: len(s & street_tokens)) if street_tokens else pd.Series(0, index=frame.index)
        candidates = frame[(estate_hits >= 2) & (town_hits >= 1)].copy()
        if candidates.empty:
            candidates = frame[(estate_hits >= 1) & (town_hits >= 1) & (street_hits >= 1)].copy()
        if candidates.empty:
            continue
        candidates["estate_overlap"] = estate_hits[candidates.index]
        candidates["town_overlap"] = town_hits[candidates.index]
        candidates["street_overlap"] = street_hits[candidates.index]
        candidates = candidates[candidates["sale_date"] >= commencement - pd.Timedelta(days=90)]
        candidates = candidates[candidates["sale_date"] <= CENSOR]
        candidates = candidates[~candidates["not_full_market_price_flag"]]
        if candidates.empty:
            continue
        candidates["confidence"] = np.where(candidates["estate_overlap"] >= 2, "B", "C")
        cap = int(phase["houses"] * 1.5)
        candidates = candidates.head(cap)
        for _, candidate in candidates.iterrows():
            rows.append({
                "phase_id": phase_id,
                "development_id": development_id,
                "town": phase.get("town"), "street": phase.get("street"),
                "estate_tokens_used": " ".join(sorted(estate_tokens))[:80],
                "phase_units": phase["houses"],
                "ppr_source_row_id": candidate["source_row_id"],
                "address": str(candidate["address_norm"])[:90],
                "eircode": str(candidate["eircode"] or ""),
                "sale_date": str(candidate["sale_date"].date()),
                "price": None if pd.isna(candidate["price_num"]) else float(candidate["price_num"]),
                "confidence": candidate["confidence"],
                "verdict": "",
                "verdict_note": "",
            })

    candidates = pd.DataFrame(rows)
    candidates.to_csv(settings.SILVER_DIR / "phase_sales_candidates_v2.csv", index=False)
    summary = {
        "candidate_rows": int(len(candidates)),
        "phases_with_candidates": int(candidates["phase_id"].nunique()) if len(candidates) else 0,
        "by_confidence": candidates["confidence"].value_counts().to_dict() if len(candidates) else {},
    }
    (settings.SILVER_DIR / "phase_sales_candidates_v2_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
