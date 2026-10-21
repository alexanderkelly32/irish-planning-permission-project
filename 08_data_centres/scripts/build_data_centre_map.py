#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
from pyproj import Transformer
from shapely import wkb


ROOT = Path(__file__).resolve().parents[2]
LIKELY_CSV = ROOT / "08_data_centres" / "source_data" / "likely_data_centres.csv"
RELATED_CSV = ROOT / "08_data_centres" / "source_data" / "data_centre_related_applications.csv"
AMBIGUOUS_BUCKETED_CSV = ROOT / "08_data_centres" / "source_data" / "ambiguous_data_centres_bucketed.csv"
OUTPUT_CSV = ROOT / "08_data_centres" / "source_data" / "data_centres_map_ready.csv"
OUTPUT_HTML = ROOT / "08_data_centres" / "current" / "data_centres_map.html"
OUTPUT_PNG = ROOT / "08_data_centres" / "current" / "data_centres_overview.png"
SUMMARY_JSON = ROOT / "08_data_centres" / "current" / "data_centres_map_summary.json"
MAP_REFERENCE_DATE = datetime(2026, 4, 14, tzinfo=timezone.utc)

SOURCE_STYLE = {
    "likely_data_centre": {"color": "#0f766e", "label": "Primary data-centre applications"},
    "promote_primary_data_centre": {"color": "#14b8a6", "label": "Reviewed mixed-use / promoted primary"},
    "promote_small_specialised_data_centre": {"color": "#d97706", "label": "Small or specialised data-centres"},
    "data_centre_related_application": {"color": "#7c3aed", "label": "Related applications"},
    "promote_related_application": {"color": "#a78bfa", "label": "Reviewed related applications"},
}

DECISION_STYLE = {
    "granted": {"color": "#2b6cb0", "label": "Granted / conditional / unconditional"},
    "rejected": {"color": "#c53030", "label": "Rejected / refused / invalid"},
    "pending": {"color": "#dd6b20", "label": "Undecided / other"},
}

AGE_STYLE = {
    "newer": {"color": "#2f855a", "label": "0 to <2 years old"},
    "mid": {"color": "#d69e2e", "label": "2 to <5 years old"},
    "older": {"color": "#805ad5", "label": "5+ years old"},
    "unknown": {"color": "#718096", "label": "Unknown age"},
}

ITM_TO_WGS84 = Transformer.from_crs("EPSG:2157", "EPSG:4326", always_xy=True)
WEBMERCATOR_TO_WGS84 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)

LEAFLET_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Data Centres Ireland</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <style>
    html, body, #map { height: 100%; margin: 0; }
    body { font-family: Arial, sans-serif; }
    .legend {
      background: rgba(255,255,255,0.95);
      padding: 10px 12px;
      line-height: 1.4;
      border-radius: 6px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.3);
    }
    .legend .row {
      display: flex;
      align-items: center;
      margin: 4px 0;
      gap: 8px;
      white-space: nowrap;
    }
    .legend .swatch {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      display: inline-block;
    }
    .legend .swatch-ring {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      display: inline-block;
      background: transparent;
      border: 3px solid #111;
      box-sizing: border-box;
    }
  </style>
</head>
<body>
  <div id="map"></div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script src="https://unpkg.com/leaflet.heat/dist/leaflet-heat.js"></script>
  <script>
    const points = __POINTS__;
    const heatPoints = __HEAT_POINTS__;
    const map = L.map('map', { preferCanvas: true });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18,
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);

    const groups = {
      primary: L.layerGroup(),
      small_specialised: L.layerGroup(),
      related: L.layerGroup(),
      age_overlay: L.layerGroup()
    };

    const labelMap = __LABEL_MAP__;
    const decisionStyleMap = __DECISION_STYLE_MAP__;
    const ageStyleMap = __AGE_STYLE_MAP__;

    const bounds = [];
    for (const point of points) {
      const decisionStyle = decisionStyleMap[point.decision_bucket];
      const emphasized = point.source_category === 'promote_small_specialised_data_centre';
      const marker = L.circleMarker([point.lat, point.lon], {
        radius: emphasized ? 8 : 6,
        color: emphasized ? '#111111' : decisionStyle.color,
        fillColor: decisionStyle.color,
        fillOpacity: emphasized ? 0.9 : 0.78,
        weight: emphasized ? 2.5 : 1
      });

      const planningLink = point.link_app_details
        ? `<a href="${point.link_app_details}" target="_blank" rel="noopener noreferrer">Open planning file</a><br/>`
        : '';
      const reviewNote = point.review_note ? `Review note: ${point.review_note}<br/>` : '';
      const popup = `
        <strong>${point.planning_authority}</strong><br/>
        Application: ${point.application_number}<br/>
        Category: ${labelMap[point.source_category]}<br/>
        Decision: ${point.decision || 'n/a'}<br/>
        Received: ${point.received_date || 'n/a'}<br/>
        Age: ${point.age_years !== null && point.age_years !== '' ? Number(point.age_years).toFixed(1) + ' years' : 'n/a'}<br/>
        Floor area (sqm): ${point.floor_area_sqm_best || point.floor_area || 'n/a'}<br/>
        Area (ha): ${point.site_area_ha_best || point.area_of_site || 'n/a'}<br/>
        ${planningLink}
        ${reviewNote}
        <div style="margin-top:6px; max-width:380px;">${point.description_html}</div>
      `;
      marker.bindPopup(popup);

      if (point.source_category === 'likely_data_centre' || point.source_category === 'promote_primary_data_centre') {
        marker.addTo(groups.primary);
      } else if (point.source_category === 'promote_small_specialised_data_centre') {
        marker.addTo(groups.small_specialised);
      } else {
        marker.addTo(groups.related);
      }

      const ageStyle = ageStyleMap[point.age_bucket];
      const ageRing = L.circleMarker([point.lat, point.lon], {
        radius: 11,
        color: ageStyle.color,
        fillOpacity: 0,
        opacity: 0.8,
        weight: 2,
        interactive: false
      });
      ageRing.addTo(groups.age_overlay);
      bounds.push([point.lat, point.lon]);
    }

    const heatLayer = L.heatLayer(heatPoints, {
      radius: 25,
      blur: 20,
      maxZoom: 10
    });

    groups.primary.addTo(map);
    groups.small_specialised.addTo(map);
    heatLayer.addTo(map);

    if (bounds.length) {
      map.fitBounds(bounds, { padding: [24, 24] });
    } else {
      map.setView([53.3, -8.0], 7);
    }

    const overlays = {
      'Primary data centres': groups.primary,
      'Small / specialised data centres': groups.small_specialised,
      'Related applications': groups.related,
      'Application age': groups.age_overlay,
      'Unique-site density': heatLayer
    };
    L.control.layers(null, overlays, { collapsed: false }).addTo(map);

    const legend = L.control({ position: 'bottomright' });
    legend.onAdd = function() {
      const div = L.DomUtil.create('div', 'legend');
      div.innerHTML = `
        <div><strong>Data Centre Map</strong></div>
        <div class="row"><span class="swatch" style="background:${decisionStyleMap.granted.color}"></span>Granted / conditional / unconditional</div>
        <div class="row"><span class="swatch" style="background:${decisionStyleMap.rejected.color}"></span>Rejected / refused / invalid</div>
        <div class="row"><span class="swatch" style="background:${decisionStyleMap.pending.color}"></span>Undecided / other</div>
        <div class="row"><span class="swatch-ring"></span>Small / specialised promoted case</div>
        <div style="margin-top:6px;"><strong>Age overlay</strong></div>
        <div class="row"><span class="swatch-ring" style="border-color:${ageStyleMap.newer.color}"></span>0 to &lt;2 years</div>
        <div class="row"><span class="swatch-ring" style="border-color:${ageStyleMap.mid.color}"></span>2 to &lt;5 years</div>
        <div class="row"><span class="swatch-ring" style="border-color:${ageStyleMap.older.color}"></span>5+ years</div>
        <div class="row"><span class="swatch-ring" style="border-color:${ageStyleMap.unknown.color}"></span>Unknown</div>
        <div style="margin-top:6px; max-width:250px;">Heat layer uses unique coordinates to show rough site density. Some sites appear more than once because the planning history includes amendments or follow-on applications.</div>
      `;
      return div;
    };
    legend.addTo(map);
  </script>
</body>
</html>
"""


def normalize_field_size_limit() -> None:
    max_limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(max_limit)
            return
        except OverflowError:
            max_limit //= 10


def html_escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
        .replace("\n", " ")
    )


def decision_bucket(decision: str) -> str:
    text = (decision or "").strip().lower()
    if not text:
        return "pending"
    if any(token in text for token in ["refused", "reject", "invalid"]):
        return "rejected"
    if any(token in text for token in ["grant", "conditional", "unconditional", "permission", "retention"]):
        return "granted"
    return "pending"


def parse_date(text: str) -> datetime | None:
    raw = (text or "").strip()
    if not raw:
        return None
    cleaned = raw.replace("Z", "+00:00")
    for candidate in [cleaned]:
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass
    for fmt in ["%Y/%m/%d %H:%M:%S+00", "%Y-%m-%d %H:%M:%S+00:00", "%Y-%m-%d"]:
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def age_years(received_date: str) -> float | None:
    parsed = parse_date(received_date)
    if not parsed:
        return None
    return max((MAP_REFERENCE_DATE - parsed).days / 365.25, 0.0)


def age_bucket(received_date: str) -> str:
    years = age_years(received_date)
    if years is None:
        return "unknown"
    if years < 2:
        return "newer"
    if years < 5:
        return "mid"
    return "older"


def parse_geometry_to_lon_lat(geometry_text: str) -> Tuple[float, float] | Tuple[None, None]:
    if not geometry_text:
        return (None, None)
    try:
        binary = ast.literal_eval(geometry_text)
        point = wkb.loads(binary)
        lon, lat = WEBMERCATOR_TO_WGS84.transform(point.x, point.y)
        return lon, lat
    except Exception:
        return (None, None)


def load_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def row_to_coords(row: Dict[str, str]) -> Tuple[float, float] | Tuple[None, None]:
    easting = row.get("ITMEasting", "")
    northing = row.get("ITMNorthing", "")
    if easting and northing:
        try:
            return ITM_TO_WGS84.transform(float(easting), float(northing))
        except Exception:
            pass
    return parse_geometry_to_lon_lat(row.get("geometry", ""))


def build_map_rows() -> List[Dict[str, str | float]]:
    rows: List[Dict[str, str | float]] = []

    def add_rows(source_path: Path, source_category: str, filter_fn=None) -> None:
        for row in load_rows(source_path):
            if filter_fn and not filter_fn(row):
                continue

            lon, lat = row_to_coords(row)
            if lon is None or lat is None:
                continue

            rows.append(
                {
                    "case_key": row.get("case_key", ""),
                    "planning_authority": row.get("PlanningAuthority", ""),
                    "application_number": row.get("ApplicationNumber", ""),
                    "decision": row.get("Decision", ""),
                    "decision_bucket": decision_bucket(row.get("Decision", "")),
                    "received_date": row.get("ReceivedDate", ""),
                    "age_years": age_years(row.get("ReceivedDate", "")),
                    "age_bucket": age_bucket(row.get("ReceivedDate", "")),
                    "source_category": source_category,
                    "source_reason": row.get("data_centre_reason", ""),
                    "review_note": row.get("ambiguous_review_note", ""),
                    "development_address": row.get("DevelopmentAddress", ""),
                    "site_area_ha_best": row.get("site_area_ha_best", ""),
                    "area_of_site": row.get("AreaofSite", ""),
                    "floor_area": row.get("FloorArea", ""),
                    "floor_area_sqm_best": row.get("floor_area_sqm_best", ""),
                    "link_app_details": row.get("LinkAppDetails", ""),
                    "lon": lon,
                    "lat": lat,
                    "description": " ".join((row.get("DevelopmentDescription", "") or "").split()),
                }
            )

    add_rows(LIKELY_CSV, "likely_data_centre")
    add_rows(RELATED_CSV, "data_centre_related_application")
    add_rows(
        AMBIGUOUS_BUCKETED_CSV,
        "promote_primary_data_centre",
        filter_fn=lambda row: row.get("ambiguous_review_bucket") == "promote_primary_data_centre",
    )
    add_rows(
        AMBIGUOUS_BUCKETED_CSV,
        "promote_small_specialised_data_centre",
        filter_fn=lambda row: row.get("ambiguous_review_bucket") == "promote_small_specialised_data_centre",
    )
    add_rows(
        AMBIGUOUS_BUCKETED_CSV,
        "promote_related_application",
        filter_fn=lambda row: row.get("ambiguous_review_bucket") == "promote_related_application",
    )
    return rows


def write_map_ready_csv(path: Path, rows: List[Dict[str, str | float]]) -> None:
    fieldnames = [
        "case_key",
        "planning_authority",
        "application_number",
        "decision",
        "decision_bucket",
        "received_date",
        "age_years",
        "age_bucket",
        "source_category",
        "source_reason",
        "review_note",
        "development_address",
        "site_area_ha_best",
        "area_of_site",
        "floor_area",
        "floor_area_sqm_best",
        "link_app_details",
        "lat",
        "lon",
        "description",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_html(path: Path, rows: List[Dict[str, str | float]]) -> None:
    point_payload = []
    unique_coords: Dict[Tuple[float, float], int] = defaultdict(int)
    for row in rows:
        lat = float(row["lat"])
        lon = float(row["lon"])
        unique_coords[(round(lat, 6), round(lon, 6))] += 1
        point_payload.append(
            {
                **row,
                "lat": lat,
                "lon": lon,
                "description_html": html_escape(str(row["description"]))[:1400],
            }
        )

    heat_points = [[lat, lon, 1] for (lat, lon), _count in unique_coords.items()]

    html = (
        LEAFLET_HTML.replace("__POINTS__", json.dumps(point_payload))
        .replace("__HEAT_POINTS__", json.dumps(heat_points))
        .replace("__DECISION_STYLE_MAP__", json.dumps(DECISION_STYLE))
        .replace("__AGE_STYLE_MAP__", json.dumps(AGE_STYLE))
        .replace("__LABEL_MAP__", json.dumps({key: value["label"] for key, value in SOURCE_STYLE.items()}))
    )
    path.write_text(html, encoding="utf-8")


def build_png(path: Path, rows: List[Dict[str, str | float]]) -> None:
    unique_coords = sorted({(round(float(row["lon"]), 5), round(float(row["lat"]), 5)) for row in rows})

    fig, axes = plt.subplots(1, 2, figsize=(14, 7), constrained_layout=True)
    ax_points, ax_density = axes

    for bucket in ["granted", "rejected", "pending"]:
        subset = [row for row in rows if row["decision_bucket"] == bucket]
        if not subset:
            continue
        ax_points.scatter(
            [float(row["lon"]) for row in subset],
            [float(row["lat"]) for row in subset],
            s=20,
            alpha=0.8,
            c=DECISION_STYLE[bucket]["color"],
            label=DECISION_STYLE[bucket]["label"],
        )

    emphasised = [row for row in rows if row["source_category"] == "promote_small_specialised_data_centre"]
    if emphasised:
        ax_points.scatter(
            [float(row["lon"]) for row in emphasised],
            [float(row["lat"]) for row in emphasised],
            s=70,
            facecolors="none",
            edgecolors="#111111",
            linewidths=1.4,
            label="Small / specialised promoted case",
        )

    if unique_coords:
        xs = [coord[0] for coord in unique_coords]
        ys = [coord[1] for coord in unique_coords]
        hb = ax_density.hexbin(xs, ys, gridsize=24, cmap="YlOrRd", mincnt=1)
        fig.colorbar(hb, ax=ax_density, label="Unique sites per hex")

    all_lons = [float(row["lon"]) for row in rows]
    all_lats = [float(row["lat"]) for row in rows]
    if all_lons and all_lats:
        x_margin = (max(all_lons) - min(all_lons)) * 0.08 or 0.3
        y_margin = (max(all_lats) - min(all_lats)) * 0.08 or 0.3
        xlim = (min(all_lons) - x_margin, max(all_lons) + x_margin)
        ylim = (min(all_lats) - y_margin, max(all_lats) + y_margin)
        ax_points.set_xlim(*xlim)
        ax_points.set_ylim(*ylim)
        ax_density.set_xlim(*xlim)
        ax_density.set_ylim(*ylim)

    ax_points.set_title("Data Centre Planning Applications")
    ax_points.set_xlabel("Longitude")
    ax_points.set_ylabel("Latitude")
    ax_points.legend(loc="lower left", fontsize=8)
    ax_points.grid(alpha=0.2)

    ax_density.set_title("Rough Density of Unique Data-Centre Sites")
    ax_density.set_xlabel("Longitude")
    ax_density.set_ylabel("Latitude")
    ax_density.grid(alpha=0.2)

    fig.suptitle("Ireland Data Centre Planning Map", fontsize=15)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def write_summary(path: Path, rows: List[Dict[str, str | float]]) -> None:
    by_category = Counter(str(row["source_category"]) for row in rows)
    by_age = Counter(str(row["age_bucket"]) for row in rows)
    unique_sites = len({(round(float(row["lat"]), 6), round(float(row["lon"]), 6)) for row in rows})
    summary = {
        "rows_plotted": len(rows),
        "unique_site_coordinates": unique_sites,
        "category_counts": dict(by_category),
        "age_bucket_counts": dict(by_age),
    }
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an interactive and static data-centre planning map.")
    parser.parse_args()

    normalize_field_size_limit()
    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    rows = build_map_rows()
    write_map_ready_csv(OUTPUT_CSV, rows)
    build_html(OUTPUT_HTML, rows)
    build_png(OUTPUT_PNG, rows)
    write_summary(SUMMARY_JSON, rows)

    print(
        json.dumps(
            {
                "map_ready_csv": str(OUTPUT_CSV),
                "html_map": str(OUTPUT_HTML),
                "png_preview": str(OUTPUT_PNG),
                "summary_json": str(SUMMARY_JSON),
                "rows_plotted": len(rows),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
