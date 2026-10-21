"""Runner: D. ePlan structured-field scrape (conditions count, site/floor
area, sewerage/water, extension-of-duration, unit mix) for the pool.

Re-scrapes the 1,595 pool eplanning pages with scrapling, parses the
Details/Development/Decision tabs' structured fields. Resume-safe.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
from scrapling import StealthyFetcher  # noqa: E402

from devrisk import settings  # noqa: E402

STATE_PATH = settings.SILVER_DIR / "eplan_fields_state.json"
OUT_PATH = settings.SILVER_DIR / "eplan_structured_fields.csv"

FIELD_RES = {
    "n_conditions": re.compile(r"Number of Conditions:\s*</[^>]+>\s*<[^>]+>\s*(\d+)", re.I),
    "decision_type": re.compile(r"Decision Type:\s*</[^>]+>\s*<[^>]+>\s*([A-Za-z ]+)", re.I),
    "sewerage": re.compile(r"(?:Sewerage|Foul|Wastewater)[^<]{0,80}", re.I),
    "water_type": re.compile(r"Water[^<]{0,60}(?:Supply|Source)", re.I),
    "floor_area": re.compile(r"Floor\s*Area[^<]{0,40}:?\s*</[^>]+>\s*<[^>]+>\s*([\d,.]+)", re.I),
    "site_area": re.compile(r"Site\s*Area[^<]{0,40}:?\s*</[^>]+>\s*<[^>]+>\s*([\d,.]+)", re.I),
    "extension_of_duration": re.compile(r"Extension of Duration", re.I),
    "previous_apps": re.compile(r"Previous Application|Previous Permission", re.I),
}


if __name__ == "__main__":
    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {"done": {}}
    base = pd.read_csv(settings.ROOT / "01_flood" / "current" / "ge10_with_flooding.csv",
                       usecols=["PlanningAuthority", "ApplicationNumber", "LinkAppDetails"], low_memory=False)
    rows = []
    done_keys = set(state["done"])
    for i, (_, app) in enumerate(base.iterrows()):
        key = f"{app['PlanningAuthority']}__{app['ApplicationNumber']}"
        if key in done_keys:
            continue
        url = str(app["LinkAppDetails"] or "")
        if "eplanning" not in url and "eplan." not in url:
            continue
        try:
            page = StealthyFetcher.fetch(url, timeout=60000)
            text = re.sub(r"<[^>]+>", " | ", page.html_content)
            text = re.sub(r"\|+", " | ", text)
            row = {"case_key": key}
            for name, pattern in FIELD_RES.items():
                match = pattern.search(text)
                row[name] = match.group(1).strip() if match and match.groups() else (1 if match else 0)
            rows.append(row)
        except Exception:
            pass
        state["done"][key] = 1
        if i % 100 == 0:
            STATE_PATH.write_text(json.dumps(state))
            print(f"processed {i}", flush=True)
        time.sleep(0.6)
    STATE_PATH.write_text(json.dumps(state))
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT_PATH, index=False)
    report = {"rows": int(len(frame)), "out": str(OUT_PATH)}
    (settings.SILVER_DIR / "eplan_fields_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
