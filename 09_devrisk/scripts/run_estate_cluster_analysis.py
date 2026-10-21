"""Runner: building-cluster phase inference (polygon-free, free data).

For each pilot estate: load its MSFT tile, keep buildings within ~800m of
the estate centroid, DBSCAN the building centroids into spatial blocks,
and compare block sizes against BCMS phase_units. Then attach OSM
addresses where available. Writes estate_cluster_analysis.json.
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from pyproj import Transformer  # noqa: E402
from sklearn.cluster import DBSCAN  # noqa: E402
from shapely.geometry import shape  # noqa: E402

from devrisk import settings  # noqa: E402
from run_msft_footprints_pull import quadkey  # noqa: E402

TO_ITM = Transformer.from_crs(4326, 2157, always_xy=True)
TO_WGS = Transformer.from_crs(2157, 4326, always_xy=True)
RADIUS_M = 900.0
DBSCAN_EPS = 28.0


def load_nearby_buildings(tile_path: Path, centre_east: float, centre_north: float) -> np.ndarray:
    points = []
    with gzip.open(tile_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            feature = json.loads(line)
            coordinates = feature["geometry"]["coordinates"][0]
            lon = float(np.mean([c[0] for c in coordinates]))
            lat = float(np.mean([c[1] for c in coordinates]))
            east, north = TO_ITM.transform(lon, lat)
            if np.hypot(east - centre_east, north - centre_north) <= RADIUS_M:
                points.append((east, north, lon, lat))
    return np.array(points) if points else np.empty((0, 4))


if __name__ == "__main__":
    tiles = {p.stem.replace(".csv", ""): p for p in (settings.RAW_DIR / "msft_footprints").glob("*.csv.gz")}
    phases = pd.read_csv(settings.SILVER_DIR / "phase_master.csv")
    shortlist = pd.read_csv(settings.SILVER_DIR / "phase_pilot_shortlist.csv")
    report: dict = {}
    for dev_id, group in phases[phases["development_id"].astype(str).isin(
            set(shortlist["development_id"].astype(str)))].dropna(subset=["itm_easting", "itm_northing"]).groupby("development_id"):
        centre_east = float(group["itm_easting"].median())
        centre_north = float(group["itm_northing"].median())
        lon, lat = TO_WGS.transform(centre_east, centre_north)
        key = quadkey(lat, lon, 9)
        tile_path = tiles.get(key)
        if tile_path is None:
            report[dev_id] = {"error": "tile missing"}
            continue
        points = load_nearby_buildings(tile_path, centre_east, centre_north)
        if len(points) < 5:
            report[dev_id] = {"buildings_near": int(len(points)), "clusters": 0}
            continue
        clustering = DBSCAN(eps=DBSCAN_EPS, min_samples=3).fit(points[:, :2])
        labels = clustering.labels_
        n_clusters = int((labels >= 0).sum())
        cluster_sizes = [int((labels == label).sum()) for label in set(labels[labels >= 0])]
        phase_units = group["houses"].dropna()
        report[dev_id] = {
            "buildings_near": int(len(points)),
            "cluster_count": len(cluster_sizes),
            "cluster_size_median": float(np.median(cluster_sizes)) if cluster_sizes else None,
            "cluster_size_max": int(np.max(cluster_sizes)) if cluster_sizes else None,
            "cluster_sizes": sorted(cluster_sizes, reverse=True)[:12],
            "bcms_phase_units": sorted(phase_units.dropna().astype(int).tolist(), reverse=True)[:12],
            "bcms_phase_count": int(group["phase_number"].nunique()),
        }
    out = settings.SILVER_DIR / "estate_cluster_analysis.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
