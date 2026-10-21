"""PPR ingestion: bulk ZIP download -> raw -> bronze -> silver.

Bulk endpoint observed 2026-09-27:
  https://propertypriceregister.ie/website/npsra/ppr/npsra-ppr.nsf/Downloads/PPR-ALL.zip/$FILE/PPR-ALL.zip

Re-use terms (psr.ie Re-Use of Public Sector Information, 2022-07-29): free
re-use in any format including commercial re-use, subject to: acknowledge
source and copyright when supplying to others; reproduce accurately; not
misleading; NOT for the principal purpose of advertising or promoting a
product or service. Derived scheme features and cited examples are the
intended use; raw redistribution is not required.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

from .. import settings
from ..provenance import build_manifest, sha256_file, stable_row_hash, utc_now_iso, write_manifest

PPR_URL = (
    "https://propertypriceregister.ie/website/npsra/ppr/npsra-ppr.nsf/"
    "Downloads/PPR-ALL.zip/$FILE/PPR-ALL.zip"
)
RAW_ZIP_NAME = "ppr_all.zip"
CSV_INNER_NAME = "PPR-ALL.csv"
BRONZE_NAME = "ppr_bronze.parquet"
SILVER_NAME = "ppr_transactions_silver.parquet"
ARTIFACT_ID = "ppr_snapshot"

REUSE_TERMS = {
    "recorded_at": "2026-09-27",
    "source_page": "https://www.psr.ie/re-use-of-public-sector-information/",
    "terms": [
        "Free re-use in any format, including commercial re-use.",
        "Acknowledge source and copyright when supplying the information to others.",
        "Reproduce accurately; not misleading.",
        "Not for the principal purpose of advertising or promoting a particular product or service.",
    ],
}

# Official CSV columns (psr.ie). Prices exclude VAT (13.5%) for new properties.
PPR_COLUMNS = [
    "date_of_sale",
    "address",
    "postal_code",
    "county",
    "price",
    "not_full_market_price",
    "vat_exclusive",
    "description_of_property",
    "property_size_description",
]

RAW_HEADER_MAP = {
    "Date of Sale (dd/mm/yyyy)": "date_of_sale",
    "Address": "address",
    "County": "county",
    "Eircode": "eircode",
    "Postal Code": "eircode",
    "Price (\u20ac)": "price",
    "Not Full Market Price": "not_full_market_price",
    "VAT Exclusive": "vat_exclusive",
    "Description of Property": "description_of_property",
    "Property Size Description": "property_size_description",
}


def download(url: str, raw_dir: Path, force: bool = False, timeout: int = 600) -> dict[str, Any]:
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / RAW_ZIP_NAME
    sidecar = raw_dir / f"{RAW_ZIP_NAME}.meta.json"
    if target.exists() and not force:
        return {"status": "exists", "path": str(target), "note": "raw snapshot already present; pass force=True to replace"}
    response = requests.get(
        url, timeout=timeout, stream=True,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    )
    response.raise_for_status()
    if force and target.exists():
        target.unlink()
    with target.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1 << 20):
            handle.write(chunk)
    meta = {
        "retrieved_at": utc_now_iso(),
        "source_url": url,
        "http_status": int(response.status_code),
        "content_type": response.headers.get("content-type"),
        "sha256": sha256_file(target),
        "size_bytes": target.stat().st_size,
        "reuse_terms": REUSE_TERMS,
    }
    sidecar.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
    return {"status": "downloaded", "path": str(target), "meta": meta}


def _read_inner_csv(zip_path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as archive:
        inner = archive.namelist()
        if CSV_INNER_NAME not in inner:
            raise FileNotFoundError(f"{CSV_INNER_NAME} not inside {zip_path.name}")
        with archive.open(CSV_INNER_NAME) as handle:
            frame = pd.read_csv(handle, low_memory=False, encoding="cp1252")
    frame = frame.rename(columns=RAW_HEADER_MAP)
    for column in PPR_COLUMNS + ["eircode"]:
        if column not in frame.columns:
            frame[column] = None
    frame = frame[[*PPR_COLUMNS, "eircode"]].copy()
    return frame


def build_bronze(zip_path: Path, bronze_dir: Path, manifest_dir: Path) -> dict[str, Any]:
    zip_path = Path(zip_path)
    frame = _read_inner_csv(zip_path)
    input_rows = len(frame)
    bronze = frame.copy()
    bronze["row_hash"] = [stable_row_hash(row) for row in bronze.to_dict(orient="records")]

    bronze_path = bronze_dir / BRONZE_NAME
    bronze_path.parent.mkdir(parents=True, exist_ok=True)
    bronze.to_parquet(bronze_path, index=False)

    manifest = build_manifest(
        artifact_id=ARTIFACT_ID,
        source={
            "kind": "url",
            "url": PPR_URL,
            "official_site": "https://propertypriceregister.ie/",
            "reuse_terms": REUSE_TERMS,
        },
        inputs=[{"path": str(zip_path), "sha256": sha256_file(zip_path), "size_bytes": zip_path.stat().st_size}],
        transformation={"code": "devrisk.ingestion.ppr.build_bronze", "code_version": "v1", "params": {"columns": PPR_COLUMNS}},
        counts={"input_rows": input_rows, "output_rows": int(len(bronze)), "rejected_rows": 0},
        outputs=[{"path": str(bronze_path), "sha256": sha256_file(bronze_path), "rows": int(len(bronze))}],
        schema_columns=list(bronze.columns),
    )
    write_manifest(manifest, manifest_dir, ARTIFACT_ID)
    return {"bronze_path": bronze_path, "rows": len(bronze), "manifest": manifest}


def _parse_price(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.replace("\u20ac", "", regex=False).str.replace(",", "", regex=False).str.strip()
    text = text.str.replace(r"[^\d.]", "", regex=True)
    return pd.to_numeric(text, errors="coerce")


def _parse_ppr_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, format="%d/%m/%Y", errors="coerce")


def build_silver(bronze: pd.DataFrame, silver_dir: Path, manifest_dir: Path) -> dict[str, Any]:
    frame = bronze.copy()
    frame["sale_date_dt"] = _parse_ppr_date(frame["date_of_sale"].astype(str))
    frame["price_num"] = _parse_price(frame["price"])
    frame["address_norm"] = frame["address"].fillna("").astype(str).str.lower().str.replace(r"\s+", " ", regex=True).str.strip()
    frame["county_norm"] = frame["county"].fillna("").astype(str).str.lower().str.strip()
    frame["not_full_market_price_flag"] = frame["not_full_market_price"].fillna("").astype(str).str.lower().isin({"yes", "y", "true"})
    frame["vat_exclusive_flag"] = frame["vat_exclusive"].fillna("").astype(str).str.lower().isin({"yes", "y", "true"})
    frame["source_row_id"] = frame["row_hash"].str.slice(0, 16)
    frame["available_at"] = frame["sale_date_dt"]

    silver = frame[
        [
            "source_row_id", "row_hash", "sale_date_dt", "address", "address_norm",
            "eircode", "county_norm", "price_num", "not_full_market_price_flag",
            "vat_exclusive_flag", "description_of_property", "property_size_description",
            "available_at",
        ]
    ].copy()

    silver_path = silver_dir / SILVER_NAME
    silver_path.parent.mkdir(parents=True, exist_ok=True)
    silver.to_parquet(silver_path, index=False)

    manifest = build_manifest(
        artifact_id="ppr_transactions_silver",
        source={"kind": "derived", "from_artifact": ARTIFACT_ID, "note": "canonical PPR transaction table for exit labels and benchmarks"},
        inputs=[],
        transformation={"code": "devrisk.ingestion.ppr.build_silver", "code_version": "v1", "params": {"date_format": "%d/%m/%Y"}},
        counts={
            "input_rows": int(len(frame)),
            "output_rows": int(len(silver)),
            "rejected_rows": 0,
            "rows_with_date": int(silver["sale_date_dt"].notna().sum()),
            "rows_with_price": int(silver["price_num"].notna().sum()),
            "not_full_market_price": int(silver["not_full_market_price_flag"].sum()),
            "date_min": str(silver["sale_date_dt"].min()),
            "date_max": str(silver["sale_date_dt"].max()),
        },
        outputs=[{"path": str(silver_path), "sha256": sha256_file(silver_path), "rows": int(len(silver))}],
        schema_columns=list(silver.columns),
    )
    write_manifest(manifest, manifest_dir, "ppr_transactions_silver")
    return {"silver_path": silver_path, "rows": len(silver), "manifest": manifest}


def run(raw_dir: Path, bronze_dir: Path, silver_dir: Path, manifest_dir: Path, force: bool = False) -> dict[str, Any]:
    result = download(PPR_URL, raw_dir, force=force)
    if result["status"] != "downloaded" and not (raw_dir / RAW_ZIP_NAME).exists():
        raise RuntimeError("PPR download unavailable and no prior snapshot exists")
    bronze = build_bronze(Path(result["path"]), bronze_dir, manifest_dir)
    silver = build_silver(pd.read_parquet(bronze["bronze_path"]), silver_dir, manifest_dir)
    return {"download": result, "bronze": bronze, "silver": silver}
