"""Runner: pull the full 4Dublin Pipeline_All feature layer (paginated).

Fields include planning references, SHD type, LA decision, appeals, ABP
references, final-grant dates, JUDICIAL REVIEW references/conclusions,
activity-on-site, units completed/under construction, and ITM coordinates -
a Dublin-region goldmine for engines b/f/h and the JR positive-events table.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import requests  # noqa: E402

from devrisk import settings  # noqa: E402

URL = "https://services.arcgis.com/NzlPQPKn5QF9v2US/arcgis/rest/services/4Dublin_Pipeline_All/FeatureServer/59/query"
HEADERS = {"User-Agent": "Mozilla/5.0 planning-risk-review/1.0 (local research)"}
PAGE = 1000


if __name__ == "__main__":
    all_rows = []
    offset = 0
    while True:
        response = requests.get(
            URL,
            params={
                "where": "1=1",
                "outFields": "*",
                "f": "json",
                "returnGeometry": "false",
                "resultRecordCount": PAGE,
                "resultOffset": offset,
            },
            timeout=180,
            headers=HEADERS,
        )
        payload = response.json()
        features = payload.get("features", [])
        if not features:
            break
        all_rows.extend(feature.get("attributes", {}) for feature in features)
        if len(features) < PAGE:
            break
        offset += PAGE
        print(f"fetched {len(all_rows)} so far", flush=True)

    frame = pd.DataFrame(all_rows).drop_duplicates(subset=["OBJECTID"])
    out = settings.SILVER_DIR / "4dublin" / "pipeline_all.csv"
    frame.to_csv(out, index=False)

    summary = {
        "records": int(len(frame)),
        "authorities": sorted(frame["Planning_Authority"].dropna().unique().tolist()) if "Planning_Authority" in frame.columns else [],
        "with_jr_reference": int(frame["JR_Reference"].notna().sum()) if "JR_Reference" in frame.columns else 0,
        "subject_to_live_jr": int(frame["Subject_to_Live_JR"].notna().sum()) if "Subject_to_Live_JR" in frame.columns else 0,
        "units_completed_total": float(frame["Units_Completed_or_Completed_an"].fillna(0).sum()) if "Units_Completed_or_Completed_an" in frame.columns else 0,
        "out_path": str(out),
    }
    (settings.SILVER_DIR / "4dublin" / "pipeline_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
