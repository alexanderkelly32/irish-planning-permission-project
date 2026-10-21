"""Runner: eplanning.ie applicant-index scraper (background-safe).

~25 councils share the eplanning platform; each AppFileRefDetails page carries
Applicant name + address (public planning-consultation data). One parser covers
them. Resume-safe state file; writes applicant_index.csv (case_key, council,
app_file_id, applicant_name, applicant_address, status). No phone numbers are
stored.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

USER_AGENT = "Mozilla/5.0 planning-risk-review/1.0 (local personal research)"
DELAY = 0.4
STATE_PATH = settings.SILVER_DIR / "eplanning_scrape_state.json"
OUT_PATH = settings.SILVER_DIR / "applicant_index.csv"

EPLANNING_RE = re.compile(r"(?:www\.)?eplanning\.ie/([A-Za-z0-9]+)/AppFileRefDetails/(\d+)/0")


def parse_applicant(html: str) -> tuple[str, str]:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    name = address = ""
    match = re.search(r"Applicant name:\s*(.*?)\s*(?:Applicant Address:|Phone)", text, re.IGNORECASE)
    if match:
        name = match.group(1).strip().strip("|, ")[:120]
    match = re.search(r"Applicant Address:\s*(.*?)\s*(?:Phone|Fax)", text, re.IGNORECASE)
    if match:
        address = match.group(1).strip().strip("|, ")[:200]
    return name, address


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"done": {}, "failed": {}}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state), encoding="utf-8")


def fetch(url: str) -> str | None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="ignore")
    except Exception:
        return None


def build_queue() -> pd.DataFrame:
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    base = pd.read_csv(settings.ROOT / "01_flood" / "current" / "ge10_with_flooding.csv",
                       usecols=["PlanningAuthority", "ApplicationNumber", "LinkAppDetails"])
    frame = cohort[["case_key", "PlanningAuthority", "ApplicationNumber"]].merge(
        base, on=["PlanningAuthority", "ApplicationNumber"], how="left")
    frame = frame[frame["LinkAppDetails"].fillna("").astype(str).str.contains("eplanning", case=False, na=False)].copy()
    rows = []
    for _, row in frame.iterrows():
        match = EPLANNING_RE.search(str(row["LinkAppDetails"]))
        if match:
            rows.append({"case_key": str(row["case_key"]), "council": match.group(1), "file_id": match.group(2),
                         "url": f"http://www.eplanning.ie/{match.group(1)}/AppFileRefDetails/{match.group(2)}/0"})
    return pd.DataFrame(rows).drop_duplicates("case_key")


def run(limit: int = 0) -> dict:
    queue = build_queue()
    state = load_state()
    pending = [row for _, row in queue.iterrows() if str(row["case_key"]) not in state["done"]]
    if limit:
        pending = pending[:limit]
    print(f"queue {len(queue)} | pending {len(pending)}", flush=True)

    rows = []
    for row in pending:
        case_key = str(row["case_key"])
        html = fetch(row["url"])
        if html is None:
            state["failed"][case_key] = row["url"]
            rows.append({"case_key": case_key, "council": row["council"], "app_file_id": row["file_id"],
                         "applicant_name": "", "applicant_address": "", "status": "fetch_failed"})
        else:
            name, address = parse_applicant(html)
            state["done"][case_key] = {"name": name, "address": address, "at": time.time()}
            rows.append({"case_key": case_key, "council": row["council"], "app_file_id": row["file_id"],
                         "applicant_name": name, "applicant_address": address, "status": "ok" if name else "no_name"})
        if len(rows) % 50 == 0:
            save_state(state)
            pd.DataFrame(rows).to_csv(OUT_PATH, index=False)
            print(f"processed {len(rows)}", flush=True)
        time.sleep(DELAY)

    save_state(state)
    new = pd.DataFrame(rows)
    if OUT_PATH.exists():
        old = pd.read_csv(OUT_PATH)
        merged = pd.concat([old, new], ignore_index=True).drop_duplicates("case_key", keep="last")
    else:
        merged = new
    merged.to_csv(OUT_PATH, index=False)
    summary = {
        "done": int(len(state["done"])),
        "failed": int(len(state["failed"])),
        "rows_with_name": int(merged["applicant_name"].fillna("").str.strip().ne("").sum()) if not merged.empty else 0,
        "out": str(OUT_PATH),
    }
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="max rows this run (0 = all pending)")
    args = parser.parse_args()
    run(limit=args.limit)
