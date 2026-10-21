"""Runner: pull PPR transactions using the human-filled sales workbook.

For each filled row: eircode exact matches (normalised) + estate-name token
matches within the county + chronology (sale >= grant). Transactions are
deduplicated by row hash; not-full-market-price rows are flagged and
excluded from headline counts. Writes scheme_sales_verified.csv and a
coverage summary; feeds the next exit-label rebuild.
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
from devrisk.entity_resolution.scoring import address_tokens  # noqa: E402

CENSOR = "2026-09-27"


def _norm_eircode(value: str) -> str:
    return str(value).strip().upper().replace(" ", "").replace("-", "")


def _county_from_authority(authority: str) -> str:
    text = str(authority or "").lower()
    for county in _COUNTY_WORDS:
        if county in text:
            return county
    return ""


_COUNTY_WORDS = {
    "carlow", "cavan", "clare", "cork", "donegal", "dublin", "galway", "kerry",
    "kildare", "kilkenny", "laois", "leitrim", "limerick", "longford", "louth",
    "mayo", "meath", "monaghan", "offaly", "roscommon", "sligo", "tipperary",
    "waterford", "westmeath", "wexford", "wicklow",
}


def pull(workbook_path: Path, out_path: Path | None = None) -> dict:
    workbook = pd.read_csv(workbook_path)
    filled = workbook[
        workbook[["estate_name_1", "estate_name_2", "estate_name_3", "eircode"]]
        .fillna("").astype(str).apply(lambda row: row.str.strip().ne("").any(), axis=1)
    ]
    print(f"filled rows: {len(filled)} of {len(workbook)}", flush=True)

    ppr = pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet")
    ppr_prepared = prepare_ppr(ppr)

    sales_rows: list[dict] = []
    scheme_coverage: dict[str, dict] = {}
    for _, row in filled.iterrows():
        scheme_id = str(row["scheme_id"])
        county = _county_from_authority(row["authority"])
        grant = pd.Timestamp(0)
        frame = ppr_prepared[ppr_prepared["county_norm"] == county] if county else ppr_prepared

        names = [str(row.get(f"estate_name_{i}") or "").strip() for i in (1, 2, 3) if str(row.get(f"estate_name_{i}") or "").strip()]
        name_tokens: set[str] = set()
        for name in names:
            name_tokens |= address_tokens(name)

        # Anchor tokens from the register address (town/street) guard against
        # same-named estates elsewhere in the county (e.g. multiple "The Willows").
        # Only uncommon tokens count as anchors - county names and road words
        # are too weak.
        from devrisk.entity_resolution.ppr_matching import STOPWORDS  # noqa: PLC0415
        from devrisk.entity_resolution.scoring import uncommon_place_tokens  # noqa: PLC0415

        register_address = str(row.get("register_address") or "")
        anchor_tokens = uncommon_place_tokens(register_address, STOPWORDS) - name_tokens
        anchor_tokens -= _COUNTY_WORDS

        eircode = _norm_eircode(str(row.get("eircode") or ""))
        eircode_hit = frame["eircode"].fillna("").map(_norm_eircode).eq(eircode) if eircode else pd.Series(False, index=frame.index)

        token_hits = None
        anchor_hits = None
        if name_tokens:
            required = min(len(name_tokens), 2)
            token_hits = frame["tokens"].map(lambda tokens: len(tokens & name_tokens) >= required)
        if anchor_tokens:
            anchor_hits = frame["tokens"].map(lambda tokens: len(tokens & anchor_tokens) >= 1)
        name_match = token_hits if token_hits is not None else pd.Series(False, index=frame.index)
        if anchor_hits is not None:
            name_match = name_match & anchor_hits
        mask = eircode_hit | name_match
        candidates = frame[mask].copy()
        if candidates.empty:
            scheme_coverage[scheme_id] = {"sales": 0, "note": "no PPR rows matched"}
            continue

        candidates["sale_date"] = pd.to_datetime(candidates["sale_date_dt"], utc=True, errors="coerce")
        candidates = candidates.dropna(subset=["sale_date"])
        candidates = candidates[candidates["sale_date"] >= pd.Timestamp("2010-01-01", tz="UTC")]
        candidates = candidates.sort_values("sale_date")

        matched = 0
        for _, transaction in candidates.iterrows():
            matched += 1
            sales_rows.append({
                "scheme_id": scheme_id,
                "ppr_source_row_id": transaction["source_row_id"],
                "sale_date": str(transaction["sale_date"].date()),
                "price": None if pd.isna(transaction["price_num"]) else float(transaction["price_num"]),
                "address": str(transaction["address_norm"])[:100],
                "eircode": str(transaction["eircode"] or ""),
                "not_full_market_price": int(bool(transaction["not_full_market_price_flag"])),
                "match_method": "human_estate_name" + ("_eircode" if eircode_hit.loc[transaction.name] else "_tokens"),
            })
        scheme_coverage[scheme_id] = {"sales": matched}

    sales = pd.DataFrame(sales_rows).drop_duplicates(subset=["scheme_id", "ppr_source_row_id"])
    out_path = out_path or (settings.SILVER_DIR / "scheme_sales_verified.csv")
    sales.to_csv(out_path, index=False)

    summary = {
        "schemes_filled": int(len(filled)),
        "schemes_with_sales": int(sum(1 for info in scheme_coverage.values() if info["sales"] > 0)),
        "total_sales_rows": int(len(sales)),
        "excluded_not_full_market": int(sales["not_full_market_price"].sum()),
        "out_path": str(out_path),
    }
    (settings.SILVER_DIR / "scheme_sales_verified_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    pull(settings.SILVER_DIR / "sales_workbook.csv")
