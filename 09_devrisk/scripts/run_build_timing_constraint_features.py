"""Runner: submission-time-safe constraint features for timing models.

Per pool scheme: flood hits/depths (01_flood), nearest NIAH building, WWTP
point, TII counter (log distances + 500m counts), Natura 2000 proximity
(shapely STRtree), plus time-safe authority/local prior activation rates.
Writes timing_constraint_features.csv.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from shapely import STRtree, wkb  # noqa: E402
from shapely.geometry import Point  # noqa: E402

from devrisk import settings  # noqa: E402

if __name__ == "__main__":
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    frame = labels.merge(register[["case_key", "PlanningAuthority", "ApplicationNumber", "GrantDate",
                                   "ITMEasting", "ITMNorthing", "ReceivedDate"]], on="case_key", how="inner")
    frame["case_key"] = frame["case_key"].astype(str)
    frame["easting"] = pd.to_numeric(frame["ITMEasting"], errors="coerce")
    frame["northing"] = pd.to_numeric(frame["ITMNorthing"], errors="coerce")
    frame["grant_dt"] = pd.to_datetime(frame["GrantDate"], utc=True, errors="coerce")
    frame["received_dt"] = pd.to_datetime(frame["ReceivedDate"], utc=True, errors="coerce")

    # Flood features
    flood = pd.read_csv(settings.ROOT / "01_flood" / "current" / "ge10_with_flooding.csv")
    flood["_join"] = flood["PlanningAuthority"].astype(str).str.lower() + "__" + flood["ApplicationNumber"].astype(str)
    frame["_join"] = frame["PlanningAuthority"].astype(str).str.lower() + "__" + frame["ApplicationNumber"].astype(str)
    flood_cols = ["_join", "fluvial_hit_any", "coastal_hit_any", "coastal_min_logdist", "fluvial_min_logdist",
                  "flood_depth__ncfhm__rp100__m"]
    frame = frame.merge(flood[flood_cols], on="_join", how="left")

    # Point constraint layers
    niah = pd.read_parquet(settings.ROOT / "07_context" / "current" / "constraint_niah.parquet")
    wwtp = pd.read_parquet(settings.ROOT / "07_context" / "current" / "constraint_wwtp.parquet")
    traffic = pd.read_parquet(settings.ROOT / "07_context" / "current" / "constraint_traffic.parquet")

    def nearest_and_count(points: pd.DataFrame, east, north) -> tuple[float, int]:
        if points.empty:
            return np.nan, 0
        distance = np.hypot(points["itm_easting"].to_numpy() - east, points["itm_northing"].to_numpy() - north)
        return float(distance.min()), int((distance <= 500).sum())

    niah_rows, wwtp_rows, traffic_rows, natura_rows = [], [], [], []
    natura = pd.read_parquet(settings.ROOT / "07_context" / "current" / "constraint_natura.parquet")
    natura_geoms = [wkb.loads(g) if isinstance(g, (bytes, bytearray)) else g for g in natura["geometry"]]
    tree = STRtree(natura_geoms) if natura_geoms else None

    for _, scheme in frame.iterrows():
        east, north = scheme["easting"], scheme["northing"]
        if pd.isna(east) or pd.isna(north):
            niah_rows.append((np.nan, 0))
            wwtp_rows.append(np.nan)
            traffic_rows.append(np.nan)
            natura_rows.append(np.nan)
            continue
        niah_rows.append(nearest_and_count(niah, east, north))
        wwtp_rows.append(nearest_and_count(wwtp, east, north)[0])
        traffic_rows.append(nearest_and_count(traffic, east, north)[0])
        if tree is not None:
            point = Point(east, north)
            idx = tree.nearest(point)
            natura_rows.append(float(point.distance(natura_geoms[idx])))
        else:
            natura_rows.append(np.nan)

    frame["niah_min_dist"] = [np.log1p(r[0]) if not pd.isna(r[0]) else np.nan for r in niah_rows]
    frame["niah_count_500m"] = [r[1] for r in niah_rows]
    frame["wwtp_min_dist"] = [np.log1p(d) if not pd.isna(d) else np.nan for d in wwtp_rows]
    frame["traffic_min_dist"] = [np.log1p(d) if not pd.isna(d) else np.nan for d in traffic_rows]
    frame["natura_min_dist"] = [np.log1p(d) if not pd.isna(d) else np.nan for d in natura_rows]

    # Time-safe prior activation rates (authority + 5km local) at grant date.
    data = frame.sort_values("grant_dt").reset_index(drop=True)
    activation = pd.to_numeric(labels.set_index("case_key")["activation_linked"], errors="coerce").astype(bool).to_dict()
    auth_rate, local_rate = np.zeros(len(data)), np.zeros(len(data))
    received = data["received_dt"].to_numpy()
    authority = data["PlanningAuthority"].astype(str).to_numpy()
    east_arr = data["easting"].to_numpy()
    north_arr = data["northing"].to_numpy()
    act = data["case_key"].map(activation).fillna(False).astype(int).to_numpy()
    for i in range(len(data)):
        prior = received < received[i]
        auth_mask = prior & (authority == authority[i])
        if auth_mask.any():
            auth_rate[i] = act[auth_mask].mean()
        if not np.isnan(east_arr[i]):
            local_mask = prior & (np.hypot(east_arr - east_arr[i], north_arr - north_arr[i]) <= 5000.0)
            if local_mask.any():
                local_rate[i] = act[local_mask].mean()
    data["prior_auth_activation_rate"] = auth_rate
    data["prior_local_activation_rate"] = local_rate

    out_cols = ["case_key", "fluvial_hit_any", "coastal_hit_any", "coastal_min_logdist", "fluvial_min_logdist",
                "flood_depth__ncfhm__rp100__m", "niah_min_dist", "niah_count_500m", "wwtp_min_dist",
                "traffic_min_dist", "natura_min_dist", "prior_auth_activation_rate", "prior_local_activation_rate"]
    out = data[out_cols].copy()
    out_path = settings.SILVER_DIR / "timing_constraint_features.csv"
    out.to_csv(out_path, index=False)
    coverage = out.notna().mean().round(3).to_dict()
    print(json.dumps({"rows": int(len(out)), "out": str(out_path), "coverage": coverage}, indent=2))
