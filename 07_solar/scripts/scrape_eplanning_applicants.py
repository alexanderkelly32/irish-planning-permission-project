#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MASTER = ROOT / "02_development" / "source_data" / "ground_source_extracted_final_wide_comprehensive_master.csv"
DEFAULT_SOLAR = ROOT / "07_solar" / "source_data" / "solar_farms_map_ready.csv"
DEFAULT_OUT = ROOT / "07_solar" / "source_data" / "solar_farm_applicants_from_eplanning.csv"


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"


@dataclass(frozen=True)
class ScrapeResult:
    case_key: str
    link: str
    applicant_name: str
    applicant_address: str
    ok: bool
    error: str
    scraped_at_utc: str


def load_solar_case_keys(solar_csv: Path) -> List[str]:
    df = pd.read_csv(solar_csv, usecols=["case_key"])
    return df["case_key"].dropna().astype(str).tolist()


def load_links_for_case_keys(master_csv: Path, case_keys: Iterable[str]) -> Dict[str, str]:
    wanted = set(case_keys)
    found: Dict[str, str] = {}
    usecols = ["case_key", "LinkAppDetails"]
    for chunk in pd.read_csv(master_csv, usecols=usecols, chunksize=200_000):
        chunk = chunk.dropna(subset=["case_key"])
        hit = chunk[chunk["case_key"].isin(wanted)]
        if hit.empty:
            continue
        for ck, link in zip(hit["case_key"].astype(str), hit["LinkAppDetails"].astype(str), strict=False):
            if ck not in found and link and link.lower().startswith("http"):
                found[ck] = link
        if len(found) >= len(wanted):
            break
    return found


def parse_applicant_tab(html: str) -> Dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    tab = soup.find(id="Applicant")
    if not tab:
        return {}
    table = tab.find("table")
    if not table:
        return {}

    fields: Dict[str, str] = {}
    for tr in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        if not cells:
            continue
        # Common formats:
        # ["Applicant name:", "Elgin Energy Services Ltd."]
        # ["Phone Number:", "", "Fax Number:", ""]
        if len(cells) == 2:
            k, v = cells
            if k.endswith(":"):
                fields[k] = v
        elif len(cells) == 4:
            k1, v1, k2, v2 = cells
            if k1.endswith(":"):
                fields[k1] = v1
            if k2.endswith(":"):
                fields[k2] = v2
    return fields


def fetch(session: requests.Session, url: str, timeout_s: float) -> str:
    resp = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout_s)
    resp.raise_for_status()
    return resp.text


def scrape_one(session: requests.Session, case_key: str, link: str, timeout_s: float) -> ScrapeResult:
    scraped_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    try:
        html = fetch(session, link, timeout_s=timeout_s)
        fields = parse_applicant_tab(html)
        name = fields.get("Applicant name:", "") or fields.get("Applicant Name:", "")
        addr = fields.get("Applicant Address:", "") or fields.get("Applicant address:", "")
        ok = bool(name)
        return ScrapeResult(
            case_key=case_key,
            link=link,
            applicant_name=name.strip(),
            applicant_address=addr.strip(),
            ok=ok,
            error="" if ok else "no_applicant_name_found",
            scraped_at_utc=scraped_at,
        )
    except Exception as e:  # noqa: BLE001
        return ScrapeResult(
            case_key=case_key,
            link=link,
            applicant_name="",
            applicant_address="",
            ok=False,
            error=f"{type(e).__name__}: {e}",
            scraped_at_utc=scraped_at,
        )


def read_existing(out_csv: Path) -> Dict[str, ScrapeResult]:
    if not out_csv.exists():
        return {}
    existing: Dict[str, ScrapeResult] = {}
    with out_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ck = (row.get("case_key") or "").strip()
            if not ck:
                continue
            existing[ck] = ScrapeResult(
                case_key=ck,
                link=row.get("link", ""),
                applicant_name=row.get("applicant_name", ""),
                applicant_address=row.get("applicant_address", ""),
                ok=(row.get("ok", "").strip().lower() == "true"),
                error=row.get("error", ""),
                scraped_at_utc=row.get("scraped_at_utc", ""),
            )
    return existing


def write_all(out_csv: Path, rows: Iterable[ScrapeResult]) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "case_key",
                "link",
                "applicant_name",
                "applicant_address",
                "ok",
                "error",
                "scraped_at_utc",
            ],
        )
        writer.writeheader()
        for r in rows:
            writer.writerow(
                {
                    "case_key": r.case_key,
                    "link": r.link,
                    "applicant_name": r.applicant_name,
                    "applicant_address": r.applicant_address,
                    "ok": str(bool(r.ok)),
                    "error": r.error,
                    "scraped_at_utc": r.scraped_at_utc,
                }
            )


def main() -> int:
    ap = argparse.ArgumentParser(description="Scrape applicant names from eplanning.ie LinkAppDetails pages")
    ap.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    ap.add_argument("--solar", type=Path, default=DEFAULT_SOLAR)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--max", type=int, default=0, help="limit number of rows to scrape (0 = all)")
    ap.add_argument("--refresh", action="store_true", help="re-scrape even if out CSV already has a row")
    ap.add_argument("--delay-s", type=float, default=0.35, help="base delay between requests (jitter is added)")
    ap.add_argument("--timeout-s", type=float, default=30.0)
    args = ap.parse_args()

    case_keys = load_solar_case_keys(args.solar)
    if args.max and args.max > 0:
        case_keys = case_keys[: args.max]

    existing = {} if args.refresh else read_existing(args.out)
    links = load_links_for_case_keys(args.master, case_keys)

    session = requests.Session()
    results: List[ScrapeResult] = []
    done = 0

    for ck in case_keys:
        if ck in existing:
            results.append(existing[ck])
            done += 1
            continue

        link = links.get(ck, "")
        if not link:
            results.append(
                ScrapeResult(
                    case_key=ck,
                    link="",
                    applicant_name="",
                    applicant_address="",
                    ok=False,
                    error="missing_link",
                    scraped_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                )
            )
            done += 1
            continue

        r = scrape_one(session, ck, link, timeout_s=args.timeout_s)
        results.append(r)
        done += 1

        if done % 25 == 0:
            print(f"{done}/{len(case_keys)} scraped (ok={sum(1 for x in results if x.ok)})")
            write_all(args.out, results)

        # Polite delay with jitter (avoid looking like a bot; also reduces resets)
        time.sleep(max(0.0, args.delay_s + random.uniform(0.05, 0.25)))

    write_all(args.out, results)
    ok = sum(1 for r in results if r.ok)
    print(f"done: {len(results)} rows (ok={ok}, failed={len(results)-ok}) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

