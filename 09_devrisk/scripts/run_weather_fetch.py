"""Met Eireann weather fetch: nearest-station daily observations per site.

Uses the OGC EDR position query (nearest station + timeseries):
GET /edr/collections/{collection}/position?coords=POINT(lon lat)
   &parameter-name=...&datetime=2018-01-01T00:00:00/2026-10-31T23:59:59&limit=20000
Outputs: silver/imagery/weather_monthly.csv (site x month aggregates:
rainfall_total, wet_days_gt5, mean_temp, frost_days, n_days).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "imagery"
BASE = "https://opendata2.met.ie/edr"


def get(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 research"})
    with urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    colls = get(f"{BASE}/collections")
    ids = [c["id"] for c in colls.get("collections", [])]
    print("collections:", ids, flush=True)
    daily = next((i for i in ids if "daily" in i.lower() or "obs" in i.lower()), ids[0])
    print("using collection:", daily, flush=True)

    cohort = pd.read_csv(OUT / "feasibility_50.csv", dtype=str)
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "ITMEasting", "ITMNorthing"])
    reg = reg.drop_duplicates("case_key")
    import pyproj  # noqa: F401
    transformer = pyproj.Transformer.from_crs("EPSG:2157", "EPSG:4326", always_xy=True)
    rows = []
    for _, r in cohort.iterrows():
        rr = reg[reg["case_key"] == r["case_key"]]
        if rr.empty:
            continue
        lon, lat = transformer.transform(float(rr["ITMEasting"].iloc[0]),
                                         float(rr["ITMNorthing"].iloc[0]))
        site = {}
        for param in ("rainfall", "temperature"):
            url = (f"{BASE}/collections/{daily}/position?"
                   f"coords={quote(f'POINT({lon:.5f} {lat:.5f})')}"
                   f"&parameter-name={param}"
                   f"&datetime=2018-01-01T00:00:00/2026-10-31T23:59:59&limit=20000")
            try:
                data = get(url)
                features = data.get("features", [])
                vals = []
                for f in features:
                    t = f["properties"].get("phenomenonTime") or f["properties"].get("time")
                    v = f["properties"].get("value") or f["properties"].get("result")
                    if t and v is not None:
                        vals.append((str(t)[:10], float(v)))
                site[param] = vals
            except Exception as exc:
                print(f"  {r['case_key']} {param} error: {str(exc)[:80]}", flush=True)
            time.sleep(0.4)
        if not site.get("rainfall") and not site.get("temperature"):
            continue
        df_r = pd.DataFrame(site.get("rainfall", []), columns=["date", "rain"])
        df_t = pd.DataFrame(site.get("temperature", []), columns=["date", "temp"])
        merged = df_r.merge(df_t, on="date", how="outer")
        if len(merged):
            merged["ym"] = merged["date"].str[:7]
            agg = merged.groupby("ym").agg(
                rainfall_total=("rain", "sum"),
                wet_days_gt5=("rain", lambda s: (s > 5).sum()),
                mean_temp=("temp", "mean"),
                frost_days=("temp", lambda s: (s < 0).sum()),
                n_days=("date", "count")).reset_index()
            agg["development_id"] = r["case_key"]
            rows.append(agg)
            print(f"{r['case_key'][:40]} {len(agg)} months", flush=True)
        time.sleep(0.5)
    if rows:
        frame = pd.concat(rows, ignore_index=True)
        frame.to_csv(OUT / "weather_monthly.csv", index=False)
        print("weather rows:", len(frame), flush=True)
    else:
        print("no weather data returned", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
