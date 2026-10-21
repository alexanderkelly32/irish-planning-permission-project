#!/usr/bin/env python3
"""Pull every mapped wind turbine in Ireland from OpenStreetMap and cluster
them into physical wind-farm sites.

Queries Overpass (kumi.systems mirror) for:
  - generator:source=wind nodes/ways/relations (turbines)
  - power=plant + plant:source=wind (whole-farm polygons, some old farms)

Outputs:
  source_data/osm_wind_turbines.csv   one row per turbine (lat/lon, tags)
  source_data/osm_wind_plants.csv     farm polygons/points with name tags
  source_data/osm_wind_clusters.csv   DBSCAN clusters = physical farm sites
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sklearn.cluster import DBSCAN

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "source_data"
RAW = OUT / "osm_raw"
RAW.mkdir(parents=True, exist_ok=True)

OVERPASS = "https://overpass.kumi.systems/api/interpreter"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) planning-wind-atlas/1.0"}

QUERY = """
[out:json][timeout:900];
area["ISO3166-1"="IE"][admin_level=2]->.a;
(
  node["generator:source"="wind"](area.a);
  way["generator:source"="wind"](area.a);
  relation["generator:source"="wind"](area.a);
  node["power"="plant"]["plant:source"="wind"](area.a);
  way["power"="plant"]["plant:source"="wind"](area.a);
  relation["power"="plant"]["plant:source"="wind"](area.a);
);
out center tags;
"""


def pull() -> None:
    raw_path = RAW / "osm_wind_raw.json"
    if raw_path.exists() and raw_path.stat().st_size > 1000:
        print(f"reusing cached {raw_path} ({raw_path.stat().st_size / 1e6:.1f} MB)")
        return
    print("querying overpass (this can take several minutes)...", flush=True)
    response = requests.post(OVERPASS, data={"data": QUERY}, headers=HEADERS, timeout=900)
    response.raise_for_status()
    raw_path.write_bytes(response.content)
    print(f"saved {raw_path} ({raw_path.stat().st_size / 1e6:.1f} MB)", flush=True)


def parse() -> tuple[pd.DataFrame, pd.DataFrame]:
    raw_path = RAW / "osm_wind_raw.json"
    payload = json.loads(raw_path.read_bytes())
    turbines: list[dict] = []
    plants: list[dict] = []
    for el in payload.get("elements", []):
        tags = el.get("tags") or {}
        rec = {
            "osm_id": el["id"],
            "osm_type": el["type"],
            "lat": el.get("lat") or (el.get("center") or {}).get("lat"),
            "lon": el.get("lon") or (el.get("center") or {}).get("lon"),
            "name": tags.get("name") or tags.get("plant:name") or "",
            "operator": tags.get("operator") or tags.get("plant:operator") or "",
            "height_m": tags.get("height"),
            "manufacturer": tags.get("manufacturer") or "",
            "model": tags.get("model") or tags.get("generator:model") or "",
            "capacity": tags.get("generator:output:electricity")
            or tags.get("rated_power")
            or tags.get("generator:output")
            or tags.get("plant:output:electricity")
            or "",
        }
        if el["type"] == "way":
            rec["way_geometry"] = json.dumps(el.get("geometry", []))[:500]
        if tags.get("power") == "plant" and "plant:source" in tags:
            plants.append(rec)
        else:
            turbines.append(rec)
    tdf = pd.DataFrame(turbines)
    pdf = pd.DataFrame(plants)
    print(f"elements: {len(payload.get('elements', []))} -> turbines={len(tdf)}, plants={len(pdf)}")
    return tdf, pdf


def cluster(tdf: pd.DataFrame) -> pd.DataFrame:
    """DBSCAN on haversine distance; turbines in the same farm chain together."""
    from math import radians

    lat_r = tdf["lat"].astype(float).map(radians).to_numpy()
    lon_r = tdf["lon"].astype(float).map(radians).to_numpy()
    dlat = lat_r[:, None] - lat_r[None, :]
    dlon = lon_r[:, None] - lon_r[None, :]
    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat_r)[:, None] * np.cos(lat_r)[None, :] * np.sin(dlon / 2) ** 2
    )
    km = 6371.0 * 2 * np.arcsin(np.sqrt(a))
    if len(tdf) < 2:
        tdf["cluster"] = -1
        return tdf
    labels = DBSCAN(eps=1.0, min_samples=2, metric="precomputed").fit_predict(km)
    tdf["cluster"] = labels
    return tdf


def build_clusters(tdf: pd.DataFrame, pdf: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for cid, grp in tdf[tdf["cluster"] >= 0].groupby("cluster"):
        names = grp["name"].replace("", pd.NA).dropna().unique().tolist()
        ops = grp["operator"].replace("", pd.NA).dropna().unique().tolist()
        rows.append({
            "cluster_id": int(cid),
            "turbine_count": int(len(grp)),
            "lat": float(grp["lat"].astype(float).mean()),
            "lon": float(grp["lon"].astype(float).mean()),
            "osm_name": names[0] if names else "",
            "osm_names": "|".join(names[:5]),
            "osm_operator": ops[0] if ops else "",
            "osm_operators": "|".join(ops[:5]),
            "height_m_common": grp["height_m"].value_counts().index[0] if grp["height_m"].notna().any() else "",
            "source": "osm_turbines",
        })
    single = tdf[tdf["cluster"] == -1]
    for _, r in single.iterrows():
        rows.append({
            "cluster_id": -1,
            "turbine_count": 1,
            "lat": float(r["lat"]),
            "lon": float(r["lon"]),
            "osm_name": r.get("name") or "",
            "osm_names": r.get("name") or "",
            "osm_operator": r.get("operator") or "",
            "osm_operators": r.get("operator") or "",
            "height_m_common": r.get("height_m") or "",
            "source": "osm_single_turbine",
        })
    return pd.DataFrame(rows)


def main() -> None:
    pull()
    tdf, pdf = parse()
    tdf.to_csv(OUT / "osm_wind_turbines.csv", index=False)
    pdf.to_csv(OUT / "osm_wind_plants.csv", index=False)
    tdf = cluster(tdf)
    clusters = build_clusters(tdf, pdf)
    clusters.to_csv(OUT / "osm_wind_clusters.csv", index=False)
    print(f"turbines={len(tdf)} mapped elements={len(tdf) + len(pdf)}")
    print(f"clusters(farms)={len(clusters)} of which single-turbine={int((clusters['source'] == 'osm_single_turbine').sum())}")
    print(f"multi-turbine farms={int((clusters['source'] == 'osm_turbines').sum())}")


if __name__ == "__main__":
    main()
