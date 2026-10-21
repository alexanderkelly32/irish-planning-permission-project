"""Runner: CCC-event-series two-label construction (user spec).

1. Build-out blocks: cluster CCC events per scheme by (street+town+
   project_name tokens) and date gaps <=120d; block units = completion
   units summed.
2. Event-level CCC->sale attribution: nearest-before CCC is a candidate
   generator ONLY; a sale is attributed when its address/eircode tokens
   match the block's address tokens AND capacity holds (attributed sales
   <= 1.5x block units). Otherwise development-level or censored.
3. Separate models: grant->first CCC (scheme level, existing) and
   CCC->first sale (event level, strict scheme-grouped split).
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

GAP_DAYS = 120
SALE_GRACE = 90
CAPACITY_FACTOR = 1.5

if __name__ == "__main__":
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    links = pd.read_csv(settings.SILVER_DIR / "bcms_links_all_granted.csv")
    overlay = settings.SILVER_DIR / "audit" / "bcms_verdict_overlay.csv"
    if overlay.exists():
        links = pd.concat([links, pd.read_csv(overlay).reindex(columns=links.columns)], ignore_index=True)
    confirmed = links[links["confidence_band"] == "confirmed"]
    events = confirmed.merge(bcms, on="bcms_event_id", how="inner")
    events["ccc_dt"] = pd.to_datetime(events["completion_certificate_date_dt"], utc=True, errors="coerce")
    ccc_events = events[events["ccc_dt"].notna()].copy()
    ccc_events["addr_key"] = ccc_events["street"].fillna("").astype(str).str.lower() + "|" + ccc_events["town"].fillna("").astype(str).str.lower()

    # ---- 1. Build-out blocks ----
    block_rows = []
    for (scheme_id, addr_key), group in ccc_events.groupby(["scheme_id", "addr_key"]):
        group = group.sort_values("ccc_dt")
        current = []
        for _, row in group.iterrows():
            if current and (row["ccc_dt"] - current[-1]["ccc_dt"]).days <= GAP_DAYS:
                current.append(row)
            else:
                if current:
                    block_rows.append(current)
                current = [row]
        if current:
            block_rows.append(current)

    blocks = []
    block_id_counter = 0
    for cluster in block_rows:
        first = min(c["ccc_dt"] for c in cluster)
        last = max(c["ccc_dt"] for c in cluster)
        units = sum(pd.to_numeric(pd.Series([c.get("completion_units")]), errors="coerce").fillna(
            pd.to_numeric(pd.Series([c.get("dwellings_phase")]), errors="coerce").fillna(0)).iloc[0] for c in cluster)
        tokens_union: set[str] = set()
        for c in cluster:
            tokens_union |= tokens(f"{c.get('street')} {c.get('town')} {c.get('project_name')}")
        blocks.append({
            "block_id": block_id_counter,
            "scheme_id": str(cluster[0]["scheme_id"]),
            "first_ccc": first,
            "last_ccc": last,
            "ccc_events": len(cluster),
            "units": float(units),
            "tokens": tokens_union,
            "eircode": str(cluster[0].get("eircode") or ""),
        })
        block_id_counter += 1
    blocks_df = pd.DataFrame(blocks)
    blocks_df.to_csv(settings.SILVER_DIR / "ccc_blocks.csv", index=False)
    print(f"blocks: {len(blocks_df)} from {ccc_events['scheme_id'].nunique()} schemes", flush=True)

    # ---- 2. Event-level attribution ----
    sales = pd.read_csv(settings.SILVER_DIR / "scheme_sales_verified.csv", low_memory=False)
    sales["scheme_id"] = sales["scheme_id"].astype(str)
    sales = sales[~sales["verification_status"].fillna("verified_prior").eq("pending")]
    sales["sale_dt"] = pd.to_datetime(sales["sale_date"], utc=True, errors="coerce")

    attribution_rows = []
    for scheme_id, scheme_blocks in blocks_df.groupby("scheme_id"):
        scheme_sales = sales[sales["scheme_id"] == scheme_id].sort_values("sale_dt")
        scheme_blocks = scheme_blocks.sort_values("first_ccc")
        cumulative = {}
        for _, sale_row in scheme_sales.iterrows():
            sale_tokens = tokens(f"{sale_row['address']}")
            sale_eircode = str(sale_row.get("eircode") or "").strip().upper().replace(" ", "")
            chosen = None
            for _, block in scheme_blocks.iterrows():
                if sale_row["sale_dt"] < block["first_ccc"] - pd.Timedelta(days=SALE_GRACE):
                    continue
                block_tokens = block["tokens"]
                estate_match = len(sale_tokens & block_tokens) >= 2
                eircode_match = bool(sale_eircode and block["eircode"] and sale_eircode[:7] == block["eircode"][:7])
                if not (estate_match or eircode_match):
                    continue
                used = cumulative.get(block["block_id"], 0.0)
                if used >= block["units"] * CAPACITY_FACTOR:
                    continue
                chosen = block
                break
            if chosen is None:
                attribution_rows.append({
                    "scheme_id": scheme_id, "block_id": None, "sale_date": sale_row["sale_date"],
                    "ccc_to_sale_days": None, "corroboration": "none", "status": "development_level_or_censored",
                })
                continue
            cumulative[chosen["block_id"]] = cumulative.get(chosen["block_id"], 0.0) + 1.0
            attribution_rows.append({
                "scheme_id": scheme_id,
                "block_id": chosen["block_id"],
                "first_ccc": str(chosen["first_ccc"].date()),
                "sale_date": sale_row["sale_date"],
                "ccc_to_sale_days": float((sale_row["sale_dt"] - chosen["first_ccc"]).days),
                "corroboration": "eircode_match" if (sale_eircode and chosen["eircode"] and sale_eircode[:7] == chosen["eircode"][:7]) else "estate_match",
                "status": "attributed",
            })

    attribution = pd.DataFrame(attribution_rows)
    attribution.to_csv(settings.SILVER_DIR / "ccc_sale_links_event.csv", index=False)
    attributed = attribution[attribution["status"] == "attributed"].copy()
    first_by_block = attributed.groupby("block_id").agg(
        first_sale=("sale_date", "min"), ccc_to_sale_days=("ccc_to_sale_days", "min"),
        corroboration=("corroboration", "first")).reset_index()
    first_by_block = first_by_block.merge(blocks_df[["block_id", "scheme_id", "first_ccc", "units"]], on="block_id", how="left")

    # ---- 3. CCC->sale event model (strict scheme-grouped split) ----
    scheme_keys = sorted(first_by_block["scheme_id"].unique())
    rng = np.random.default_rng(7)
    rng.shuffle(scheme_keys)
    split = int(len(scheme_keys) * 0.7)
    train_schemes = set(scheme_keys[:split])
    test_schemes = set(scheme_keys[split:])
    train = first_by_block[first_by_block["scheme_id"].isin(train_schemes)]
    test = first_by_block[first_by_block["scheme_id"].isin(test_schemes)]

    report = {
        "blocks": int(len(blocks_df)),
        "attributed_rows": int(len(attributed)),
        "attributed_blocks": int(first_by_block["block_id"].nunique()),
        "estate_match_share": round(float((attributed["corroboration"] == "estate_match").mean()), 3),
        "eircode_match_share": round(float((attributed["corroboration"] == "eircode_match").mean()), 3),
        "unattributed_rows": int((attribution["status"] != "attributed").sum()),
        "ccc_to_sale_median_days": round(float(attributed["ccc_to_sale_days"].median()), 0),
        "ccc_to_sale_model": {},
    }
    if len(train) >= 20 and len(test) >= 10:
        train_median = float(train["ccc_to_sale_days"].median())
        test_median = float(test["ccc_to_sale_days"].median())
        y_te = test["ccc_to_sale_days"].to_numpy()
        pred_const = np.full(len(y_te), train_median)
        pred_block = np.full(len(y_te), test_median)
        report["ccc_to_sale_model"] = {
            "train_blocks": int(len(train)), "test_blocks": int(len(test)),
            "constant_mae": round(float(np.mean(np.abs(y_te - pred_const))), 0),
            "median_ae": round(float(np.median(np.abs(y_te - pred_const))), 0),
            "pm180": round(float(np.mean(np.abs(y_te - pred_const) <= 180)), 3),
            "pm365": round(float(np.mean(np.abs(y_te - pred_const) <= 365)), 3),
        }

    out = settings.SILVER_DIR / "ccc_event_series_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
