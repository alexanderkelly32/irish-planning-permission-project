"""Runner: retry the blocked scrapes with Scrapling (user standard).

iDocsWeb document flow with a stealth session: AppFileRefDetails ->
copyright page -> chkAgree postback -> document list -> download
site-layout/phasing files for the 9 pilot estates. Then probe the other
blocked endpoints (eircode products, gov.ie search, excavations).
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

OUT_DIR = settings.RAW_DIR / "site_layouts"
STATE_PATH = settings.SILVER_DIR / "site_layouts_scrapling_state.json"
HIDDEN_RE = re.compile(r'<input[^>]+type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"')
LAYOUT_RE = re.compile(r"site\s*layout|layout\s*plan|phasing|master\s*plan|overall\s*site", re.IGNORECASE)


def load_state() -> dict:
    return json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {"done": {}, "failed": {}}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state), encoding="utf-8")


def run(limit: int = 0) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    shortlist = pd.read_csv(settings.SILVER_DIR / "phase_pilot_shortlist.csv")
    base = pd.read_csv(settings.ROOT / "01_flood" / "current" / "ge10_with_flooding.csv",
                       usecols=["PlanningAuthority", "ApplicationNumber", "LinkAppDetails"], low_memory=False)
    queue = []
    for _, row in shortlist.iterrows():
        match = base[(base["PlanningAuthority"] == str(row["authority"])) & (base["ApplicationNumber"].astype(str) == str(row["appno"]))]
        if len(match):
            queue.append({"appno": str(row["appno"]), "url": str(match.iloc[0]["LinkAppDetails"])})
    if limit:
        queue = queue[:limit]

    report = {"queued": len(queue), "downloaded": 0, "done": 0, "failed": 0}
    for item in queue:
        key = item["appno"]
        if key in state["done"] or key in state["failed"]:
            continue
        try:
            fetcher = StealthyFetcher()
            page = fetcher.fetch(item["url"], timeout=60000)
            idocs = re.search(r"https?://[^'\"]*iDocsWebDPSS[^'\"]*", page.html_content)
            if not idocs:
                state["failed"][key] = "no iDocsWeb url"
                report["failed"] += 1
                save_state(state)
                continue
            copyright_url = idocs.group(0).replace("&amp;", "&")
            agree_page = fetcher.fetch(copyright_url, timeout=60000)
            hidden = {name: value for name, value in HIDDEN_RE.findall(agree_page.html_content)}
            payload = {
                "__EVENTTARGET": "chkAgree",
                "__EVENTARGUMENT": "",
                "__VIEWSTATE": hidden.get("__VIEWSTATE", ""),
                "__EVENTVALIDATION": hidden.get("__EVENTVALIDATION", ""),
                "__VIEWSTATEGENERATOR": hidden.get("__VIEWSTATEGENERATOR", ""),
                "chkAgree": "on",
            }
            listing = fetcher.fetch(copyright_url, method="POST", body=payload, timeout=60000)
            saved = 0
            for href in re.findall(r'href="([^"]+)"', listing.html_content):
                label = href.rsplit("/", 1)[-1]
                if not re.search(r"pdf|tif|jpg|ashx|download|document", href, re.IGNORECASE):
                    continue
                if not LAYOUT_RE.search(label) and not LAYOUT_RE.search(urllib_parse_unquote(label)):
                    continue
                absolute = href if href.startswith("http") else copyright_url.rsplit("/", 1)[0] + "/" + href
                try:
                    blob = fetcher.fetch(absolute, timeout=120000)
                    if len(blob.body) < 5000:
                        continue
                    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", urllib_parse_unquote(label))[:70]
                    (OUT_DIR / f"{key}_{safe}").write_bytes(blob.body)
                    saved += 1
                except Exception:
                    continue
                time.sleep(0.5)
            state["done"][key] = {"files_saved": saved}
            report["downloaded"] += saved
            report["done"] += 1
        except Exception as exc:
            state["failed"][key] = str(exc)[:200]
            report["failed"] += 1
        save_state(state)
        time.sleep(1.5)

    (settings.SILVER_DIR / "site_layouts_scrapling_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return report


def urllib_parse_unquote(text: str) -> str:
    import urllib.parse
    return urllib.parse.unquote(text)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    run(limit=args.limit)
