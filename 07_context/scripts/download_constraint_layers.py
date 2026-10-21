#!/usr/bin/env python3
"""Download national constraint layers for site-context evidence.

Sources:
  - NIAH buildings national dataset (CSV, heritagedata.maps.arcgis.com)
  - NPWS Natura 2000 boundaries: SPA + SAC (ITM shapefiles, npws.ie)
  - EPA urban waste-water emission points (WFS, gis.epa.ie)
  - TII/TMU traffic counters: already on disk (07_context/raw/tmu_traffic_counters.geojson)

Outputs land in 07_context/raw/; build_constraint_reference.py turns them into
query-time parquet tables.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "07_context" / "raw"

NIAH_URL = "https://heritagedata.maps.arcgis.com/sharing/rest/content/items/69689ebd654e4a83af76fdb4648f8529/data"
SPA_URL = "https://www.npws.ie/sites/default/files/files/SPA_ITM_2026_02.zip"
SAC_URL = "https://www.npws.ie/sites/default/files/files/SAC_ITM_2026_02.zip"
EPA_WFS = "http://gis.epa.ie/geoserver/EPA/wfs"
EPA_LAYER = "EPA:SIIF_UWWEmissionPoints"


def _download(url: str, out_path: Path, timeout: int = 300) -> None:
    print(f"GET {url}", flush=True)
    with requests.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        with out_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1 << 16):
                handle.write(chunk)
    print(f"  -> {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)", flush=True)


def download_niah() -> None:
    out = RAW / "niah_buildings.csv"
    if out.exists() and out.stat().st_size > 100_000:
        print("niah already present")
        return
    _download(NIAH_URL, out)


def download_natura() -> None:
    out_dir = RAW / "natura"
    for name, url in (("SPA_ITM_2026_02.zip", SPA_URL), ("SAC_ITM_2026_02.zip", SAC_URL)):
        zip_path = RAW / name
        if not zip_path.exists():
            try:
                _download(url, zip_path)
            except Exception as exc:
                print(f"  FAILED {name}: {type(exc).__name__} {str(exc)[:120]}")
                continue
        if not zipfile.is_zipfile(zip_path):
            print(f"  not a zip: {zip_path}")
            continue
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(out_dir)
            print(f"  extracted {name}: {len(archive.namelist())} entries -> {out_dir}")


def download_wwtp() -> None:
    out = RAW / "wwtp_emission_points.json"
    if out.exists() and out.stat().st_size > 100_000:
        print("wwtp already present")
        return
    print("GET EPA WFS emission points", flush=True)
    response = requests.get(
        EPA_WFS,
        params={"service": "WFS", "version": "1.1.0", "request": "GetFeature",
                "typeName": EPA_LAYER, "outputFormat": "application/json", "maxFeatures": 100000},
        timeout=300,
    )
    response.raise_for_status()
    out.write_text(response.text, encoding="utf-8")
    print(f"  -> {out} ({out.stat().st_size / 1e6:.1f} MB)")


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    download_niah()
    download_natura()
    download_wwtp()
    print("done")


if __name__ == "__main__":
    main()
