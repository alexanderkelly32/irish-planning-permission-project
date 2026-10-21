#!/usr/bin/env python3
"""
Pull Further Information (FI) document metadata (and optional files) from planning portals.

This script targets cases with FI events already identified (`fi_events_count > 0`) and uses:
- Agile API document endpoints
- ePlan/iDocs scanned files pages via Playwright
"""
from __future__ import annotations

import argparse
import re
import time
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PWTimeoutError
from playwright.sync_api import sync_playwright


DEFAULT_INPUT = Path("extraction_of_site_data/greater_than_10_units_with_refusal_reasons_plus_ge10_fi_enriched.csv")
DEFAULT_LONG_OUT = Path("extraction_of_site_data/fi_documents_long.csv")
DEFAULT_CASE_OUT = Path("extraction_of_site_data/fi_documents_case_summary.csv")
DEFAULT_DOWNLOAD_ROOT = Path("extraction_of_site_data/fi_documents")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

FI_PATTERNS = [
    r"\bfurther information\b",
    r"\brequest for further information\b",
    r"\bresponse to fi\b",
    r"\bfi response\b",
    r"\badditional information\b",
    r"\bclarification\b",
    r"\bfi\b",
]


@dataclass
class CaseResult:
    case_key: str
    planning_authority: str
    application_number: str
    portal_type: str
    source_url: str
    status: str
    error: str
    all_docs_count: int
    fi_docs_count: int
    rows: List[Dict[str, object]]


def log(msg: str) -> None:
    print(f"{datetime.now().strftime('%H:%M:%S')} | {msg}", flush=True)


def clean_text(v: object) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in {"nan", "nat", "none"} else s


def safe_filename(s: str) -> str:
    s = clean_text(s).replace(" ", "_").replace("/", "_").replace("\\", "_")
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s)
    return s[:180]


def extension_from_content_type(content_type: str) -> str:
    ct = clean_text(content_type).lower()
    if "pdf" in ct:
        return ".pdf"
    if "djvu" in ct:
        return ".djvu"
    if "msword" in ct:
        return ".doc"
    if "officedocument.wordprocessingml.document" in ct:
        return ".docx"
    if "zip" in ct:
        return ".zip"
    if "jpeg" in ct:
        return ".jpg"
    if "png" in ct:
        return ".png"
    return ".bin"


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
            if getattr(exc, "winerror", None) != 32:
                raise
        if wait_seconds >= 0 and (time.time() - start) > wait_seconds:
            raise TimeoutError(f"Timed out waiting for file lock to clear: {path}")
        log(f"Input locked/in use, waiting: {path}")
        time.sleep(poll_seconds)


def is_fi_doc(*values: str) -> bool:
    text = " ".join(clean_text(v).lower() for v in values if clean_text(v))
    if not text:
        return False
    for pat in FI_PATTERNS:
        if re.search(pat, text, flags=re.I):
            return True
    return False


def detect_portal(url: str) -> str:
    u = clean_text(url).lower()
    if "agileapplications.ie" in u:
        return "agile"
    if (
        "appfilerefdetails" in u
        or "eplanning.ie" in u
        or "planning.corkcity.ie" in u
        or "planning.corkcoco.ie" in u
        or "planninglive" in u
    ):
        return "eplan"
    return "unknown"


def normalize_details_url(authority: str, app_num: str, app_url: str) -> str:
    url = clean_text(app_url)
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
                # Cork planninglive refs are concatenated without forced year zero-padding.
                # Example: 8/7493 -> 87493 (not 087493).
                normalized_ref = f"{int(year_digits)}{file_digits}"
        if normalized_ref:
            return f"https://planning.corkcoco.ie/ePlan/AppFileRefDetails/{normalized_ref}/0"
    if url.startswith("http://"):
        return "https://" + url[len("http://") :]
    return url


def parse_agile_url(url: str) -> Tuple[str, str]:
    m = re.search(r"agileapplications\.ie/([^/]+)/application-details/(\d+)", url, flags=re.I)
    if m:
        return m.group(1), m.group(2)
    m_slug = re.search(r"agileapplications\.ie/([^/]+)/", url, flags=re.I)
    if m_slug:
        return m_slug.group(1), ""
    return "", ""


def get_agile_client_code(slug: str, timeout: int, cache: Dict[str, Optional[str]]) -> Optional[str]:
    key = slug.lower().strip()
    if key in cache:
        return cache[key]
    try:
        r = requests.get(
            f"https://identity.agileapplications.ie/api/client/get?url={key}",
            headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*"},
            timeout=timeout,
        )
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


def resolve_agile_app_id(slug: str, app_ref: str, timeout: int, cache: Dict[str, Optional[str]]) -> str:
    client = get_agile_client_code(slug, timeout=timeout, cache=cache)
    if not client:
        return ""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://planning.agileapplications.ie/",
        "x-client": client,
        "x-service": "PA",
        "x-product": "CITIZENPORTAL",
    }
    q = clean_text(app_ref)
    if not q:
        return ""
    try:
        r = requests.get(
            "https://planningapi.agileapplications.ie/api/application/search",
            headers=headers,
            params={"query": q, "page": 1},
            timeout=timeout,
        )
        if r.status_code >= 400:
            return ""
        data = r.json()
        if not isinstance(data, dict):
            return ""
        results = data.get("results")
        if not isinstance(results, list) or not results:
            return ""
        q_up = q.upper()
        for item in results:
            if isinstance(item, dict) and clean_text(item.get("reference")).upper() == q_up:
                app_id = clean_text(item.get("id"))
                if app_id.isdigit():
                    return app_id
        first = results[0] if isinstance(results[0], dict) else {}
        app_id = clean_text(first.get("id"))
        return app_id if app_id.isdigit() else ""
    except Exception:
        return ""


def normalize_document_href(href: str, base_url: str) -> str:
    href = clean_text(href)
    if not href:
        return ""
    if href.lower().startswith("javascript:"):
        matches = re.findall(r"""['"]([^'"]+)['"]""", href)
        href = matches[0].strip() if matches else ""
    if not href:
        return ""
    if href.startswith(("http://", "https://")):
        return href
    if href.startswith("//"):
        return f"https:{href}"
    return urljoin(base_url, href)


def parse_idocs_documents(html_text: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html_text, "html.parser")
    rows = soup.find_all("tr")
    documents: List[Dict[str, str]] = []
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        doc_type = cells[0].get_text(strip=True)
        comment = cells[1].get_text(strip=True) if len(cells) > 1 else ""
        num_files = cells[2].get_text(strip=True) if len(cells) > 2 else ""
        size = cells[3].get_text(strip=True) if len(cells) > 3 else ""
        low_doc_type = doc_type.lower()
        if (
            not doc_type
            or doc_type in {"Type", ""}
            or doc_type.startswith("Note:")
            or "planning application" in low_doc_type
            or "order by" in low_doc_type
        ):
            continue
        links = row.find_all("a")
        if not links:
            continue
        href = ""
        for link in links:
            candidate = clean_text(link.get("href"))
            if not candidate:
                continue
            if "format=jpeg" in candidate.lower():
                continue
            href = candidate
            break
        if not href:
            href = clean_text(links[0].get("href"))
        if not href:
            continue
        documents.append(
            {
                "type": doc_type,
                "comment": comment,
                "files": num_files,
                "size": size,
                "href": href,
            }
        )
    return documents


def parse_donegal_documents(html_text: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html_text, "html.parser")
    table = soup.find("table")
    if not table:
        return []
    rows = table.find_all("tr")
    documents: List[Dict[str, str]] = []
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        doc_type = cells[1].get_text(strip=True) if len(cells) > 1 else cells[0].get_text(strip=True)
        comment = cells[3].get_text(strip=True) if len(cells) > 3 else ""
        href = ""
        link = cells[-1].find("a")
        if link:
            href = clean_text(link.get("href"))
        if doc_type and href:
            documents.append(
                {
                    "type": doc_type,
                    "comment": comment,
                    "files": "",
                    "size": "",
                    "href": href,
                }
            )
    return documents


def extract_planningdocs_url(text: str) -> str:
    m = re.search(
        r"(https?://planningdocs\.corkcoco\.ie/PlanningDocumentDisplay/Documents/[^\"'\s<>)]+)",
        clean_text(text),
        flags=re.I,
    )
    return clean_text(m.group(1)) if m else ""


def parse_cork_planningdocs_tree(tree: object) -> List[Dict[str, str]]:
    if not isinstance(tree, list):
        return []
    base = "https://planningdocs.corkcoco.ie/PlanningDocumentDisplay"
    docs: List[Dict[str, str]] = []

    def walk(node: object, trail: List[str]) -> None:
        if not isinstance(node, dict):
            return
        title = clean_text(node.get("Title"))
        node_id = clean_text(node.get("Id"))
        children = node.get("Documents") if isinstance(node.get("Documents"), list) else []
        current = trail + ([title] if title else [])
        if "|" in node_id and not children:
            parts = node_id.split("|", 2)
            if len(parts) == 3:
                _doc_num, guid, file_name = parts
                docs.append(
                    {
                        "type": title,
                        "comment": " > ".join(current[:-1]),
                        "files": "",
                        "size": "",
                        "href": f"{base}/Documents/Display/{file_name}/{guid}",
                    }
                )
        for child in children:
            walk(child, current)

    for root in tree:
        walk(root, [])
    return docs


def fetch_cork_planningdocs(page, planningdocs_url: str, timeout_ms: int) -> List[Dict[str, str]]:
    m = re.search(r"/documents/([^/?#]+)", clean_text(planningdocs_url), flags=re.I)
    if not m:
        return []
    app_ref = clean_text(m.group(1))
    api_url = f"https://planningdocs.corkcoco.ie/PlanningDocumentDisplay/api/Documents/{app_ref}"
    try:
        r = page.context.request.get(api_url, timeout=timeout_ms)
        if getattr(r, "status", 500) >= 400:
            return []
        tree = r.json()
        return parse_cork_planningdocs_tree(tree)
    except Exception:
        return []


def filter_out_non_document_rows(docs: List[Dict[str, str]], details_url: str) -> List[Dict[str, str]]:
    filtered: List[Dict[str, str]] = []
    for d in docs:
        href = clean_text(d.get("href"))
        href_l = href.lower()
        # Some pages contain application navigation rows that point back to AppFileRefDetails;
        # these are not actual scanned/document files.
        if "appfilerefdetails" in href_l:
            continue
        filtered.append(d)
    return filtered


def get_page_content_with_retries(page, timeout_ms: int, retries: int = 6) -> str:
    last_error = ""
    for attempt in range(1, retries + 1):
        try:
            page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        except Exception:
            pass
        try:
            page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 5000))
        except Exception:
            pass
        try:
            return page.content()
        except Exception as exc:
            last_error = str(exc)
            if "navigating and changing the content" not in last_error.lower():
                raise
            # Backoff for in-flight page transitions before trying again.
            page.wait_for_timeout(min(400 * attempt, 2000))
    raise RuntimeError(last_error or "Unable to retrieve page content after retries")


def fetch_eplan_docs(page, details_url: str, timeout_ms: int) -> Tuple[List[Dict[str, str]], str, str]:
    page.goto(details_url, wait_until="domcontentloaded", timeout=timeout_ms)
    trigger = page.locator('input[value="View Scanned Files"]')
    page_html = ""
    try:
        page_html = get_page_content_with_retries(page, timeout_ms=timeout_ms, retries=3)
    except Exception:
        page_html = ""
    direct_planningdocs = extract_planningdocs_url(page_html)
    if direct_planningdocs:
        docs = fetch_cork_planningdocs(page, direct_planningdocs, timeout_ms=timeout_ms)
        docs = filter_out_non_document_rows(docs, details_url=details_url)
        if docs:
            return docs, "ok", direct_planningdocs

    if trigger.count() == 0:
        txt = page.inner_text("body")
        if "view scanned files" not in txt.lower():
            return [], "no_scanned_files_button", page.url
    popup = None
    popup_url = ""
    if trigger.count() > 0:
        try:
            onclick_attr = clean_text(trigger.first.get_attribute("onclick"))
            for pat in [
                r"(https?://[^\"']*(?:ViewExternalDocuments|listFiles\.aspx|copyright\.aspx)[^\"']*)",
                r"'(https?://[^']+)'",
                r'"(https?://[^"]+)"',
            ]:
                m = re.search(pat, onclick_attr, flags=re.I)
                if m:
                    popup_url = unescape(m.group(1))
                    break
        except Exception:
            popup_url = ""

    if popup_url:
        if "planningdocs.corkcoco.ie/planningdocumentdisplay/documents/" in popup_url.lower():
            docs = fetch_cork_planningdocs(page, popup_url, timeout_ms=timeout_ms)
            docs = filter_out_non_document_rows(docs, details_url=details_url)
            if docs:
                return docs, "ok", popup_url
        popup = page
        popup.goto(popup_url, wait_until="domcontentloaded", timeout=timeout_ms)
    else:
        try:
            with page.expect_popup(timeout=timeout_ms) as pop:
                if trigger.count() > 0:
                    trigger.first.click(timeout=timeout_ms)
                else:
                    page.get_by_text(re.compile(r"view scanned files", re.I)).first.click(timeout=timeout_ms)
            popup = pop.value
        except PWTimeoutError:
            # same-tab fallback
            if trigger.count() > 0:
                trigger.first.click(timeout=timeout_ms)
            else:
                page.get_by_text(re.compile(r"view scanned files", re.I)).first.click(timeout=timeout_ms)
            popup = page

    popup.wait_for_load_state("domcontentloaded", timeout=timeout_ms)

    if "copyright" in popup.url.lower():
        try:
            chk = popup.locator("input#chkAgree")
            if chk.count() > 0:
                chk.check(timeout=timeout_ms)
            btn = popup.locator("input#btnViewFiles")
            if btn.count() > 0:
                btn.click(timeout=timeout_ms)
            popup.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        except Exception:
            pass

    list_url = (popup.url or details_url).replace("copyright.aspx", "listFiles.aspx").replace("Copyright.aspx", "listFiles.aspx")
    if "listfiles.aspx" not in list_url.lower():
        # if already on list page this is harmless; otherwise best guess
        list_url = details_url
    if "orderBy=type" not in list_url:
        list_url += ("&" if "?" in list_url else "?") + "orderBy=type"
    try:
        popup.goto(list_url, wait_until="domcontentloaded", timeout=timeout_ms)
    except Exception:
        pass
    html_text = get_page_content_with_retries(popup, timeout_ms=timeout_ms, retries=6)
    docs = parse_idocs_documents(html_text)
    if not docs:
        docs = parse_donegal_documents(html_text)
    docs = filter_out_non_document_rows(docs, details_url=details_url)
    if not docs:
        return [], "no_documents", popup.url
    return docs, "ok", popup.url


def suggest_name_from_url(url: str, fallback: str) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query or "")
    tail = Path(parsed.path).name
    if tail and "." in tail and not tail.lower().endswith(".aspx"):
        return safe_filename(tail)
    docid = clean_text((qs.get("docid") or [""])[0])
    fmt = clean_text((qs.get("format") or [""])[0]).lower()
    if docid:
        if fmt in {"pdf", "djvu", "doc", "docx", "jpg", "jpeg", "png"}:
            ext = ".jpg" if fmt == "jpeg" else f".{fmt}"
        else:
            ext = ".bin"
        return safe_filename(f"docid_{docid}{ext}")
    return safe_filename(fallback)


def download_file_requests(
    url: str,
    out_dir: Path,
    timeout: int,
    headers: Optional[Dict[str, str]] = None,
    suggested_name: str = "file.bin",
) -> Tuple[bool, str]:
    try:
        r = requests.get(url, timeout=timeout, headers=headers)
        if r.status_code >= 400 or not r.content:
            return False, ""
        cd = clean_text(r.headers.get("Content-Disposition"))
        filename = ""
        if cd:
            m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd, flags=re.I)
            if m:
                filename = safe_filename(unescape(m.group(1)))
        if not filename:
            filename = suggest_name_from_url(url, suggested_name)
        if "." not in Path(filename).name:
            filename += extension_from_content_type(r.headers.get("Content-Type", ""))
        out = out_dir / filename
        if out.exists():
            stem = out.stem
            suf = out.suffix
            idx = 2
            while (out_dir / f"{stem}({idx}){suf}").exists():
                idx += 1
            out = out_dir / f"{stem}({idx}){suf}"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(r.content)
        return True, str(out)
    except Exception:
        return False, ""


def fetch_agile_case(
    row: pd.Series,
    timeout: int,
    download: bool,
    download_root: Path,
    client_cache: Dict[str, Optional[str]],
) -> CaseResult:
    authority = clean_text(row.get("PlanningAuthority"))
    app_num = clean_text(row.get("ApplicationNumber"))
    case_key = clean_text(row.get("case_key"))
    source_url = normalize_details_url(authority, app_num, clean_text(row.get("LinkAppDetails")))
    slug, app_id = parse_agile_url(source_url)
    if slug and not app_id:
        app_id = resolve_agile_app_id(slug=slug, app_ref=app_num, timeout=timeout, cache=client_cache)
    if not slug or not app_id:
        return CaseResult(case_key, authority, app_num, "agile", source_url, "bad_agile_url", "", 0, 0, [])

    client_code = get_agile_client_code(slug, timeout=timeout, cache=client_cache)
    if not client_code:
        return CaseResult(case_key, authority, app_num, "agile", source_url, "no_agile_client", "", 0, 0, [])
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://planning.agileapplications.ie/",
        "x-client": client_code,
        "x-service": "PA",
        "x-product": "CITIZENPORTAL",
    }
    docs_url = f"https://planningapi.agileapplications.ie/api/application/{app_id}/document"
    try:
        r = requests.get(docs_url, headers=headers, timeout=timeout)
        if r.status_code >= 400:
            return CaseResult(case_key, authority, app_num, "agile", source_url, f"http_{r.status_code}", "", 0, 0, [])
        docs = r.json()
        if not isinstance(docs, list):
            return CaseResult(case_key, authority, app_num, "agile", source_url, "bad_payload", "", 0, 0, [])
    except Exception as exc:
        return CaseResult(case_key, authority, app_num, "agile", source_url, "error", str(exc), 0, 0, [])

    rows: List[Dict[str, object]] = []
    fi_count = 0
    for i, d in enumerate(docs, start=1):
        name = clean_text(d.get("name"))
        descr = clean_text(d.get("description"))
        media = clean_text(d.get("mediaDescription"))
        received = clean_text(d.get("receivedDate"))
        doc_hash = clean_text(d.get("documentHash"))
        doc_id = clean_text(d.get("documentId"))
        file_url = f"https://planningapi.agileapplications.ie/api/application/document/{doc_hash}" if doc_hash else ""
        fi = is_fi_doc(name, descr, media)
        if fi:
            fi_count += 1
        dl_path = ""
        dl_status = ""
        if download and fi and file_url:
            out_dir = download_root / safe_filename(authority) / safe_filename(app_num)
            ok, saved_path = download_file_requests(
                file_url,
                out_dir=out_dir,
                timeout=90,
                headers=headers,
                suggested_name=name or f"fi_{i}.bin",
            )
            dl_path = saved_path
            dl_status = "saved" if ok else "download_failed"
        rows.append(
            {
                "case_key": case_key,
                "PlanningAuthority": authority,
                "ApplicationNumber": app_num,
                "portal_type": "agile",
                "source_url": source_url,
                "resolved_url": docs_url,
                "doc_index": i,
                "doc_name": name,
                "doc_type": media,
                "doc_comment": descr,
                "doc_received_date": received,
                "doc_href": file_url,
                "doc_id": doc_id,
                "is_fi_doc": fi,
                "download_status": dl_status,
                "download_path": dl_path,
            }
        )
    return CaseResult(case_key, authority, app_num, "agile", source_url, "ok", "", len(docs), fi_count, rows)


def fetch_eplan_case(row: pd.Series, timeout_ms: int, page, download: bool, download_root: Path) -> CaseResult:
    authority = clean_text(row.get("PlanningAuthority"))
    app_num = clean_text(row.get("ApplicationNumber"))
    case_key = clean_text(row.get("case_key"))
    source_url = normalize_details_url(authority, app_num, clean_text(row.get("LinkAppDetails")))
    try:
        docs, status, resolved = fetch_eplan_docs(page=page, details_url=source_url, timeout_ms=timeout_ms)
        if status != "ok":
            return CaseResult(case_key, authority, app_num, "eplan", source_url, status, "", 0, 0, [])
    except Exception as exc:
        return CaseResult(case_key, authority, app_num, "eplan", source_url, "error", str(exc), 0, 0, [])

    rows: List[Dict[str, object]] = []
    fi_count = 0
    for i, d in enumerate(docs, start=1):
        doc_type = clean_text(d.get("type"))
        comment = clean_text(d.get("comment"))
        href = normalize_document_href(clean_text(d.get("href")), source_url)
        fi = is_fi_doc(doc_type, comment, href)
        if fi:
            fi_count += 1
        dl_path = ""
        dl_status = ""
        if download and fi and href and href.startswith("http"):
            hint = "_".join(x for x in [doc_type, comment] if clean_text(x)) or f"fi_{i}.bin"
            out_dir = download_root / safe_filename(authority) / safe_filename(app_num)
            ok, saved_path = download_file_requests(
                href,
                out_dir=out_dir,
                timeout=90,
                headers={"User-Agent": USER_AGENT},
                suggested_name=safe_filename(hint),
            )
            dl_path = saved_path
            dl_status = "saved" if ok else "download_failed"
        rows.append(
            {
                "case_key": case_key,
                "PlanningAuthority": authority,
                "ApplicationNumber": app_num,
                "portal_type": "eplan",
                "source_url": source_url,
                "resolved_url": resolved,
                "doc_index": i,
                "doc_name": "",
                "doc_type": doc_type,
                "doc_comment": comment,
                "doc_received_date": "",
                "doc_href": href,
                "doc_id": "",
                "is_fi_doc": fi,
                "download_status": dl_status,
                "download_path": dl_path,
            }
        )
    return CaseResult(case_key, authority, app_num, "eplan", source_url, "ok", "", len(docs), fi_count, rows)


def should_restart_browser_for_error(msg: str) -> bool:
    m = clean_text(msg).lower()
    return "err_network_io_suspended" in m or "target page, context or browser has been closed" in m


def main() -> None:
    parser = argparse.ArgumentParser(description="Pull FI document metadata/files from Agile and ePlan portals.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--long-output", default=str(DEFAULT_LONG_OUT))
    parser.add_argument("--case-output", default=str(DEFAULT_CASE_OUT))
    parser.add_argument("--download-root", default=str(DEFAULT_DOWNLOAD_ROOT))
    parser.add_argument("--portal", choices=["all", "agile", "eplan"], default="all")
    parser.add_argument("--download", action="store_true", help="Download matched FI files.")
    parser.add_argument("--max-cases", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=35)
    parser.add_argument("--wait-seconds", type=int, default=1800)
    parser.add_argument("--headless", action="store_true", default=True)
    args = parser.parse_args()

    input_path = Path(args.input)
    long_out = Path(args.long_output)
    case_out = Path(args.case_output)
    download_root = Path(args.download_root)

    wait_for_readable_file(input_path, wait_seconds=args.wait_seconds)
    df = pd.read_csv(input_path, low_memory=False, dtype={"ApplicationNumber": str})
    need = {"PlanningAuthority", "ApplicationNumber", "LinkAppDetails", "fi_events_count"}
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    work = df[df["fi_events_count"].fillna(0) > 0].copy()
    work["portal_type_detected"] = work["LinkAppDetails"].fillna("").astype(str).map(detect_portal)
    if args.portal != "all":
        work = work[work["portal_type_detected"] == args.portal]
    work = work[work["LinkAppDetails"].fillna("").astype(str).str.strip().ne("")]
    if args.max_cases and args.max_cases > 0:
        work = work.head(args.max_cases).copy()

    log(f"Cases to process: {len(work)} (portal={args.portal})")
    rows_long: List[Dict[str, object]] = []
    rows_case: List[Dict[str, object]] = []
    client_cache: Dict[str, Optional[str]] = {}

    # Agile first (fast, requests-only)
    agile = work[work["portal_type_detected"] == "agile"]
    for idx, (_, row) in enumerate(agile.iterrows(), start=1):
        res = fetch_agile_case(row=row, timeout=args.timeout, download=args.download, download_root=download_root, client_cache=client_cache)
        rows_long.extend(res.rows)
        rows_case.append(
            {
                "case_key": res.case_key,
                "PlanningAuthority": res.planning_authority,
                "ApplicationNumber": res.application_number,
                "portal_type": res.portal_type,
                "source_url": res.source_url,
                "status": res.status,
                "error": res.error,
                "all_docs_count": res.all_docs_count,
                "fi_docs_count": res.fi_docs_count,
            }
        )
        if idx % 100 == 0 or idx == len(agile):
            log(f"Agile processed {idx}/{len(agile)}")

    # ePlan next (browser)
    eplan = work[work["portal_type_detected"] == "eplan"]
    if len(eplan) > 0:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=args.headless)
            context = browser.new_context(ignore_https_errors=True, accept_downloads=True)
            page = context.new_page()
            for idx, (_, row) in enumerate(eplan.iterrows(), start=1):
                timeout_ms = max(10000, args.timeout * 1000)
                res = None
                for attempt in range(1, 4):
                    res = fetch_eplan_case(
                        row=row,
                        timeout_ms=timeout_ms,
                        page=page,
                        download=args.download,
                        download_root=download_root,
                    )
                    if res.status != "error":
                        break
                    if should_restart_browser_for_error(res.error):
                        try:
                            context.close()
                        except Exception:
                            pass
                        try:
                            browser.close()
                        except Exception:
                            pass
                        browser = p.chromium.launch(headless=args.headless)
                        context = browser.new_context(ignore_https_errors=True, accept_downloads=True)
                        page = context.new_page()
                        page.wait_for_timeout(500 * attempt)
                        continue
                    page.wait_for_timeout(500 * attempt)
                assert res is not None
                rows_long.extend(res.rows)
                rows_case.append(
                    {
                        "case_key": res.case_key,
                        "PlanningAuthority": res.planning_authority,
                        "ApplicationNumber": res.application_number,
                        "portal_type": res.portal_type,
                        "source_url": res.source_url,
                        "status": res.status,
                        "error": res.error,
                        "all_docs_count": res.all_docs_count,
                        "fi_docs_count": res.fi_docs_count,
                    }
                )
                if idx % 100 == 0 or idx == len(eplan):
                    log(f"ePlan processed {idx}/{len(eplan)}")
            context.close()
            browser.close()

    long_df = pd.DataFrame(rows_long)
    case_df = pd.DataFrame(rows_case)
    long_out.parent.mkdir(parents=True, exist_ok=True)
    case_out.parent.mkdir(parents=True, exist_ok=True)
    long_df.to_csv(long_out, index=False)
    case_df.to_csv(case_out, index=False)

    total_fi_docs = int(long_df["is_fi_doc"].fillna(False).sum()) if not long_df.empty else 0
    total_docs = len(long_df)
    cases_with_fi_docs = int((case_df["fi_docs_count"].fillna(0) > 0).sum()) if not case_df.empty else 0
    log(f"Wrote long docs: {long_out} ({total_docs} rows)")
    log(f"Wrote case summary: {case_out} ({len(case_df)} rows)")
    log(f"FI docs found: {total_fi_docs}")
    log(f"Cases with >=1 FI doc: {cases_with_fi_docs}")
    if not case_df.empty:
        log(f"Status counts: {case_df['status'].value_counts(dropna=False).to_dict()}")


if __name__ == "__main__":
    main()
