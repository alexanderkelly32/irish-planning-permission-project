"""Runner: iDocsWeb document pull via patchright browser (JS postback).

Scrapling StealthyFetcher locates each estate's iDocsWeb URL; patchright
(real Chrome) loads the copyright page, checks the agree checkbox, lets the
ASP.NET postback fire, then extracts and downloads site-layout/phasing
documents. Writes site_layouts/. Resume-safe.
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
STATE_PATH = settings.SILVER_DIR / "site_layouts_browser_state.json"
LAYOUT_RE = re.compile(r"site\s*layout|layout\s*plan|phasing|master\s*plan|overall\s*site", re.IGNORECASE)


def load_state() -> dict:
    return json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {"done": {}, "failed": {}}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state), encoding="utf-8")


def build_queue() -> list[dict]:
    shortlist = pd.read_csv(settings.SILVER_DIR / "phase_pilot_shortlist.csv")
    base = pd.read_csv(settings.ROOT / "01_flood" / "current" / "ge10_with_flooding.csv",
                       usecols=["PlanningAuthority", "ApplicationNumber", "LinkAppDetails"], low_memory=False)
    queue = []
    for _, row in shortlist.iterrows():
        match = base[(base["PlanningAuthority"] == str(row["authority"])) & (base["ApplicationNumber"].astype(str) == str(row["appno"]))]
        if len(match):
            queue.append({"appno": str(row["appno"]), "url": str(match.iloc[0]["LinkAppDetails"])})
    return queue


def run(limit: int = 0) -> dict:
    from patchright.sync_api import sync_playwright

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    queue = build_queue()
    if limit:
        queue = queue[:limit]
    report = {"queued": len(queue), "downloaded": 0, "done": 0, "failed": 0}

    for item in queue:
        key = item["appno"]
        if key in state["done"] or key in state["failed"]:
            continue
        try:
            fetcher = StealthyFetcher()
            page_html = fetcher.fetch(item["url"], timeout=60000)
            idocs = re.search(r"https?://[^'\"]*iDocsWebDPSS[^'\"]*", page_html.html_content)
            if not idocs:
                state["failed"][key] = "no iDocsWeb url"
                report["failed"] += 1
                save_state(state)
                continue
            copyright_url = idocs.group(0).replace("&amp;", "&")

            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=False)
                context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
                page = context.new_page()
                page.goto(copyright_url, timeout=90000)
                page.check("#chkAgree")
                page.wait_for_timeout(4000)
                content = page.content()
                saved = 0
                links = re.findall(r'href="([^"]+)"', content)
                for href in links:
                    label = href.rsplit("/", 1)[-1]
                    if not re.search(r"pdf|tif|jpg|ashx|download|document", href, re.IGNORECASE):
                        continue
                    if not LAYOUT_RE.search(label) and not LAYOUT_RE.search(href):
                        continue
                    absolute = href if href.startswith("http") else copyright_url.rsplit("/", 1)[0] + "/" + href
                    try:
                        response = context.request.get(absolute, timeout=120000)
                        if len(response.body()) < 5000:
                            continue
                        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", label)[:70]
                        (OUT_DIR / f"{key}_{safe}").write_bytes(response.body())
                        saved += 1
                    except Exception:
                        continue
                    time.sleep(0.4)
                browser.close()
            state["done"][key] = {"files_saved": saved}
            report["downloaded"] += saved
            report["done"] += 1
        except Exception as exc:
            state["failed"][key] = str(exc)[:200]
            report["failed"] += 1
        save_state(state)
        time.sleep(1.0)

    (settings.SILVER_DIR / "site_layouts_browser_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    run(limit=args.limit)
