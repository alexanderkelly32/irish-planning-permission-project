#!/usr/bin/env python3
"""
Enrich planning rows with all online Further Information (FI) events.

What this does:
1. Waits for the input CSV if it is temporarily locked/in use.
2. Pulls FI events online for each case (supports ePlan + Agile portals).
3. Writes:
   - a long FI events table (one row per FI event)
   - a case-level FI summary
   - a merged copy of the source dataset with FI summary columns
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.exceptions import SSLError
import urllib3


DEFAULT_INPUT = Path("extraction_of_site_data/greater_than_10_units_with_refusal_reasons_master.csv")
DEFAULT_EVENTS = Path("extraction_of_site_data/fi_events_long.csv")
DEFAULT_CASE_SUMMARY = Path("extraction_of_site_data/fi_events_case_summary.csv")
DEFAULT_MERGED = Path("extraction_of_site_data/greater_than_10_units_with_refusal_reasons_plus_ge10_fi_enriched.csv")


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dataclass
class FetchResult:
    case_key: str
    planning_authority: str
    application_number: str
    source_url: str
    resolved_url: str
    portal_type: str
    status: str
    error: str
    events: List[Dict[str, str]]


def log(msg: str) -> None:
    print(f"{datetime.now().strftime('%H:%M:%S')} | {msg}", flush=True)


def wait_for_readable_file(path: Path, wait_seconds: int, poll_seconds: int = 5) -> None:
    start = time.time()
    while True:
        try:
            with path.open("rb") as f:
                f.read(1)
            return
        except PermissionError:
            pass
        except OSError as exc:
            winerr = getattr(exc, "winerror", None)
            if winerr != 32:
                raise
        if wait_seconds >= 0 and (time.time() - start) > wait_seconds:
            raise TimeoutError(f"Timed out waiting for file lock to clear: {path}")
        log(f"Input locked/in use, waiting: {path}")
        time.sleep(poll_seconds)


def clean_text(v: object) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in {"nan", "nat", "none"} else s


def to_iso_date(value: str) -> str:
    s = clean_text(value)
    if not s:
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        dt = pd.to_datetime(s, errors="coerce", dayfirst=False)
    else:
        dt = pd.to_datetime(s, errors="coerce", dayfirst=True)
    if pd.isna(dt):
        return ""
    return dt.date().isoformat()


def build_case_key(authority: str, app_num: str) -> str:
    left = re.sub(r"[^a-z0-9]+", "_", clean_text(authority).lower()).strip("_")
    right = re.sub(r"[^a-z0-9]+", "", clean_text(app_num).lower())
    return f"{left}_{right}".strip("_")


def detect_portal(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "agileapplications.ie" in host:
        return "agile"
    if (
        "eplanning.ie" in host
        or "planning.corkcity.ie" in host
        or "planning.corkcoco.ie" in host
        or "appfilerefdetails" in url.lower()
    ):
        return "eplan"
    return "unknown"


def normalize_details_url(authority: str, app_num: str, raw_url: str) -> str:
    url = clean_text(raw_url)
    if not url:
        return ""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host == "planninglive":
        qs = parse_qs(parsed.query or "")
        year_file = clean_text((qs.get("yearAndFileNo") or [""])[0])
        normalized_ref = re.sub(r"[^0-9]", "", clean_text(app_num))
        if "/" in year_file:
            year, file_no = year_file.split("/", 1)
            year_digits = re.sub(r"[^0-9]", "", year)
            file_digits = re.sub(r"[^0-9]", "", file_no)
            if year_digits and file_digits:
                normalized_ref = f"{int(year_digits):02d}{file_digits}"
        if normalized_ref:
            return f"https://planning.corkcoco.ie/ePlan/AppFileRefDetails/{normalized_ref}/0"
    if url.startswith("http://"):
        return "https://" + url[len("http://") :]
    return url


def parse_fi_table_from_eplan_html(html: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    fi_div = soup.find(id="DivFI")
    if fi_div is None:
        header = soup.find(["h2", "h3", "h4"], string=re.compile(r"Further Information Details", re.I))
        if header:
            fi_div = header.parent
    if fi_div is None:
        return []

    table = fi_div.find("table")
    if table is None:
        return []

    header_cells = [clean_text(th.get_text(" ", strip=True)).lower() for th in table.find_all("th")]
    col_map = {
        "issued date": "issued_date",
        "received date": "received_date",
        "type": "fi_type",
        "decision date": "event_decision_date",
        "managers order no.": "managers_order_no",
        "managers order no": "managers_order_no",
    }
    mapped_cols: List[str] = [col_map.get(h, h.replace(" ", "_")) for h in header_cells]

    out: List[Dict[str, str]] = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        values = [clean_text(td.get_text(" ", strip=True)) for td in tds]
        if not any(values):
            continue
        row: Dict[str, str] = {}
        for i, v in enumerate(values):
            key = mapped_cols[i] if i < len(mapped_cols) else f"col_{i}"
            row[key] = v

        event = {
            "fi_type": clean_text(row.get("fi_type")),
            "requested_date": to_iso_date(row.get("issued_date", "")),
            "received_date": to_iso_date(row.get("received_date", "")),
            "event_decision_date": to_iso_date(row.get("event_decision_date", "")),
            "managers_order_no": clean_text(row.get("managers_order_no")),
            "issued_date_raw": clean_text(row.get("issued_date")),
            "received_date_raw": clean_text(row.get("received_date")),
        }
        if any([event["fi_type"], event["requested_date"], event["received_date"], event["event_decision_date"]]):
            out.append(event)
    return out


def fetch_eplan_events(url: str, timeout: int) -> Tuple[List[Dict[str, str]], str, str]:
    headers = {"User-Agent": USER_AGENT}
    last_exc: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            try:
                r = requests.get(url, headers=headers, timeout=timeout)
            except SSLError:
                # Some council endpoints have certificate chain issues; retry without TLS verification.
                r = requests.get(url, headers=headers, timeout=timeout, verify=False)
            if r.status_code >= 500 and attempt < 3:
                time.sleep(0.8 * attempt)
                continue
            break
        except Exception as exc:
            last_exc = exc
            if attempt < 3:
                time.sleep(0.8 * attempt)
                continue
            raise
    if last_exc is not None and "r" not in locals():
        raise last_exc
    if r.status_code >= 400:
        return [], f"http_{r.status_code}", r.url
    events = parse_fi_table_from_eplan_html(r.text)
    if not events:
        return [], "no_fi_section_or_events", r.url
    return events, "ok", r.url


def get_agile_client_code(slug: str, timeout: int, cache: Dict[str, Optional[str]]) -> Optional[str]:
    key = slug.lower().strip()
    if key in cache:
        return cache[key]
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*"}
    url = f"https://identity.agileapplications.ie/api/client/get?url={key}"
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code >= 400:
            cache[key] = None
            return None
        data = r.json()
        code = clean_text(data.get("code")) if isinstance(data, dict) else ""
        cache[key] = code or None
        return cache[key]
    except Exception:
        cache[key] = None
        return None


def parse_agile_url(url: str) -> Tuple[str, str]:
    m = re.search(r"agileapplications\.ie/([^/]+)/application-details/(\d+)", url, flags=re.I)
    if m:
        return m.group(1), m.group(2)
    m_slug = re.search(r"agileapplications\.ie/([^/]+)/", url, flags=re.I)
    if m_slug:
        return m_slug.group(1), ""
    return "", ""


def resolve_agile_app_id_from_reference(
    slug: str,
    app_ref: str,
    timeout: int,
    client_cache: Dict[str, Optional[str]],
) -> str:
    client_code = get_agile_client_code(slug, timeout=timeout, cache=client_cache)
    if not client_code:
        return ""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://planning.agileapplications.ie/",
        "x-client": client_code,
        "x-service": "PA",
        "x-product": "CITIZENPORTAL",
    }
    query = clean_text(app_ref)
    if not query:
        return ""
    endpoint = "https://planningapi.agileapplications.ie/api/application/search"
    try:
        r = requests.get(endpoint, headers=headers, params={"query": query, "page": 1}, timeout=timeout)
        if r.status_code >= 400:
            return ""
        data = r.json()
        if not isinstance(data, dict):
            return ""
        results = data.get("results")
        if not isinstance(results, list) or not results:
            return ""
        exact = None
        for item in results:
            if not isinstance(item, dict):
                continue
            ref = clean_text(item.get("reference")).upper()
            if ref == query.upper():
                exact = item
                break
        chosen = exact if exact is not None else results[0]
        app_id = str(chosen.get("id") or "").strip()
        return app_id if app_id.isdigit() else ""
    except Exception:
        return ""


def fetch_agile_events(
    url: str,
    app_ref: str,
    timeout: int,
    client_cache: Dict[str, Optional[str]],
) -> Tuple[List[Dict[str, str]], str, str]:
    slug, app_id = parse_agile_url(url)
    if slug and not app_id:
        app_id = resolve_agile_app_id_from_reference(slug, app_ref=app_ref, timeout=timeout, client_cache=client_cache)
    if not slug or not app_id:
        return [], "bad_agile_url", url

    client_code = get_agile_client_code(slug, timeout=timeout, cache=client_cache)
    if not client_code:
        return [], "agile_client_not_found", url

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://planning.agileapplications.ie/",
        "x-client": client_code,
        "x-service": "PA",
        "x-product": "CITIZENPORTAL",
    }
    endpoint = f"https://planningapi.agileapplications.ie/api/application/{app_id}/further-info"
    r = requests.get(endpoint, headers=headers, timeout=timeout)
    if r.status_code >= 400:
        return [], f"http_{r.status_code}", endpoint
    data = r.json()
    if not isinstance(data, list):
        return [], "unexpected_payload", endpoint

    events: List[Dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        event = {
            "fi_type": clean_text(item.get("furtherInformationType")),
            "requested_date": to_iso_date(clean_text(item.get("requestedDate"))),
            "received_date": to_iso_date(clean_text(item.get("receivedDate"))),
            "event_decision_date": "",
            "managers_order_no": "",
            "issued_date_raw": clean_text(item.get("requestedDate")),
            "received_date_raw": clean_text(item.get("receivedDate")),
        }
        if any([event["fi_type"], event["requested_date"], event["received_date"]]):
            events.append(event)

    if not events:
        return [], "no_fi_events", endpoint
    return events, "ok", endpoint


def summarize_events(events: List[Dict[str, str]]) -> Dict[str, str | int]:
    req_dates = sorted({e["requested_date"] for e in events if clean_text(e.get("requested_date"))})
    rec_dates = sorted({e["received_date"] for e in events if clean_text(e.get("received_date"))})
    dec_dates = sorted({e["event_decision_date"] for e in events if clean_text(e.get("event_decision_date"))})
    fi_types = sorted({clean_text(e.get("fi_type")) for e in events if clean_text(e.get("fi_type"))})

    request_events = 0
    received_events = 0
    for e in events:
        fi_type = clean_text(e.get("fi_type")).lower()
        if "request" in fi_type or clean_text(e.get("requested_date")):
            request_events += 1
        if "receiv" in fi_type or clean_text(e.get("received_date")):
            received_events += 1

    return {
        "fi_events_count": len(events),
        "fi_request_events_count": request_events,
        "fi_received_events_count": received_events,
        "fi_first_requested_date": req_dates[0] if req_dates else "",
        "fi_last_requested_date": req_dates[-1] if req_dates else "",
        "fi_first_received_date": rec_dates[0] if rec_dates else "",
        "fi_last_received_date": rec_dates[-1] if rec_dates else "",
        "fi_last_event_decision_date": dec_dates[-1] if dec_dates else "",
        "fi_all_requested_dates": "|".join(req_dates),
        "fi_all_received_dates": "|".join(rec_dates),
        "fi_types_seen": "|".join(fi_types),
    }


def fetch_case(
    row: Dict[str, object],
    timeout: int,
    client_cache: Dict[str, Optional[str]],
) -> FetchResult:
    authority = clean_text(row.get("PlanningAuthority"))
    app_num = clean_text(row.get("ApplicationNumber"))
    case_key = clean_text(row.get("case_key")) or build_case_key(authority, app_num)
    source_url = clean_text(row.get("LinkAppDetails"))
    normalized_url = normalize_details_url(authority, app_num, source_url)

    if not normalized_url:
        return FetchResult(case_key, authority, app_num, source_url, "", "none", "no_url", "", [])

    portal = detect_portal(normalized_url)
    try:
        if portal == "eplan":
            events, status, resolved_url = fetch_eplan_events(normalized_url, timeout=timeout)
        elif portal == "agile":
            events, status, resolved_url = fetch_agile_events(
                normalized_url,
                app_ref=app_num,
                timeout=timeout,
                client_cache=client_cache,
            )
        else:
            return FetchResult(case_key, authority, app_num, source_url, normalized_url, portal, "unsupported_portal", "", [])
        return FetchResult(case_key, authority, app_num, source_url, resolved_url, portal, status, "", events)
    except Exception as exc:
        return FetchResult(case_key, authority, app_num, source_url, normalized_url, portal, "error", str(exc), [])


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich planning dataset with multi-event FI data from online sources.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--events-output", default=str(DEFAULT_EVENTS))
    parser.add_argument("--case-summary-output", default=str(DEFAULT_CASE_SUMMARY))
    parser.add_argument("--merged-output", default=str(DEFAULT_MERGED))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--max-cases", type=int, default=0, help="0 means all rows.")
    parser.add_argument("--wait-seconds", type=int, default=1800, help="How long to wait if the input file is locked. -1 waits forever.")
    args = parser.parse_args()

    input_path = Path(args.input)
    events_path = Path(args.events_output)
    case_summary_path = Path(args.case_summary_output)
    merged_path = Path(args.merged_output)

    wait_for_readable_file(input_path, wait_seconds=args.wait_seconds)
    log(f"Reading input: {input_path}")
    df = pd.read_csv(input_path, low_memory=False, dtype={"ApplicationNumber": str})

    needed = ["PlanningAuthority", "ApplicationNumber", "LinkAppDetails"]
    for col in needed:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")
    if "case_key" not in df.columns:
        df["case_key"] = ""

    if args.max_cases and args.max_cases > 0:
        df = df.head(args.max_cases).copy()
        log(f"Limiting to first {len(df)} rows due to --max-cases")

    records = df[["case_key", "PlanningAuthority", "ApplicationNumber", "LinkAppDetails"]].to_dict("records")
    log(f"Processing rows: {len(records)}")

    client_cache: Dict[str, Optional[str]] = {}
    all_events: List[Dict[str, str]] = []
    case_rows: List[Dict[str, object]] = []

    with futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        pending = [ex.submit(fetch_case, rec, args.timeout, client_cache) for rec in records]
        done = 0
        for fut in futures.as_completed(pending):
            res = fut.result()
            done += 1
            if done % 200 == 0 or done == len(pending):
                log(f"Completed {done}/{len(pending)}")

            summary = summarize_events(res.events) if res.events else {
                "fi_events_count": 0,
                "fi_request_events_count": 0,
                "fi_received_events_count": 0,
                "fi_first_requested_date": "",
                "fi_last_requested_date": "",
                "fi_first_received_date": "",
                "fi_last_received_date": "",
                "fi_last_event_decision_date": "",
                "fi_all_requested_dates": "",
                "fi_all_received_dates": "",
                "fi_types_seen": "",
            }
            case_row = {
                "case_key": res.case_key,
                "PlanningAuthority": res.planning_authority,
                "ApplicationNumber": res.application_number,
                "fi_source_url": res.source_url,
                "fi_resolved_url": res.resolved_url,
                "fi_portal_type": res.portal_type,
                "fi_fetch_status": res.status,
                "fi_fetch_error": res.error,
            }
            case_row.update(summary)
            case_rows.append(case_row)

            for i, event in enumerate(res.events, start=1):
                all_events.append(
                    {
                        "case_key": res.case_key,
                        "PlanningAuthority": res.planning_authority,
                        "ApplicationNumber": res.application_number,
                        "event_index": i,
                        "fi_portal_type": res.portal_type,
                        "fi_source_url": res.source_url,
                        "fi_resolved_url": res.resolved_url,
                        "fi_fetch_status": res.status,
                        **event,
                    }
                )

    events_df = pd.DataFrame(all_events)
    case_df = pd.DataFrame(case_rows)
    merged = df.merge(case_df.drop(columns=["PlanningAuthority", "ApplicationNumber"]), on="case_key", how="left")

    events_path.parent.mkdir(parents=True, exist_ok=True)
    case_summary_path.parent.mkdir(parents=True, exist_ok=True)
    merged_path.parent.mkdir(parents=True, exist_ok=True)

    events_df.to_csv(events_path, index=False)
    case_df.to_csv(case_summary_path, index=False)
    merged.to_csv(merged_path, index=False)

    log(f"Wrote events: {events_path} ({len(events_df)} rows)")
    log(f"Wrote case summary: {case_summary_path} ({len(case_df)} rows)")
    log(f"Wrote merged dataset: {merged_path} ({len(merged)} rows)")

    status_counts = case_df["fi_fetch_status"].value_counts(dropna=False).to_dict() if not case_df.empty else {}
    log(f"Status counts: {status_counts}")


if __name__ == "__main__":
    main()
