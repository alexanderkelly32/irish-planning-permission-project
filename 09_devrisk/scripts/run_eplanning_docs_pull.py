"""Runner: ePlanning/iDocsWeb document puller for phase-pilot estates.

Flow per application: AppFileRefDetails page -> extract the iDocsWeb
copyright.aspx URL -> GET (session cookie) -> POST the chkAgree postback
(__VIEWSTATE/__EVENTVALIDATION) -> parse the document list -> download
site-layout/phasing-related scanned files. Resume-safe; background-friendly.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

OUT_DIR = settings.RAW_DIR / "site_layouts"
STATE_PATH = settings.SILVER_DIR / "site_layouts_pull_state.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) planning-risk-review/1.0"
LAYOUT_RE = re.compile(r"site\s*layout|layout\s*plan|phasing|master\s*plan|overall\s*site|development\s*plan\s*\(|unit\s*schedule|house\s*type", re.IGNORECASE)
HIDDEN_RE = re.compile(r'<input[^>]+type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"')


def opener() -> urllib.request.OpenerDirector:
    jar = CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def get(op, url: str, referer: str = "") -> str:
    headers = {"User-Agent": USER_AGENT}
    if referer:
        headers["Referer"] = referer
    request = urllib.request.Request(url, headers=headers)
    with op.open(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="ignore")


def post(op, url: str, payload: dict, referer: str) -> str:
    data = urllib.parse.urlencode(payload).encode()
    request = urllib.request.Request(url, data=data, headers={
        "User-Agent": USER_AGENT, "Referer": referer, "Content-Type": "application/x-www-form-urlencoded"})
    with op.open(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="ignore")


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"done": {}, "failed": {}}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state), encoding="utf-8")


def build_queue() -> pd.DataFrame:
    shortlist = pd.read_csv(settings.SILVER_DIR / "phase_pilot_shortlist.csv")
    base = pd.read_csv(settings.ROOT / "01_flood" / "current" / "ge10_with_flooding.csv",
                       usecols=["PlanningAuthority", "ApplicationNumber", "LinkAppDetails"], low_memory=False)
    rows = []
    for _, row in shortlist.iterrows():
        match = base[(base["PlanningAuthority"] == str(row["authority"])) & (base["ApplicationNumber"].astype(str) == str(row["appno"]))]
        if not len(match):
            continue
        link = str(match.iloc[0]["LinkAppDetails"])
        if "eplanning.ie" in link or "eplan." in link:
            rows.append({"appno": str(row["appno"]), "authority": str(row["authority"]),
                         "development_id": str(row["development_id"]), "url": link})
    return pd.DataFrame(rows)


def run(limit: int = 0) -> dict:
    queue = build_queue()
    state = load_state()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = {"queued": int(len(queue)), "downloaded": 0, "skipped_done": 0, "failed": 0}

    for _, row in queue.iterrows():
        key = row["appno"]
        if key in state["done"] or key in state["failed"]:
            report["skipped_done"] += 1
            continue
        try:
            op = opener()
            html = get(op, row["url"])
            idocs_match = re.search(r"(https?://[^'\"]*iDocsWebDPSS[^'\"]*)", html)
            if not idocs_match:
                state["failed"][key] = "no iDocsWeb URL on page"
                report["failed"] += 1
                save_state(state)
                continue
            copyright_url = idocs_match.group(1).replace("&amp;", "&")
            agree_page = get(op, copyright_url, referer=row["url"])
            hidden = dict(HIDDEN_RE.findall(agree_page))
            payload = {
                "__EVENTTARGET": "chkAgree",
                "__EVENTARGUMENT": "",
                "__VIEWSTATE": hidden.get("__VIEWSTATE", ""),
                "__EVENTVALIDATION": hidden.get("__EVENTVALIDATION", ""),
                "__VIEWSTATEGENERATOR": hidden.get("__VIEWSTATEGENERATOR", ""),
                "chkAgree": "on",
            }
            listing = post(op, copyright_url, payload, referer=copyright_url)
            doc_links = re.findall(r'href="([^"]+)"', listing)
            saved = 0
            for href in doc_links:
                if not re.search(r"(pdf|tif|jpg|ashx|download|document)", href, re.IGNORECASE):
                    continue
                label_match = re.search(r"[^/]+$", href)
                label = urllib.parse.unquote(label_match.group(0)) if label_match else href[-40:]
                if not LAYOUT_RE.search(label) and not LAYOUT_RE.search(listing[max(0, listing.find(href) - 200):listing.find(href)]):
                    continue
                absolute = href if href.startswith("http") else urllib.parse.urljoin(copyright_url, href)
                try:
                    request = urllib.request.Request(absolute, headers={"User-Agent": USER_AGENT,
                                                                        "Referer": listing and copyright_url or row["url"]})
                    with op.open(request, timeout=300) as response:
                        content = response.read()
                    if len(content) < 5000:
                        continue
                    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", label)[:70]
                    (OUT_DIR / f"{key}_{safe}").write_bytes(content)
                    saved += 1
                except Exception:
                    continue
                time.sleep(0.5)
            state["done"][key] = {"authority": row["authority"], "files_saved": saved}
            report["downloaded"] += saved
        except Exception as exc:
            state["failed"][key] = str(exc)[:200]
            report["failed"] += 1
        save_state(state)
        time.sleep(1.0)

    (settings.SILVER_DIR / "site_layouts_pull_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    run(limit=args.limit)
