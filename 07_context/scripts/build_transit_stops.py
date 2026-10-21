"""Extract national transit stops from TFI GTFS and build per-application features."""
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

ROOT = Path(r"")
RAW = ROOT / "07_context" / "raw"
OUT = ROOT / "07_context" / "current"

zip_path = RAW / "GTFS_All.zip"
OUT.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(zip_path) as archive:
    names = [n for n in archive.namelist() if n.endswith("stops.txt")]
    print("stops files:", names)
    frames = []
    for n in names:
        frames.append(pd.read_csv(archive.open(n), dtype=str, usecols=lambda c: c in {"stop_id", "stop_name", "stop_lat", "stop_lon"}))
stops = pd.concat(frames, ignore_index=True).drop_duplicates("stop_id")
stops["stop_lat"] = pd.to_numeric(stops["stop_lat"], errors="coerce")
stops["stop_lon"] = pd.to_numeric(stops["stop_lon"], errors="coerce")
stops = stops.dropna(subset=["stop_lat", "stop_lon"])
print("unique stops:", len(stops))

from pyproj import Transformer

transformer = Transformer.from_crs("EPSG:4326", "EPSG:2157", always_xy=True)
eastings, northings = transformer.transform(stops["stop_lon"].to_numpy(), stops["stop_lat"].to_numpy())
stop_xy = np.column_stack([eastings, northings])
tree = cKDTree(stop_xy)
stops_out = pd.DataFrame({"stop_id": stops["stop_id"], "stop_name": stops["stop_name"], "ITMEasting": eastings, "ITMNorthing": northings})
stops_out.to_parquet(OUT / "national_transit_stops.parquet", index=False)
print("saved", len(stops_out), "stops")
