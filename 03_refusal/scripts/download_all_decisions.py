#!/usr/bin/env python3
"""
Download decision documents for all rejected Irish planning applications.
Version 3 - Handles multiple council systems and naming conventions.

Assumptions:
- This .py file and the CSV are in the SAME folder.
- The CSV filename is: greater_than_10_units_with_flooding.csv

Output:
- Creates ./downloads/rejected_decisions/ beside this script
- Saves PDFs there
- Writes a log to ./downloads/download_log.txt
"""

import asyncio
import re
import os
import textwrap
import html
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, quote

import pandas as pd
import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


# ----------------------------
# Local paths (relative to this script)
# ----------------------------
BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = Path(os.environ.get("PLANNING_CSV_PATH", "")) if os.environ.get("PLANNING_CSV_PATH") else (BASE_DIR / "greater_than_10_units_with_flooding.csv")

DOWNLOADS_DIR = Path(os.environ.get("PLANNING_DOWNLOADS_DIR", "")) if os.environ.get("PLANNING_DOWNLOADS_DIR") else (BASE_DIR / "downloads")
OUTPUT_DIR = Path(os.environ.get("PLANNING_OUTPUT_DIR", "")) if os.environ.get("PLANNING_OUTPUT_DIR") else (DOWNLOADS_DIR / "rejected_decisions")
LOG_FILE = Path(os.environ.get("PLANNING_LOG_PATH", "")) if os.environ.get("PLANNING_LOG_PATH") else (DOWNLOADS_DIR / "download_log.txt")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)


def safe_filename(s: str) -> str:
    """Make a string safe for Windows/macOS/Linux filenames."""
    s = s.strip().replace(" ", "_").replace("/", "_").replace("\\", "_")
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s)
    return s[:180]


def reason_filename_from_pdf(filename: str) -> str:
    """Create fallback reason filename from standard PDF filename."""
    if filename.lower().endswith(".pdf"):
        return filename[:-4] + "_Reasons.txt"
    return filename + "_Reasons.txt"


def djvu_filename_from_pdf(filename: str) -> str:
    """Create DJVU filename from the standard PDF filename."""
    if filename.lower().endswith(".pdf"):
        return filename[:-4] + ".djvu"
    return filename + ".djvu"


def convert_djvu_to_pdf(djvu_path: Path, pdf_path: Path) -> bool:
    """Convert a DJVU file to PDF if a converter is available."""
    try:
        if not djvu_path.exists():
            return False
        pdf_path.parent.mkdir(parents=True, exist_ok=True)

        # Prefer ddjvu if installed.
        ddjvu = shutil.which("ddjvu")
        if not ddjvu:
            candidate = Path(r"C:\\Program Files (x86)\\DjVuLibre\\ddjvu.exe")
            if candidate.exists():
                ddjvu = str(candidate)
        if ddjvu:
            result = subprocess.run(
                [ddjvu, "-format=pdf", str(djvu_path), str(pdf_path)],
                check=False,
                capture_output=True,
                text=True,
            )
            return result.returncode == 0 and pdf_path.exists()

        # ImageMagick can also convert DJVU to PDF.
        magick = shutil.which("magick")
        if magick:
            result = subprocess.run(
                [magick, str(djvu_path), str(pdf_path)],
                check=False,
                capture_output=True,
                text=True,
            )
            return result.returncode == 0 and pdf_path.exists()

        # djvutops + Ghostscript pipeline.
        djvutops = shutil.which("djvutops")
        gs = shutil.which("gswin64c") or shutil.which("gswin32c") or shutil.which("gs")
        if djvutops and gs:
            ps_path = pdf_path.with_suffix(".ps")
            try:
                result_ps = subprocess.run(
                    [djvutops, str(djvu_path)],
                    check=False,
                    capture_output=True,
                )
                if result_ps.returncode != 0:
                    return False
                with open(ps_path, "wb") as f:
                    f.write(result_ps.stdout)
                result_gs = subprocess.run(
                    [
                        gs,
                        "-sDEVICE=pdfwrite",
                        "-dNOPAUSE",
                        "-dBATCH",
                        f"-sOutputFile={pdf_path}",
                        str(ps_path),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                return result_gs.returncode == 0 and pdf_path.exists()
            finally:
                if ps_path.exists():
                    ps_path.unlink(missing_ok=True)

        return False
    except Exception:
        return False


def normalize_document_href(href: str, base_url: str) -> str:
    """Normalize plain/relative/javascript links to an absolute URL when possible."""
    if not href:
        return ""

    href = href.strip()
    if href.lower().startswith("javascript:"):
        matches = re.findall(r"""['"]([^'"]+)['"]""", href)
        href = matches[0].strip() if matches else ""

    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("//"):
        return f"https:{href}"

    return urljoin(base_url, href)


def normalize_app_details_url(council_name: str, app_num: str, app_url: str) -> str:
    """Fix known malformed app-detail URLs before scraping."""
    url = (app_url or "").strip()
    if url.lower() in {"nan", "none", "nat"}:
        url = ""
    council = (council_name or "").lower()
    low = url.lower()
    council_slug_map = {
        "dublin city council": "dublincity",
        "fingal county council": "fingal",
        "south dublin county council": "southdublin",
        "dun laoghaire rathdown county council": "dunlaoghaire",
    }

    # Some source rows have blank LinkAppDetails for Agile councils.
    # Return a minimal Agile base URL so app id can be resolved from app reference.
    if not url:
        slug = council_slug_map.get(council)
        if slug:
            return f"https://planning.agileapplications.ie/{slug}/"
        return url

    # Cork County data can contain placeholder Odyssey host `planninglive`.
    if "cork county council" in council and "planninglive/odyssey" in low:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query or "")
        year_file = (qs.get("yearAndFileNo") or [""])[0]
        normalized_ref = (app_num or "").strip()
        if "/" in year_file:
            year, file_no = year_file.split("/", 1)
            year_digits = "".join(ch for ch in year if ch.isdigit())
            file_digits = "".join(ch for ch in file_no if ch.isdigit())
            if year_digits and file_digits:
                normalized_ref = f"{int(year_digits):02d}{file_digits}"
        if not normalized_ref:
            return url
        return f"https://planning.corkcoco.ie/ePlan/AppFileRefDetails/{normalized_ref}/0"

    return url


def download_binary_file(url: str, file_path: Path, timeout: int = 60, headers=None, require_pdf: bool = True) -> bool:
    """Download a file with requests and save to disk."""
    try:
        response = requests.get(url, timeout=timeout, headers=headers)
        if response.status_code >= 400:
            return False
        if not response.content:
            return False
        if require_pdf:
            content_type = (response.headers.get("content-type") or "").lower()
            starts_with_pdf = response.content.startswith(b"%PDF")
            if "pdf" not in content_type and not starts_with_pdf:
                return False
        with open(file_path, "wb") as f:
            f.write(response.content)
        return True
    except Exception:
        return False


def looks_like_djvu_reference(url_or_text: str) -> bool:
    """Best-effort check whether a URL/reference points to DJVU content."""
    s = (url_or_text or "").lower()
    return ".djvu" in s or "format=djvu" in s


def looks_like_jpeg_reference(url_or_text: str) -> bool:
    """Return True when link appears to be a JPEG preview rendition."""
    s = (url_or_text or "").lower()
    return "format=jpeg" in s or s.endswith(".jpg") or s.endswith(".jpeg")


def download_djvu_file(url: str, file_path: Path, timeout: int = 60, headers=None) -> bool:
    """Download a DJVU file and validate that payload is not an HTML wrapper."""
    try:
        response = requests.get(url, timeout=timeout, headers=headers)
        if response.status_code >= 400 or not response.content:
            return False

        content_type = (response.headers.get("content-type") or "").lower()
        # Many valid DJVU files start with this magic marker.
        djvu_magic = response.content.startswith(b"AT&TFORM")
        likely_html = b"<html" in response.content[:300].lower() or "text/html" in content_type
        is_djvu_type = "djvu" in content_type

        if not djvu_magic and not is_djvu_type:
            return False
        if likely_html and not djvu_magic:
            return False

        with open(file_path, "wb") as f:
            f.write(response.content)
        return True
    except Exception:
        return False


def save_reasons_text_file(
    file_path: Path,
    council_name: str,
    application_reference: str,
    decision_text: str,
    decision_date: str,
    reasons: list,
) -> bool:
    """Write extracted refusal reasons to a readable text file."""
    try:
        if not reasons:
            return False
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("Planning Decision Reasons (Fallback)\n")
            f.write("=" * 60 + "\n")
            f.write(f"Council: {council_name}\n")
            f.write(f"Application: {application_reference}\n")
            f.write(f"Decision: {decision_text}\n")
            f.write(f"Decision date: {decision_date}\n\n")
            f.write("Reasons for refusal:\n")
            f.write("-" * 60 + "\n\n")
            for idx, reason in enumerate(reasons, start=1):
                wrapped = textwrap.fill(reason.strip(), width=110)
                f.write(f"{idx}. {wrapped}\n\n")
        return True
    except Exception:
        return False


def save_decision_summary_text_file(
    file_path: Path,
    council_name: str,
    application_reference: str,
    decision_text: str,
    decision_date: str,
    notes: str,
) -> bool:
    """Write a minimal decision summary when no detailed reason document exists."""
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("Planning Decision Summary (Fallback)\n")
            f.write("=" * 60 + "\n")
            f.write(f"Council: {council_name}\n")
            f.write(f"Application: {application_reference}\n")
            f.write(f"Decision: {decision_text}\n")
            f.write(f"Decision date: {decision_date}\n\n")
            f.write(notes.strip() + "\n")
        return True
    except Exception:
        return False


def extract_refusal_reasons_from_conditions(conditions: dict) -> list:
    """Extract refusal reason text from Agile 'conditions' payload."""
    reasons = []
    prescriptions = conditions.get("applicationPrescriptions") or []
    for item in prescriptions:
        code = (item.get("prescriptionCode") or "").strip().upper()
        code_desc = (item.get("prescriptionCodeDescription") or "").lower()
        text = (item.get("longPrescription") or "").strip()
        if not text:
            continue
        # Prefer explicit refusal reason entries.
        if code == "R" or "reason" in code_desc:
            reasons.append(text)

    # Fallback: if no explicit reason code, keep all prescriptions.
    if not reasons:
        for item in prescriptions:
            text = (item.get("longPrescription") or "").strip()
            if text:
                reasons.append(text)

    # Deduplicate while preserving order.
    deduped = []
    seen = set()
    for r in reasons:
        key = r.strip().lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped


def get_decision_keywords():
    """
    Return keywords to search for decision documents, in priority order.
    Returns list of (keyword, priority) where lower priority = higher importance.
    """
    return [
        # Priority 1: The actual signed decision/order
        ("decision - grant/refusal", 1),
        ("decision grant/refusal", 1),
        ("decision - refusal", 1),
        ("decision refusal", 1),
        ("notification of refusal", 1),
        ("refusal order", 1),
        ("r2", 1),
        ("rp", 1),
        ("m.o. signed", 1),
        ("managers order", 1),
        ("manager's order", 1),
        ("decision maker", 1),
        ("decision makers order", 1),
        ("schedule of refusal reasons", 1),
        ("notification of decison refusal", 1),
        ("notification of decision refusal", 1),
        ("chief executive's order", 1),
        ("chief executives order", 1),
        ("chief executive order", 1),
        
        # Priority 2: Decision notifications and reports
        ("notification of decision", 2),
        ("decision notification", 2),
        ("planners recommendation", 2),
        ("planner's recommendation", 2),
        ("planners report", 2),
        ("planner's report", 2),
        ("planning report", 2),
        
        # Priority 3: Generic decision/refusal terms (use with caution)
        ("refusal", 3),
        ("refused", 3),
        ("decision", 3),
        # Priority 4: Reports (last-resort when no decision docs exist)
        ("reports", 4),
        ("report", 4),
    ]


def is_non_decision_document(doc: dict) -> bool:
    """Return True for document types we should never use as final refusal evidence."""
    searchable = f"{doc.get('type', '').lower()} {doc.get('comment', '').lower()} {doc.get('href', '').lower()}"
    excluded_terms = [
        "pre-planning report",
        "pre planning report",
        "preplanning report",
    ]
    return any(term in searchable for term in excluded_terms)


def _has_token(text: str, token: str) -> bool:
    return bool(re.search(rf"(^|[^a-z0-9]){re.escape(token)}([^a-z0-9]|$)", text.lower()))


def _parse_doc_date(doc: dict):
    """Extract a comparable datetime from doc fields when possible."""
    date_candidates = [
        str(doc.get("date", "")).strip(),
        str(doc.get("comment", "")).strip(),
        str(doc.get("type", "")).strip(),
    ]
    patterns = ["%d/%m/%Y", "%d/%m/%y"]
    for candidate in date_candidates:
        if not candidate:
            continue
        for match in re.findall(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", candidate):
            for fmt in patterns:
                try:
                    return datetime.strptime(match, fmt)
                except ValueError:
                    continue
    return datetime.min


def _doc_flags(doc: dict):
    searchable = f"{doc.get('type', '')} {doc.get('comment', '')} {doc.get('href', '')}".lower()
    fi_terms = [
        "further information",
        "revised plans",
        "clarification/revised plans",
        "request for further information",
        "response to fi",
        "fi plans",
    ]
    has_fi = any(term in searchable for term in fi_terms) or _has_token(searchable, "fi")
    has_rp = _has_token(searchable, "rp")
    has_r2 = _has_token(searchable, "r2")
    has_refusal = any(term in searchable for term in ["refuse", "refusal", "decision to refuse"])
    is_planners_report = any(term in searchable for term in ["planners report", "planner's report"])
    return {
        "fi": has_fi,
        "rp": has_rp,
        "r2": has_r2,
        "refusal": has_refusal,
        "planners_report": is_planners_report,
    }


def find_best_document(documents, council_name=""):
    """
    Find the best document to download based on document type.
    Returns the best matching document or None.
    """
    keywords = get_decision_keywords()

    def keyword_match(candidates):
        best_match = None
        # Lower score is better.
        # (keyword_priority, fi_penalty, planners_penalty, preview_penalty, r2_rp_penalty, refusal_penalty, recency_rank)
        best_score = (999, 1, 1, 1, 1, 1, 0)
        for doc in candidates:
            if is_non_decision_document(doc):
                continue
            doc_type = doc.get('type', '').lower()
            doc_comment = doc.get('comment', '').lower()
            doc_href = doc.get('href', '').lower()
            searchable = f"{doc_type} {doc_comment} {doc_href}"
            preview_penalty = 1 if looks_like_jpeg_reference(doc_href) else 0
            flags = _doc_flags(doc)
            recency_rank = -_parse_doc_date(doc).toordinal()

            for keyword, priority in keywords:
                keyword_hit = keyword in searchable
                if keyword in {"r2", "rp"}:
                    keyword_hit = _has_token(searchable, keyword)
                if keyword_hit:
                    score = (
                        priority,
                        1 if flags["fi"] else 0,
                        1 if flags["planners_report"] else 0,
                        preview_penalty,
                        0 if (flags["r2"] or flags["rp"]) else 1,
                        0 if flags["refusal"] else 1,
                        recency_rank,
                    )
                    if score < best_score:
                        best_score = score
                        best_match = doc
                        break
        return best_match

    # Strong preference: explicit RP/R2 docs (non-FI), newest first.
    explicit_finalists = []
    for doc in documents:
        if is_non_decision_document(doc):
            continue
        flags = _doc_flags(doc)
        if (flags["r2"] or flags["rp"]) and not flags["fi"]:
            explicit_finalists.append(doc)
    if explicit_finalists:
        explicit_finalists.sort(
            key=lambda d: (
                0 if _doc_flags(d)["refusal"] else 1,
                1 if _doc_flags(d)["planners_report"] else 0,
                -_parse_doc_date(d).toordinal(),
            )
        )
        return explicit_finalists[0]

    non_jpeg_docs = [d for d in documents if not looks_like_jpeg_reference(d.get("href", ""))]
    best_match = keyword_match(non_jpeg_docs)
    if best_match:
        return best_match

    best_match = keyword_match(documents)
    if best_match:
        return best_match

    # Fallback 1: still prefer obvious refusal/decision terms from type/comment/href.
    for doc in non_jpeg_docs + documents:
        if is_non_decision_document(doc):
            continue
        flags = _doc_flags(doc)
        if flags["fi"]:
            continue
        searchable = f"{doc.get('type', '').lower()} {doc.get('comment', '').lower()} {doc.get('href', '').lower()}"
        if any(term in searchable for term in ["refus", "decision", "order", "planners report", "planner's report"]):
            return doc

    # Fallback 2: some councils store everything as one consolidated file.
    for doc in documents:
        if is_non_decision_document(doc):
            continue
        searchable = f"{doc.get('type', '').lower()} {doc.get('comment', '').lower()}"
        if "consolidated application" in searchable:
            return doc

    # Fallback 3: if there is only one option, take it.
    filtered_docs = [doc for doc in documents if not is_non_decision_document(doc)]
    if len(filtered_docs) == 1:
        return filtered_docs[0]

    # Optional fallback: allow correspondence when nothing else exists (e.g., Galway City).
    allow_correspondence = os.environ.get("PLANNING_ALLOW_CORRESPONDENCE", "").strip().lower() in {"1", "true", "yes"}
    if allow_correspondence:
        for doc in non_jpeg_docs + documents:
            if is_non_decision_document(doc):
                continue
            searchable = f"{doc.get('type', '').lower()} {doc.get('comment', '').lower()}"
            if "correspondence" in searchable:
                return doc

    # Last-resort fallback for capture/completeness runs.
    allow_any_doc = os.environ.get("PLANNING_ALLOW_ANY_DOC", "").strip().lower() in {"1", "true", "yes"}
    if allow_any_doc:
        for doc in non_jpeg_docs + documents:
            if is_non_decision_document(doc):
                continue
            return doc

    return None


def parse_idocs_documents(soup):
    """Parse documents from iDocsWebDPSS system (most councils)."""
    rows = soup.find_all("tr")
    documents = []
    
    for row in rows:
        cells = row.find_all("td")
        if len(cells) >= 4:
            doc_type = cells[0].get_text(strip=True)
            comment = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            num_files = cells[2].get_text(strip=True) if len(cells) > 2 else ""
            size = cells[3].get_text(strip=True) if len(cells) > 3 else ""
            
            low_doc_type = doc_type.lower()
            if (
                doc_type
                and doc_type not in ["Type", ""]
                and not doc_type.startswith("Note:")
                and len(doc_type) < 180
                and "planning application" not in low_doc_type
                and "order by" not in low_doc_type
                and "files may be in either" not in low_doc_type
            ):
                links = row.find_all("a")
                if links:
                    href = ""
                    # Prefer the actual file link over JPG preview links.
                    for link in links:
                        candidate = (link.get("href") or "").strip()
                        if not candidate:
                            continue
                        if "format=jpeg" in candidate.lower():
                            continue
                        href = candidate
                        break
                    if not href:
                        href = (links[0].get("href") or "").strip()

                    if href:
                        documents.append({
                            "type": doc_type,
                            "comment": comment,
                            "files": num_files,
                            "size": size,
                            "href": href
                        })
    
    return documents


def parse_donegal_documents(soup):
    """Parse documents from Donegal's eplan.donegalcoco.ie system."""
    table = soup.find('table')
    if not table:
        return []
    
    rows = table.find_all('tr')
    documents = []
    
    for row in rows:
        cells = row.find_all('td')
        if len(cells) >= 2:
            doc_type = cells[1].get_text(strip=True) if len(cells) > 1 else cells[0].get_text(strip=True)
            date = cells[2].get_text(strip=True) if len(cells) > 2 else ""
            comment = cells[3].get_text(strip=True) if len(cells) > 3 else ""
            view_cell = cells[-1]
            
            # Find the link in the view cell
            link = view_cell.find('a')
            if link:
                href = link.get('href')
                documents.append({
                    "type": doc_type,
                    "comment": comment,
                    "date": date,
                    "href": href
                })
    
    return documents


async def download_from_idocs(page, popup_url, base_url, output_dir, filename, council_name="", app_num=""):
    """Download document from iDocsWebDPSS system."""
    if "planningdocs.corkcoco.ie" in (popup_url or "").lower() and "/planningdocumentdisplay/documents/" in (popup_url or "").lower():
        return await download_from_cork_planningdocs(page, popup_url, output_dir, filename, council_name, app_num=app_num)

    async def try_download_djvu_with_browser(djvu_url: str, djvu_path: Path) -> bool:
        """Use Playwright navigation to retrieve DJVU, including HTML wrapper pages."""
        tried = set()
        queue = [djvu_url]

        while queue:
            current = queue.pop(0)
            if not current or current in tried:
                continue
            tried.add(current)
            try:
                # First try Playwright's request context (handles some hosts that reject plain requests).
                try:
                    api_resp = await page.context.request.get(current, timeout=45000)
                    api_ct = (api_resp.headers.get("content-type") or "").lower()
                    api_body = await api_resp.body()
                    if api_body and api_body.startswith(b"AT&TFORM"):
                        with open(djvu_path, "wb") as f:
                            f.write(api_body)
                        return True
                    if api_body and "djvu" in api_ct and b"<html" not in api_body[:300].lower():
                        with open(djvu_path, "wb") as f:
                            f.write(api_body)
                        return True
                    if api_body and "html" in api_ct:
                        wrapper_soup = BeautifulSoup(api_body, "html.parser")
                        for selector, attr in [("embed", "src"), ("object", "data"), ("param", "value"), ("a", "href"), ("iframe", "src")]:
                            for tag in wrapper_soup.select(selector):
                                candidate = (tag.get(attr) or "").strip()
                                if not candidate or not looks_like_djvu_reference(candidate):
                                    continue
                                candidate = candidate.replace("\\", "/")
                                if candidate.startswith("./") or candidate.startswith(".//"):
                                    candidate = candidate.lstrip("./")
                                if candidate.startswith("."):
                                    candidate = candidate[1:]
                                resolved = normalize_document_href(candidate, current)
                                if resolved not in tried:
                                    queue.append(resolved)
                except Exception:
                    pass

                # Direct file endpoints can trigger browser download events.
                try:
                    async with page.expect_download(timeout=4000) as download_info:
                        await page.goto(current, wait_until="domcontentloaded", timeout=45000)
                    download = await download_info.value
                    await download.save_as(str(djvu_path))
                    payload = djvu_path.read_bytes() if djvu_path.exists() else b""
                    if payload.startswith(b"AT&TFORM"):
                        return True
                    if djvu_path.exists():
                        djvu_path.unlink(missing_ok=True)
                except PlaywrightTimeoutError:
                    pass

                response = await page.goto(current, wait_until="domcontentloaded", timeout=45000)
                content_type = ((response.headers.get("content-type") if response else "") or "").lower()
                body = await response.body() if response else b""
                if body and body.startswith(b"AT&TFORM"):
                    with open(djvu_path, "wb") as f:
                        f.write(body)
                    return True
                if body and "djvu" in content_type and b"<html" not in body[:300].lower():
                    with open(djvu_path, "wb") as f:
                        f.write(body)
                    return True

                html = await page.content()
                wrapper_soup = BeautifulSoup(html, "html.parser")
                for selector, attr in [("embed", "src"), ("object", "data"), ("param", "value"), ("a", "href"), ("iframe", "src")]:
                    for tag in wrapper_soup.select(selector):
                        candidate = (tag.get(attr) or "").strip()
                        if not candidate:
                            continue
                        if not looks_like_djvu_reference(candidate):
                            continue
                        candidate = candidate.replace("\\", "/")
                        if candidate.startswith("./") or candidate.startswith(".//"):
                            candidate = candidate.lstrip("./")
                        if candidate.startswith("."):
                            candidate = candidate[1:]
                        resolved = normalize_document_href(candidate, current)
                        if resolved not in tried:
                            queue.append(resolved)
            except Exception:
                continue

        return False

    # Go to file list
    file_list_url = (
        popup_url.replace("copyright.aspx", "listFiles.aspx")
        .replace("Copyright.aspx", "listFiles.aspx")
    )
    if "?" in file_list_url:
        file_list_url += "&orderBy=type"
    else:
        file_list_url += "?orderBy=type"
    
    last_goto_err = None
    for _ in range(3):
        try:
            await page.goto(file_list_url, wait_until="domcontentloaded", timeout=30000)
            last_goto_err = None
            break
        except Exception as exc:
            last_goto_err = exc
            await asyncio.sleep(1.5)
    if last_goto_err:
        raise last_goto_err
    
    # Handle copyright page if needed
    if "copyright" in page.url.lower():
        try:
            view_files_btn = page.locator("input#btnViewFiles")
            if await view_files_btn.count() > 0:
                await page.check("input#chkAgree")
                await page.click("input#btnViewFiles")
                await page.wait_for_load_state("domcontentloaded")
            else:
                await page.check("input#chkAgree")
                await asyncio.sleep(1)
                view_files_btn = page.locator("input#btnViewFiles")
                if await view_files_btn.count() > 0:
                    await page.click("input#btnViewFiles")
                    await page.wait_for_load_state("domcontentloaded")
        except Exception:
            pass
    
    content = await page.content()
    soup = BeautifulSoup(content, "html.parser")
    
    documents = parse_idocs_documents(soup)
    
    if not documents:
        return "no_documents", None
    
    best_doc = find_best_document(documents, council_name)
    
    if not best_doc:
        doc_types = [d['type'] for d in documents[:5]]
        return f"no_match: {doc_types}", None
    
    decision_href = best_doc.get("href", "")
    full_url = normalize_document_href(decision_href, page.url or popup_url)
    if not full_url:
        return "no_link", best_doc.get("type")

    file_path = output_dir / filename
    # Fast path: many systems expose the PDF directly and can be fetched with requests.
    if download_binary_file(full_url, file_path):
        return "success", best_doc["type"]

    response = None
    try:
        async with page.expect_download(timeout=5000) as download_info:
            response = await page.goto(full_url, wait_until="domcontentloaded", timeout=45000)
        download = await download_info.value
        await download.save_as(str(file_path))
        return "success", best_doc['type']
    except PlaywrightTimeoutError:
        # No direct download event; continue with HTML/PDF parsing.
        response = await page.goto(full_url, wait_until="domcontentloaded", timeout=45000)

    response_headers = response.headers if response else {}
    content_type = (response_headers.get("content-type") or "").lower()

    # Some councils link directly to the PDF.
    file_path = output_dir / filename
    if response:
        try:
            response_bytes = await response.body()
        except Exception:
            response_bytes = b""
        if ("pdf" in content_type or full_url.lower().endswith(".pdf") or response_bytes.startswith(b"%PDF")) and response_bytes:
            with open(file_path, "wb") as f:
                f.write(response_bytes)
            return "success", best_doc['type']
    
    doc_content = await page.content()
    doc_soup = BeautifulSoup(doc_content, "html.parser")
    iframe = doc_soup.find("iframe")
    
    if iframe:
        iframe_src = iframe.get("src") or ""
        pdf_url = normalize_document_href(iframe_src, full_url)
        if pdf_url:
            if looks_like_djvu_reference(pdf_url):
                djvu_path = output_dir / djvu_filename_from_pdf(filename)
                if await try_download_djvu_with_browser(pdf_url, djvu_path):
                    pdf_path = file_path
                    if convert_djvu_to_pdf(djvu_path, pdf_path):
                        return "success_djvu_pdf", best_doc["type"]
                    return "success_djvu", best_doc['type']
            if download_binary_file(pdf_url, file_path):
                return "success", best_doc['type']

    # Fallback: some systems put the PDF in object/embed/a tags.
    pdf_candidates = []
    for tag_name, attr in [("embed", "src"), ("object", "data"), ("a", "href")]:
        for tag in doc_soup.find_all(tag_name):
            value = (tag.get(attr) or "").strip()
            if value and (".pdf" in value.lower() or "document" in value.lower()):
                pdf_candidates.append(value)

    for candidate in pdf_candidates:
        pdf_url = normalize_document_href(candidate, full_url)
        if not pdf_url:
            continue
        if looks_like_djvu_reference(pdf_url):
            djvu_path = output_dir / djvu_filename_from_pdf(filename)
            if await try_download_djvu_with_browser(pdf_url, djvu_path):
                pdf_path = file_path
                if convert_djvu_to_pdf(djvu_path, pdf_path):
                    return "success_djvu_pdf", best_doc["type"]
                return "success_djvu", best_doc['type']
        if download_binary_file(pdf_url, file_path):
            return "success", best_doc['type']

    # Some systems (e.g., Galway ViewPDF.aspx) are directly downloadable.
    if download_binary_file(full_url, file_path):
        return "success", best_doc['type']

    return "no_iframe", best_doc['type']


def _cork_tree_has_documents(tree) -> bool:
    """Return True when Cork PlanningDocumentDisplay tree contains at least one file-like node."""
    if not isinstance(tree, list):
        return False

    stack = list(tree)
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("Id") or "")
        doc_url = str(node.get("DocUrl") or "").strip()
        children = node.get("Documents") or []
        # Leaf file nodes commonly use pipe-delimited Id, but some payloads expose DocUrl.
        if "|" in node_id or doc_url:
            return True
        if isinstance(children, list):
            stack.extend(children)
    return False


def _cork_ref_candidates(app_ref: str, app_num: str) -> list[str]:
    """Generate candidate PlanningDocumentDisplay refs for Cork fallback probing."""
    candidates = []
    base_ref = (app_ref or "").strip()
    if base_ref:
        candidates.append(base_ref)

    app_num_clean = (app_num or "").strip()
    digits = "".join(ch for ch in app_num_clean if ch.isdigit())
    digits_no_zero = digits.lstrip("0") or "0"

    for raw in [app_num_clean, digits, digits_no_zero]:
        if not raw:
            continue
        candidates.append(raw)
        candidates.append(f"18a-{raw}")

    deduped = []
    seen = set()
    for cand in candidates:
        key = cand.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cand)
    return deduped


async def download_from_cork_planningdocs(page, popup_url, output_dir, filename, council_name="", app_num=""):
    """Download decision document from Cork County PlanningDocumentDisplay API."""
    try:
        match = re.search(r"/documents/([^/?#]+)", popup_url, flags=re.IGNORECASE)
        if not match:
            return "no_documents", None
        app_ref = match.group(1).strip()
        base = "https://planningdocs.corkcoco.ie/PlanningDocumentDisplay"
        tree = None
        used_ref = None
        for ref in _cork_ref_candidates(app_ref, app_num):
            api_url = f"{base}/api/Documents/{ref}"
            api_resp = await page.context.request.get(api_url, timeout=60000)
            if api_resp.status >= 400:
                continue
            candidate_tree = await api_resp.json()
            if _cork_tree_has_documents(candidate_tree):
                tree = candidate_tree
                used_ref = ref
                break
            # Keep the first successful payload as a fallback for diagnostics.
            if tree is None and isinstance(candidate_tree, list):
                tree = candidate_tree
                used_ref = ref
        if tree is None or not _cork_tree_has_documents(tree):
            return "no_documents", None

        documents = []

        def walk(node, trail):
            title = (node.get("Title") or "").strip()
            node_id = (node.get("Id") or "").strip()
            doc_url = (node.get("DocUrl") or "").strip()
            children = node.get("Documents") or []
            current = trail + ([title] if title else [])

            if doc_url:
                documents.append(
                    {
                        "type": title,
                        "comment": " > ".join(current[:-1]),
                        "href": doc_url,
                    }
                )
            elif isinstance(node_id, str) and "|" in node_id and not children:
                parts = node_id.split("|", 2)
                if len(parts) == 3:
                    _doc_num, guid, file_name = parts
                    display_url = f"{base}/Documents/Display/{quote(file_name)}/{guid}"
                    documents.append(
                        {
                            "type": title,
                            "comment": " > ".join(current[:-1]),
                            "href": display_url,
                        }
                    )

            for child in children:
                walk(child, current)

        for root in tree:
            walk(root, [])

        if not documents:
            return "no_documents", None

        best_doc = find_best_document(documents, council_name)
        if not best_doc:
            doc_types = [d["type"] for d in documents[:5]]
            return f"no_match: {doc_types}", None

        file_url = best_doc.get("href", "")
        if not file_url:
            return "no_link", best_doc.get("type")

        file_path = output_dir / filename
        dl_resp = await page.context.request.get(file_url, timeout=90000)
        if dl_resp.status >= 400:
            return "no_file_url", best_doc.get("type")
        payload = await dl_resp.body()
        if not payload:
            return "no_file_url", best_doc.get("type")

        content_type = (dl_resp.headers.get("content-type") or "").lower()
        if "pdf" in content_type or payload.startswith(b"%PDF"):
            with open(file_path, "wb") as f:
                f.write(payload)
            return "success", best_doc.get("type")

        # Some entries can be non-PDF; save only if meaningful binary content exists.
        with open(file_path, "wb") as f:
            f.write(payload)
        return "success", best_doc.get("type")
    except Exception as e:
        return f"error: {str(e)[:80]}", None


async def download_from_donegal(page, popup_url, output_dir, filename):
    """Download document from Donegal's eplan system using Playwright."""
    try:
        await page.goto(popup_url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(1500)
        soup = BeautifulSoup(await page.content(), "html.parser")

        documents = parse_donegal_documents(soup)
        if not documents:
            return "no_documents", None

        best_doc = find_best_document(documents, "Donegal")
        if not best_doc:
            doc_types = [d["type"] for d in documents[:5]]
            return f"no_match: {doc_types}", None

        href = (best_doc.get("href") or "").strip()
        file_path = output_dir / filename

        # Donegal links are ASP.NET postbacks; trigger download via Playwright.
        postback_match = re.search(r"__doPostBack\('([^']*)','([^']*)'\)", href or "")
        if postback_match:
            event_target, _event_argument = postback_match.groups()
            link = page.locator(f"a[href*=\"{event_target}\"]")
            if await link.count() == 0:
                return "no_file_url", best_doc.get("type")

            async with page.expect_download(timeout=60000) as download_info:
                await link.first.click()
            download = await download_info.value

            suggested = (download.suggested_filename or "").strip()
            if suggested:
                suffix = Path(suggested).suffix
                if suffix and suffix.lower() != ".pdf":
                    file_path = output_dir / f"{Path(filename).stem}{suffix}"
            await download.save_as(str(file_path))
            return "success", best_doc["type"]

        # If not a postback, handle as a standard URL.
        file_url = normalize_document_href(href, "https://eplan.donegalcoco.ie/")
        if not file_url:
            return "no_file_url", best_doc.get("type")
        if download_binary_file(file_url, file_path, require_pdf=False):
            return "success", best_doc["type"]
        return "no_file_url", best_doc.get("type")

    except Exception as e:
        return f"error: {str(e)[:50]}", None


def get_agile_client_code(client_slug: str):
    """Resolve planning.agileapplications.ie client code from URL slug."""
    try:
        response = requests.get(
            "https://identity.agileapplications.ie/api/client/get",
            params={"url": client_slug},
            timeout=30,
        )
        data = response.json()
        code = data.get("code")
        if code:
            return code
    except Exception:
        pass
    return None


def resolve_agile_app_id(client_slug: str, app_ref: str, client_code: str):
    """Resolve Agile application id from a human-readable application reference."""
    ref = (app_ref or "").strip()
    if not ref:
        return None
    headers = {
        "x-service": "PA",
        "x-product": "CITIZENPORTAL",
        "x-client": client_code,
        "accept": "application/json, text/plain, */*",
        "referer": "https://planning.agileapplications.ie/",
    }
    try:
        response = requests.get(
            "https://planningapi.agileapplications.ie/api/application/search",
            headers=headers,
            params={"query": ref, "page": 1},
            timeout=60,
        )
        if response.status_code >= 400:
            return None
        payload = response.json()
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list) or not results:
            return None

        ref_up = ref.upper()
        for item in results:
            if not isinstance(item, dict):
                continue
            candidate_ref = str(item.get("reference") or "").strip().upper()
            candidate_id = str(item.get("id") or "").strip()
            if candidate_ref == ref_up and candidate_id.isdigit():
                return candidate_id

        first = results[0] if isinstance(results[0], dict) else {}
        first_id = str(first.get("id") or "").strip()
        if first_id.isdigit():
            return first_id
    except Exception:
        return None
    return None


async def download_from_agile(app_url: str, output_dir: Path, filename: str, app_ref: str = ""):
    """
    Download decision document from planning.agileapplications.ie.
    Uses direct API calls (faster + avoids brittle UI scraping).
    """
    parsed = urlparse(app_url)
    parts = [p for p in parsed.path.split("/") if p]
    # Expected: /{client_slug}/application-details/{id}
    if len(parts) < 1:
        return "bad_agile_url", None

    client_slug = parts[0]
    client_code = get_agile_client_code(client_slug)
    if not client_code:
        return "no_agile_client", None
    app_id = parts[-1] if (len(parts) >= 3 and str(parts[-1]).isdigit()) else ""
    if not app_id:
        app_id = resolve_agile_app_id(client_slug=client_slug, app_ref=app_ref, client_code=client_code) or ""
    if not app_id:
        return "bad_agile_url", None

    headers = {
        "x-service": "PA",
        "x-product": "CITIZENPORTAL",
        "x-client": client_code,
        "accept": "application/json, text/plain, */*",
        "referer": "https://planning.agileapplications.ie/",
    }

    docs_url = f"https://planningapi.agileapplications.ie/api/application/{app_id}/document"
    app_details = {}
    try:
        app_response = requests.get(
            f"https://planningapi.agileapplications.ie/api/application/{app_id}",
            headers=headers,
            timeout=60,
        )
        if app_response.status_code == 200:
            app_details = app_response.json() or {}

        docs_response = requests.get(docs_url, headers=headers, timeout=60)
        if docs_response.status_code >= 400:
            return f"error: agile documents {docs_response.status_code}", None
        documents_raw = docs_response.json()
    except Exception as e:
        return f"error: {str(e)[:50]}", None

    def try_save_reasons_fallback():
        """Fallback to refusal reasons when no downloadable decision document exists."""
        try:
            conditions_response = requests.get(
                f"https://planningapi.agileapplications.ie/api/application/{app_id}/conditions",
                headers=headers,
                timeout=60,
            )
            if conditions_response.status_code >= 400:
                return False
            conditions = conditions_response.json() or {}
            reasons = extract_refusal_reasons_from_conditions(conditions)

            out_name = reason_filename_from_pdf(filename)
            out_path = output_dir / out_name
            council_name = app_details.get("authorityName") or client_slug
            app_ref = app_details.get("reference") or app_id
            decision_text = conditions.get("decisionText") or app_details.get("decisionText") or "Unknown"
            decision_date = conditions.get("decisionDate") or app_details.get("decisionDate") or ""
            if save_reasons_text_file(
                out_path,
                str(council_name),
                str(app_ref),
                str(decision_text),
                str(decision_date),
                reasons,
            ):
                return True

            # If no detailed reasons exist, still save a summary for refused decisions.
            decision_upper = str(decision_text).upper()
            if "REFUSE" in decision_upper:
                notes = (
                    "No detailed refusal reasons were available in the council's public document API "
                    "for this record. This summary was generated from available metadata."
                )
                if save_decision_summary_text_file(
                    out_path,
                    str(council_name),
                    str(app_ref),
                    str(decision_text),
                    str(decision_date),
                    notes,
                ):
                    return True
        except Exception:
            return False
        return False

    if not isinstance(documents_raw, list) or not documents_raw:
        if try_save_reasons_fallback():
            return "success_reasons", "API refusal reasons"
        return "no_documents", None

    documents = []
    for doc in documents_raw:
        doc_type = doc.get("description") or doc.get("mediaDescription") or ""
        comment = f"{doc.get('mediaDescription', '')} {doc.get('name', '')}".strip()
        href = doc.get("documentHash", "")
        documents.append(
            {
                "type": doc_type,
                "comment": comment,
                "href": href,
                "name": doc.get("name", ""),
            }
        )

    best_doc = find_best_document(documents)
    if not best_doc:
        if try_save_reasons_fallback():
            return "success_reasons", "API refusal reasons"
        doc_types = [d["type"] for d in documents[:5]]
        return f"no_match: {doc_types}", None

    document_hash = best_doc.get("href")
    if not document_hash:
        return "no_file_url", best_doc.get("type")

    file_url = f"https://planningapi.agileapplications.ie/api/application/document/{document_hash}"
    file_path = output_dir / filename
    if not download_binary_file(file_url, file_path, timeout=90, headers=headers):
        if try_save_reasons_fallback():
            return "success_reasons", "API refusal reasons"
        return "no_file_url", best_doc.get("type")

    return "success", best_doc.get("type")


async def download_decision_v3(
    app_url: str,
    output_dir: Path,
    filename: str,
    council_name: str = "",
    app_num: str = "",
) -> tuple:
    """
    Download decision document - handles all council variations.
    Returns (status, doc_type_found).
    """
    if "planning.agileapplications.ie" in app_url:
        return await download_from_agile(app_url, output_dir, filename, app_ref=app_num)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True, ignore_https_errors=True)
        page = await context.new_page()
        
        try:
            last_goto_err = None
            for _ in range(3):
                try:
                    await page.goto(app_url, wait_until="domcontentloaded", timeout=30000)
                    last_goto_err = None
                    break
                except Exception as exc:
                    last_goto_err = exc
                    await asyncio.sleep(1.5)
            if last_goto_err:
                raise last_goto_err
            
            scanned_files_button = page.locator('input[value="View Scanned Files"]')
            popup_url = None

            if await scanned_files_button.count() > 0:
                onclick_attr = await scanned_files_button.get_attribute("onclick")
                match = re.search(r"popupEnquirySubWindow\('([^']+)'", onclick_attr or "")
                if match:
                    popup_url = match.group(1).replace(" ", "")
            else:
                # Some councils expose the document URL directly in page scripts.
                content = await page.content()
                direct_match = re.search(
                    r"(https?://[^\"']*(?:ViewExternalDocuments|listFiles\.aspx|copyright\.aspx)[^\"']*)",
                    content,
                    flags=re.IGNORECASE,
                )
                if direct_match:
                    popup_url = direct_match.group(1).replace(" ", "")

            if not popup_url:
                await browser.close()
                return "no_popup_url", None

            popup_url = html.unescape(popup_url)
            if not popup_url.startswith(("http://", "https://")):
                popup_url = urljoin(page.url, popup_url)

            base_url_match = re.search(r"(https?://[^/]+)", popup_url)
            if not base_url_match:
                await browser.close()
                return "no_base_url", None
            
            base_url = base_url_match.group(1)
            
            # Check which system this council uses
            if "donegalcoco.ie" in base_url:
                # Donegal uses a different system - use Playwright
                result = await download_from_donegal(page, popup_url, output_dir, filename)
                await browser.close()
                return result
            
            # Standard iDocs system
            result, doc_type = await download_from_idocs(
                page, popup_url, base_url, output_dir, filename, council_name, app_num=app_num
            )
            
            await browser.close()
            return result, doc_type
            
        except Exception as e:
            await browser.close()
            msg = str(e).lower()
            if "timeout" in msg:
                return "timeout", None
            return f"error: {str(e)[:80]}", None


async def main():
    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"CSV not found: {CSV_PATH}\n"
            "Put 'greater_than_10_units_with_flooding.csv' in the same folder as this script "
            "or change CSV_PATH at the top."
        )

    df = pd.read_csv(CSV_PATH, dtype=str)

    refused_terms = [
        "REFUSED",
        "REFUSE PERMISSION",
        "Refused",
        "REFUSE OUTLINE PERMISSION",
        "REFUSE EXT. OF DURATION OF PERMISSION",
        "REFUSE APPROVAL",
        "REFUSE PERMISSION & REFUSE RETENTION",
        "REFUSE PERMISSION & REFUSE OUTLINE PERM.",
        "REFUSE RETENTION PERMISSI",
    ]

    decision_series = df["Decision"].fillna("").astype(str).str.upper()
    rejected_df = df[decision_series.isin(refused_terms) | decision_series.str.contains("REFUSE", regex=False)]
    agile_councils = {
        "dublin city council",
        "fingal county council",
        "south dublin county council",
        "dun laoghaire rathdown county council",
    }
    link_series = rejected_df["LinkAppDetails"].fillna("").astype(str).str.strip()
    agile_council_mask = rejected_df["PlanningAuthority"].fillna("").astype(str).str.lower().isin(agile_councils)
    rejected_with_links = rejected_df[link_series.ne("") | agile_council_mask].copy()

    downloaded_files = {p.name for p in OUTPUT_DIR.iterdir() if p.is_file()}

    pending = []
    for _, row in rejected_with_links.iterrows():
        council = str(row["PlanningAuthority"])
        app_num = str(row["ApplicationNumber"])

        filename = f"{safe_filename(council)}_{safe_filename(app_num)}_Decision.pdf"
        fallback_name = reason_filename_from_pdf(filename)
        djvu_name = djvu_filename_from_pdf(filename)
        base_name = Path(filename).stem
        alt_names = {
            filename,
            fallback_name,
            djvu_name,
            f"{base_name}.doc",
            f"{base_name}.docx",
        }
        # Backward compatibility: older runs coerced numeric app numbers and dropped leading zeros.
        app_digits = "".join(ch for ch in app_num if ch.isdigit())
        if app_digits and app_num.startswith("0"):
            legacy_app = str(int(app_digits))
            legacy_filename = f"{safe_filename(council)}_{safe_filename(legacy_app)}_Decision.pdf"
            legacy_base = Path(legacy_filename).stem
            alt_names.update(
                {
                    legacy_filename,
                    reason_filename_from_pdf(legacy_filename),
                    djvu_filename_from_pdf(legacy_filename),
                    f"{legacy_base}.doc",
                    f"{legacy_base}.docx",
                }
            )

        if not any(name in downloaded_files for name in alt_names):
            pending.append(
                {
                    "council": council,
                    "app_num": app_num,
                    "url": normalize_app_details_url(council, app_num, str(row["LinkAppDetails"])),
                    "filename": filename,
                }
            )

    print(f"Output folder: {OUTPUT_DIR}")
    print(f"Log file:      {LOG_FILE}")
    print(f"Already downloaded: {len(downloaded_files)}")
    print(f"Pending:            {len(pending)}")
    print("\nStarting batch processing...\n")

    results = {
        "success": 0,
        "success_reasons": 0,
        "success_djvu": 0,
        "success_djvu_pdf": 0,
        "no_button": 0,
        "bad_agile_url": 0,
        "no_agile_client": 0,
        "no_popup_url": 0,
        "no_base_url": 0,
        "no_documents": 0,
        "no_match": 0,
        "no_link": 0,
        "no_file_url": 0,
        "no_iframe": 0,
        "timeout": 0,
        "error": 0,
    }

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("Download Log\n")
        f.write("=" * 60 + "\n\n")

    for i, item in enumerate(pending):
        council = item["council"]
        app_num = item["app_num"]
        url = item["url"]
        filename = item["filename"]

        print(f"[{i+1}/{len(pending)}] {council} - {app_num}...", end=" ", flush=True)

        try:
            result, doc_type = await asyncio.wait_for(
                download_decision_v3(url, OUTPUT_DIR, filename, council, app_num),
                timeout=140,
            )
            
            status = result.split(":")[0] if ":" in result else result
            results[status] = results.get(status, 0) + 1
            
            if result == "success":
                print(f"success ({doc_type})")
            else:
                print(result)

        except asyncio.TimeoutError:
            results["timeout"] += 1
            result = "timeout"
            doc_type = None
            print("timeout")

        except Exception as e:
            results["error"] += 1
            result = "error"
            doc_type = None
            print(f"error: {str(e)[:80]}")

        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{council} - {app_num}: {result}")
            if doc_type:
                f.write(f" [{doc_type}]")
            f.write(f" ({filename})\n")

        await asyncio.sleep(0.5)

        if (i + 1) % 10 == 0:
            print(f"\n--- Progress: {i+1}/{len(pending)} ---")
            print(
                f"Success: {results['success']}, "
                f"No match: {results['no_match']}, "
                f"Timeout: {results['timeout']}, "
                f"Error: {results['error']}\n"
            )

    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    for key, value in results.items():
        if value > 0:
            print(f"{key}: {value}")

    total_success_like = (
        results.get("success", 0)
        + results.get("success_reasons", 0)
        + results.get("success_djvu", 0)
        + results.get("success_djvu_pdf", 0)
    )
    print(f"\nTotal successful downloads: {total_success_like}")
    print(f"Total files in output folder: {len([p for p in OUTPUT_DIR.iterdir() if p.is_file()])}")

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write("\n" + "=" * 60 + "\n")
        f.write("FINAL SUMMARY\n")
        f.write("=" * 60 + "\n")
        for key, value in results.items():
            f.write(f"{key}: {value}\n")


if __name__ == "__main__":
    asyncio.run(main())
