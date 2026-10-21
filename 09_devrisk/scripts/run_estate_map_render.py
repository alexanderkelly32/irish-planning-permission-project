"""Runner: render estate maps for manual phase review.

One PNG per pilot estate: MSFT buildings coloured by DBSCAN cluster, BCMS
phase notice centroids numbered, OSM address points marked, estate centroid
+ radius. A review CSV with verdict columns accompanies the maps.
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

from devrisk import settings  # noqa: E402
from run_msft_footprints_pull import quadkey  # noqa: E402

TO_ITM = Transformer.from_crs(4326, 2157, always_xy=True)
TO_WGS = Transformer.from_crs(2157, 4326, always_xy=True)
RADIUS_M = 900.0
OUT_DIR = settings.ROOT / "09_devrisk" / "data" / "silver" / "estate_review_maps"


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
            if np.hypot(east - centre_east, north - centre_north) <= RADIUS_M:
                points.append((east, north))
    return np.array(points) if points else np.empty((0, 2))


if __name__ == "__main__":
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: E402

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tiles = {p.stem.replace(".csv", ""): p for p in (settings.RAW_DIR / "msft_footprints").glob("*.csv.gz")}
    phases = pd.read_csv(settings.SILVER_DIR / "phase_master.csv")
    shortlist = pd.read_csv(settings.SILVER_DIR / "phase_pilot_shortlist.csv")
    devs = set(shortlist["development_id"].astype(str))

    review_rows = []
    for dev_id, group in phases[phases["development_id"].astype(str).isin(devs)].dropna(subset=["itm_easting", "itm_northing"]).groupby("development_id"):
        centre_east = float(group["itm_easting"].median())
        centre_north = float(group["itm_northing"].median())
        lon, lat = TO_WGS.transform(centre_east, centre_north)
        tile_path = tiles.get(quadkey(lat, lon, 9))
        buildings = load_buildings(tile_path, centre_east, centre_north) if tile_path else np.empty((0, 2))

        fig, ax = plt.subplots(figsize=(12, 12))
        if len(buildings) >= 5:
            labels = DBSCAN(eps=28.0, min_samples=3).fit(buildings).labels_
            for label in set(labels):
                mask = labels == label
                colour = "gray" if label == -1 else None
                ax.scatter(buildings[mask, 0], buildings[mask, 1], s=6,
                           c=None if label == -1 else [plt.cm.tab20(label % 20)],
                           alpha=0.85, label=f"cluster {label}" if label >= 0 else None)
        # BCMS phase notice centroids, numbered by phase number.
        for phase_number, notice in group.dropna(subset=["itm_easting", "itm_northing"]).iterrows():
            ax.scatter(float(notice["itm_easting"]), float(notice["itm_northing"]), marker="*", s=320,
                       c="red", edgecolors="black", zorder=5)
            ax.annotate(f"P{int(notice['phase_number']) if pd.notna(notice['phase_number']) else '?'}",
                        (float(notice["itm_easting"]), float(notice["itm_northing"])),
                        xytext=(6, 6), textcoords="offset points", fontsize=11, weight="bold", color="red")
        # OSM address points if present.
        osm_file = settings.RAW_DIR / "osm_pilot" / f"{dev_id.split('__')[1]}.geojson"
        if osm_file.exists():
            osm = json.loads(osm_file.read_text(encoding="utf-8"))
            addr_points = []
            for element in osm.get("elements", []):
                if element.get("type") == "node" and "addr:housenumber" in element.get("tags", {}):
                    elon, elat = element["lon"], element["lat"]
                    eeast, enorth = TO_ITM.transform(elon, elat)
                    if np.hypot(eeast - centre_east, enorth - centre_north) <= RADIUS_M:
                        addr_points.append((eeast, enorth))
            if addr_points:
                addr = np.array(addr_points)
                ax.scatter(addr[:, 0], addr[:, 1], marker="+", s=40, c="blue", alpha=0.9, label="OSM addresses")

        circle = plt.Circle((centre_east, centre_north), RADIUS_M, fill=False, color="black", linestyle="--", linewidth=1)
        ax.add_patch(circle)
        ax.set_aspect("equal")
        phase_units = sorted(group["houses"].dropna().astype(int).tolist(), reverse=True)
        ax.set_title(f"{dev_id}\nBCMS phases: {len(group)} (units {phase_units[:8]})\nclusters: coloured blocks | red stars = phase notice points")
        ax.legend(loc="lower right", fontsize=7, ncol=2)
        out_png = OUT_DIR / f"{dev_id.split('__')[1]}.png"
        fig.savefig(out_png, dpi=110)
        plt.close(fig)

        review_rows.append({
            "development_id": dev_id,
            "map_png": str(out_png),
            "buildings_shown": int(len(buildings)),
            "bcms_phases": len(group),
            "bcms_phase_units": str(phase_units[:8]),
            "which_clusters_match_which_phases": "",
            "verdict_notes": "",
        })

    review = pd.DataFrame(review_rows)
    review.to_csv(OUT_DIR / "review_sheet.csv", index=False)
    print(json.dumps({"maps_rendered": len(review_rows), "out_dir": str(OUT_DIR),
                      "review_sheet": str(OUT_DIR / "review_sheet.csv")}, indent=2))
