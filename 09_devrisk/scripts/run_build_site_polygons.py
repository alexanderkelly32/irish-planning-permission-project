"""Runner: site polygons for satellite feature extraction.

Builds a polygon per development from BCMS phase notice coordinates and
MSFT building footprints (convex hull of buildings near notices, buffered
75 m). Writes site_polygons.geojson (WGS84) for AlphaEarth/Sentinel pulls.
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
from shapely.geometry import MultiPoint, Polygon, mapping  # noqa: E402

from devrisk import settings  # noqa: E402

TO_WGS = Transformer.from_crs(2157, 4326, always_xy=True)
TO_ITM = Transformer.from_crs(4326, 2157, always_xy=True)


def load_buildings(tile_path: Path, centre_east: float, centre_north: float) -> np.ndarray:
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
            if np.hypot(east - centre_east, north - centre_north) <= 900.0:
                points.append((east, north))
    return np.array(points) if points else np.empty((0, 2))


if __name__ == "__main__":
    phases = pd.read_csv(settings.SILVER_DIR / "phase_master.csv")
    tiles = {p.stem.replace(".csv", ""): p for p in (settings.RAW_DIR / "msft_footprints").glob("*.csv.gz")}
    from run_msft_footprints_pull import quadkey  # noqa: E402

    features = []
    for dev_id, group in phases.dropna(subset=["itm_easting", "itm_northing"]).groupby("development_id"):
        east = group["itm_easting"].astype(float)
        north = group["itm_northing"].astype(float)
        centre_east, centre_north = float(east.median()), float(north.median())
        lon, lat = TO_WGS.transform(centre_east, centre_north)
        tile = tiles.get(quadkey(lat, lon, 9))
        points = list(zip(east, north, strict=False))
        if tile:
            buildings = load_buildings(tile, centre_east, centre_north)
            if len(buildings):
                hull = MultiPoint([(float(e), float(n)) for e, n in zip(buildings[:, 0], buildings[:, 1], strict=False)]).convex_hull
                if isinstance(hull, Polygon):
                    hull_points = list(hull.exterior.coords)
                    points.extend([(float(e), float(n)) for e, n in hull_points])
        if len(points) < 3:
            continue
        hull = MultiPoint(points).convex_hull
        if not isinstance(hull, Polygon):
            continue
        buffered = hull.buffer(75.0)
        wgs = [TO_WGS.transform(x, y) for x, y in buffered.exterior.coords]
        features.append({
            "type": "Feature",
            "properties": {"development_id": dev_id, "area_m2": round(float(buffered.area), 0)},
            "geometry": mapping(Polygon(wgs)),
        })

    geojson = {"type": "FeatureCollection", "features": features}
    out = settings.SILVER_DIR / "site_polygons.geojson"
    out.write_text(json.dumps(geojson), encoding="utf-8")
    summary = {"sites": len(features),
               "median_area_m2": round(float(np.median([f["properties"]["area_m2"] for f in features])), 0),
               "out": str(out)}
    (settings.SILVER_DIR / "site_polygons_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
