#!/usr/bin/env python3
"""
wkb_to_itm_and_flood_end_to_end.py

End-to-end pipeline:
1) Read an input CSV that contains a WKB geometry column (Point)
2) Parse WKB -> Point -> create ITMEasting / ITMNorthing (EPSG:2157)
   - Auto-detects whether the point coords look like lon/lat (EPSG:4326) vs ITM (EPSG:2157)
3) Add flood extent features (hit within BUFFER + distance to nearest polygon) from selected shapefiles
4) Add flood depth features from selected GeoTIFFs (band 1), COLLAPSING tiles on-the-fly into:
      flood_depth__nifm__rp20__m, rp100, rp1000
      flood_depth__ncfhm__rp2__m, rp5, rp10, rp20, rp50, rp100, rp200, rp1000
   plus matching __has flags
   - NaN depth is treated as "not flooded" -> filled with 0.0
5) Add compact summary features:
      coastal_depth_max_m, fluvial_depth_max_m
      coastal_hit_any, fluvial_hit_any
      coastal_min_dist_m, fluvial_min_dist_m
      coastal_min_logdist, fluvial_min_logdist
6) Write a NEW output CSV (never overwrites input)

Install:
  pip install pandas numpy geopandas shapely pyproj rasterio

Notes:
- Requires GeoPandas spatial index support (recommended: pip install rtree)
- Set BASE_DIR to your flood_data folder.
"""

from __future__ import annotations

import ast
import base64
import re
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely import wkb as shapely_wkb
from shapely.geometry import Point
from pyproj import Transformer
import rasterio

# -----------------------
# CONFIG
# -----------------------
BASE_DIR = Path(r"flood_data")

INPUT_CSV = Path(r"greater_than_15_units_data.csv")
GEOM_COL = "geometry"  # WKB column name in your CSV

# Output
OUTPUT_SUFFIX = "_with_itm__flood_model"

# CRS
EPSG_ITM = 2157
EPSG_WGS84 = 4326

# If you KNOW the WKB is in a specific CRS, set this to 2157 or 4326. Otherwise "auto".
INPUT_WKB_EPSG: str | int = "auto"  # "auto" or 2157 or 4326

# Flood extent features use buffered points (meters)
BUFFER_M = 50.0

# Which flood folders/files to include/exclude (substring match on full path)
INCLUDE_EXTENT_KEYWORDS = [
    "nifm_ext_f_c",                      # fluvial extents
    "ncfhm_itm_ext_c_c",                 # coastal extents
    "cfram_area_for_further_assessment", # AFA boundaries (optional but useful)
]
INCLUDE_DEPTH_KEYWORDS = [
    "nifm_dep_f_c",        # fluvial depth rasters
    "ncfhm_itm_dep_c_c",   # coastal depth rasters
]
EXCLUDE_KEYWORDS = [
    "esds_floodmap",       # skip ESDS layers (slow/redundant)
]

# Depth return periods to parse from filenames
RP_CODES = {"0002", "0005", "0010", "0020", "0050", "0100", "0200", "1000"}
RP_RE = re.compile(r"_(" + "|".join(sorted(RP_CODES)) + r")_")

# -----------------------
# Helpers
# -----------------------
def safe_output_path(input_csv: Path, suffix: str) -> Path:
    base = input_csv.with_suffix("")
    out = Path(str(base) + suffix + ".csv")
    if not out.exists():
        return out
    ts = time.strftime("%Y%m%d_%H%M%S")
    return Path(str(base) + suffix + f"__{ts}.csv")


def sanitize(name: str, max_len: int = 80) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()
    return s[:max_len] if len(s) > max_len else s


def matches_any(path: Path, keywords: List[str]) -> bool:
    p = str(path).lower()
    return any(k.lower() in p for k in keywords)


def matches_none(path: Path, keywords: List[str]) -> bool:
    p = str(path).lower()
    return all(k.lower() not in p for k in keywords)


def parse_wkb_cell(v) -> Optional[Point]:
    """
    Accepts:
      - bytes
      - hex string
      - python bytes-literal string like: b"\\x01\\x01..."
    Returns shapely Point or None.
    """
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None

    b: Optional[bytes] = None

    if isinstance(v, (bytes, bytearray, memoryview)):
        b = bytes(v)
    else:
        s = str(v).strip()
        if not s:
            return None

        # Fix common CSV quoting artifact: b""\x01..."" -> b"\x01..."
        if s.startswith('b""'):
            s = s.replace('b""', 'b"', 1)
        if s.endswith('""'):
            s = s[:-2] + '"'
        s = s.replace('""', '"')

        # python bytes-literal?
        if s.startswith("b'") or s.startswith('b"'):
            try:
                lit = ast.literal_eval(s)
                if isinstance(lit, (bytes, bytearray)):
                    b = bytes(lit)
            except Exception:
                b = None

        # hex WKB?
        if b is None:
            s2 = s[2:] if s.lower().startswith("0x") else s
            if re.fullmatch(r"[0-9A-Fa-f]+", s2) and (len(s2) % 2 == 0):
                b = bytes.fromhex(s2)

        # base64?
        if b is None:
            try:
                b = base64.b64decode(s, validate=True)
            except Exception:
                b = None

    if b is None:
        return None

    geom = shapely_wkb.loads(b)
    if geom is None or geom.is_empty:
        return None
    if geom.geom_type != "Point":
        raise ValueError(f"WKB geometry is not a Point: {geom.geom_type}")
    return geom


def guess_input_epsg(x: float, y: float) -> int:
    # If it looks like lon/lat
    if -20.0 <= x <= 20.0 and 40.0 <= y <= 70.0:
        return EPSG_WGS84
    # If it looks like ITM meters
    if 0.0 <= x <= 1_000_000.0 and 0.0 <= y <= 1_500_000.0:
        return EPSG_ITM
    # fallback to ITM
    return EPSG_ITM


def build_points_from_wkb(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    geoms = df[GEOM_COL].apply(parse_wkb_cell)
    if geoms.isna().any():
        # allow some missing, but not all
        if geoms.notna().sum() == 0:
            raise ValueError(f"All values in {GEOM_COL} failed to parse as WKB Points.")

    xs = geoms.apply(lambda g: g.x if g is not None else np.nan).to_numpy(dtype="float64")
    ys = geoms.apply(lambda g: g.y if g is not None else np.nan).to_numpy(dtype="float64")

    # Determine CRS handling
    if INPUT_WKB_EPSG == "auto":
        # guess from median of non-nan
        mask = np.isfinite(xs) & np.isfinite(ys)
        if mask.sum() == 0:
            raise ValueError("No valid point coordinates after parsing WKB.")
        epsg_in = guess_input_epsg(float(np.nanmedian(xs[mask])), float(np.nanmedian(ys[mask])))
    else:
        epsg_in = int(INPUT_WKB_EPSG)

    if epsg_in == EPSG_ITM:
        easting, northing = xs, ys
    elif epsg_in == EPSG_WGS84:
        tr = Transformer.from_crs(EPSG_WGS84, EPSG_ITM, always_xy=True)
        easting, northing = tr.transform(xs, ys)
    else:
        tr = Transformer.from_crs(epsg_in, EPSG_ITM, always_xy=True)
        easting, northing = tr.transform(xs, ys)

    return np.asarray(easting, dtype="float64"), np.asarray(northing, dtype="float64")


def build_points_gdf(df: pd.DataFrame, easting: np.ndarray, northing: np.ndarray) -> gpd.GeoDataFrame:
    gdf = gpd.GeoDataFrame(
        df.copy(),
        geometry=[Point(xy) if np.isfinite(xy[0]) and np.isfinite(xy[1]) else None for xy in zip(easting, northing)],
        crs=f"EPSG:{EPSG_ITM}",
    )
    return gdf


def load_polygons_itm(shp_path: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(shp_path)
    if gdf.empty:
        return gdf
    if gdf.crs is None:
        raise ValueError(f"Shapefile has no CRS metadata: {shp_path}")
    return gdf.to_crs(epsg=EPSG_ITM)


def polygon_hit_distance(
    pts: gpd.GeoDataFrame,
    poly: gpd.GeoDataFrame,
    buffer_m: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    hit: buffered point intersects any polygon
    dist: distance to nearest polygon (0 if inside); NaN if no polygons
    """
    n = len(pts)
    hit = np.zeros(n, dtype=np.int8)
    dist = np.full(n, np.nan, dtype="float64")

    if poly.empty:
        return hit, dist

    # stable row ids
    pts_idx = pts.reset_index(drop=False).rename(columns={"index": "__rowid"})
    poly_idx = poly.reset_index(drop=True)

    # HIT: buffered intersects
    buffered = pts_idx.copy()
    buffered["geometry"] = buffered.geometry.buffer(buffer_m)

    try:
        j = gpd.sjoin(
            buffered[["__rowid", "geometry"]],
            poly_idx[["geometry"]],
            how="left",
            predicate="intersects",
        )
    except Exception as e:
        raise RuntimeError(
            "GeoPandas spatial join failed. Install spatial index support:\n"
            "  pip install rtree\n"
            f"Original error: {e}"
        )

    matched = j.loc[j["index_right"].notna(), "__rowid"].unique()
    hit[matched] = 1

    # DIST: nearest polygon distance
    try:
        jn = gpd.sjoin_nearest(
            pts_idx[["__rowid", "geometry"]],
            poly_idx[["geometry"]],
            how="left",
            distance_col="__dist",
        )
    except Exception as e:
        raise RuntimeError(
            "GeoPandas sjoin_nearest failed (version/index issue). Upgrade geopandas/shapely, and ensure spatial index:\n"
            "  pip install -U geopandas shapely rtree\n"
            f"Original error: {e}"
        )

    # in rare cases there can be multiple matches; take min distance
    dmin = jn.groupby("__rowid")["__dist"].min()
    dist[dmin.index.to_numpy(dtype=int)] = dmin.to_numpy(dtype="float64")

    return hit, dist


def add_polygon_layer_features(gdf_pts: gpd.GeoDataFrame, shp_path: Path, buffer_m: float) -> None:
    rel_parent = shp_path.parent.name
    stem = shp_path.stem
    key = sanitize(f"{rel_parent}__{stem}")

    poly = load_polygons_itm(shp_path)

    hit, dist = polygon_hit_distance(gdf_pts, poly, buffer_m) if not poly.empty else (np.zeros(len(gdf_pts), np.int8), np.full(len(gdf_pts), np.nan))
    gdf_pts[f"flood_ext__{key}__hit_{int(buffer_m)}m"] = hit
    gdf_pts[f"flood_ext__{key}__dist_m"] = np.round(dist, 3)


def tif_family_and_rp(tif_path: Path) -> Optional[Tuple[str, int]]:
    s = str(tif_path).lower()
    fam = None
    if "nifm" in s:
        fam = "nifm"
    elif "ncfhm" in s:
        fam = "ncfhm"
    else:
        return None

    m = RP_RE.search(s)
    if not m:
        return None
    rp_code = m.group(1)  # "0020"
    rp_int = int(rp_code)  # 20, 100, 1000, etc.
    return fam, rp_int


def update_depth_aggregators(
    agg: Dict[Tuple[str, int], np.ndarray],
    has: Dict[Tuple[str, int], np.ndarray],
    key: Tuple[str, int],
    vals: np.ndarray,
) -> None:
    mask = np.isfinite(vals)
    if key not in agg:
        agg[key] = np.full(vals.shape[0], np.nan, dtype="float64")
        has[key] = np.zeros(vals.shape[0], dtype=np.int8)

    cur = agg[key]
    cur_nan = np.isnan(cur)

    # fill where empty
    cur[cur_nan & mask] = vals[cur_nan & mask]
    # max where both present
    cur[~cur_nan & mask] = np.maximum(cur[~cur_nan & mask], vals[~cur_nan & mask])

    has[key][mask] = 1


def sample_raster(ds: rasterio.DatasetReader, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    nodata = ds.nodata
    out = np.full(xs.shape[0], np.nan, dtype="float64")
    for i, v in enumerate(ds.sample(list(zip(xs, ys)))):
        val = float(v[0])
        if nodata is not None and np.isfinite(val) and np.isclose(val, nodata):
            continue
        if not np.isfinite(val):
            continue
        out[i] = val
    return out


def main():
    if not BASE_DIR.exists():
        raise FileNotFoundError(f"BASE_DIR does not exist: {BASE_DIR}")
    if not INPUT_CSV.exists():
        raise FileNotFoundError(f"INPUT_CSV does not exist: {INPUT_CSV}")

    out_csv = safe_output_path(INPUT_CSV, OUTPUT_SUFFIX)

    df = pd.read_csv(INPUT_CSV, low_memory=False)
    if GEOM_COL not in df.columns:
        raise ValueError(f"Geometry column '{GEOM_COL}' not found in CSV.")

    # 1) WKB -> ITM coords
    easting, northing = build_points_from_wkb(df)
    df["ITMEasting"] = np.round(easting, 3)
    df["ITMNorthing"] = np.round(northing, 3)

    # 2) GeoDataFrame
    gdf_pts = build_points_gdf(df, easting, northing)

    # 3) Find relevant shapefiles/rasters
    shp_files = sorted([
        p for p in BASE_DIR.rglob("*.shp")
        if matches_any(p, INCLUDE_EXTENT_KEYWORDS) and matches_none(p, EXCLUDE_KEYWORDS)
    ])
    tif_files = sorted([
        p for p in list(BASE_DIR.rglob("*.tif")) + list(BASE_DIR.rglob("*.tiff"))
        if matches_any(p, INCLUDE_DEPTH_KEYWORDS) and matches_none(p, EXCLUDE_KEYWORDS)
    ])

    print(f"Found {len(shp_files)} extent shapefiles and {len(tif_files)} depth rasters", flush=True)

    # 4) Extent features
    for i, shp in enumerate(shp_files, 1):
        t0 = time.time()
        print(f"[{i}/{len(shp_files)}] Extent: {shp.name}", flush=True)
        add_polygon_layer_features(gdf_pts, shp, BUFFER_M)
        print(f"    done in {time.time()-t0:.1f}s", flush=True)

    # 5) Depth features (collapsed by family + return period on-the-fly)
    agg: Dict[Tuple[str, int], np.ndarray] = {}
    has: Dict[Tuple[str, int], np.ndarray] = {}

    for i, tif in enumerate(tif_files, 1):
        fr = tif_family_and_rp(tif)
        if fr is None:
            continue
        fam, rp = fr

        t0 = time.time()
        print(f"[{i}/{len(tif_files)}] Depth: {tif.name}  -> ({fam}, rp{rp})", flush=True)

        with rasterio.open(tif) as ds:
            if ds.crs is None:
                raise ValueError(f"Raster has no CRS metadata: {tif}")

            if ds.crs.to_epsg() == EPSG_ITM:
                xs = gdf_pts.geometry.x.to_numpy()
                ys = gdf_pts.geometry.y.to_numpy()
            else:
                tr = Transformer.from_crs(EPSG_ITM, ds.crs, always_xy=True)
                xs, ys = tr.transform(gdf_pts.geometry.x.to_numpy(), gdf_pts.geometry.y.to_numpy())

            vals = sample_raster(ds, np.asarray(xs), np.asarray(ys))
            update_depth_aggregators(agg, has, (fam, rp), vals)

        print(f"    done in {time.time()-t0:.1f}s", flush=True)

    # add aggregated depth columns (+ has flags), fill NaN->0
    for (fam, rp), arr in sorted(agg.items(), key=lambda x: (x[0][0], x[0][1])):
        col = f"flood_depth__{fam}__rp{rp}__m"
        gdf_pts[col] = arr
        gdf_pts[col + "__has"] = has[(fam, rp)]
        gdf_pts[col] = pd.to_numeric(gdf_pts[col], errors="coerce").fillna(0.0)

    # 6) Compact summary features
    depth_cols = [c for c in gdf_pts.columns if c.startswith("flood_depth__") and c.endswith("__m")]
    fluvial_depth = [c for c in depth_cols if "__nifm__" in c]
    coastal_depth = [c for c in depth_cols if "__ncfhm__" in c]

    hit_cols = [c for c in gdf_pts.columns if c.startswith("flood_ext__") and c.endswith(f"__hit_{int(BUFFER_M)}m")]
    dist_cols = [c for c in gdf_pts.columns if c.startswith("flood_ext__") and c.endswith("__dist_m")]

    fluvial_hit = [c for c in hit_cols if "__nifm_" in c]
    coastal_hit = [c for c in hit_cols if "__ncfhm_" in c]
    fluvial_dist = [c for c in dist_cols if "__nifm_" in c]
    coastal_dist = [c for c in dist_cols if "__ncfhm_" in c]

    gdf_pts["fluvial_depth_max_m"] = gdf_pts[fluvial_depth].max(axis=1) if fluvial_depth else 0.0
    gdf_pts["coastal_depth_max_m"] = gdf_pts[coastal_depth].max(axis=1) if coastal_depth else 0.0

    gdf_pts["fluvial_hit_any"] = gdf_pts[fluvial_hit].max(axis=1).fillna(0).astype(np.int8) if fluvial_hit else 0
    gdf_pts["coastal_hit_any"] = gdf_pts[coastal_hit].max(axis=1).fillna(0).astype(np.int8) if coastal_hit else 0

    gdf_pts["fluvial_min_dist_m"] = gdf_pts[fluvial_dist].min(axis=1) if fluvial_dist else np.nan
    gdf_pts["coastal_min_dist_m"] = gdf_pts[coastal_dist].min(axis=1) if coastal_dist else np.nan

    gdf_pts["fluvial_min_logdist"] = np.log1p(pd.to_numeric(gdf_pts["fluvial_min_dist_m"], errors="coerce"))
    gdf_pts["coastal_min_logdist"] = np.log1p(pd.to_numeric(gdf_pts["coastal_min_dist_m"], errors="coerce"))

    # fill any missing min distances with a sensible large value (so models don't see NaN)
    for base in ["fluvial_min_dist_m", "coastal_min_dist_m"]:
        if gdf_pts[base].isna().any():
            mx = gdf_pts[base].max(skipna=True)
            gdf_pts[base] = gdf_pts[base].fillna(mx if pd.notna(mx) else 0.0)
    for base in ["fluvial_min_logdist", "coastal_min_logdist"]:
        if gdf_pts[base].isna().any():
            mx = gdf_pts[base].max(skipna=True)
            gdf_pts[base] = gdf_pts[base].fillna(mx if pd.notna(mx) else 0.0)

    # 7) Write output (no overwrite)
    out_df = pd.DataFrame(gdf_pts.drop(columns=["geometry"]))
    out_df.to_csv(out_csv, index=False)

    print("Input:", INPUT_CSV, flush=True)
    print("Output:", out_csv, flush=True)
    print(f"Added depth columns: {len([c for c in out_df.columns if c.startswith('flood_depth__') and c.endswith('__m')])}", flush=True)
    print(f"Total columns: {out_df.shape[1]}", flush=True)


if __name__ == "__main__":
    main()
