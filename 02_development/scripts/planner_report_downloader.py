"""Phase B: planner-report downloader for ePlan/iDocs councils."""
from __future__ import annotations

import html as html_lib
import re
import time
from pathlib import Path
from typing import Any

import pandas as pd

IDOCS_URL_PATTERN = re.compile(
    r"popupEnquirySubWindow\('([^']*iDocs[^']*)'",
    re.IGNORECASE,
)
VIEWSTATE_PATTERN = re.compile(r'name="__VIEWSTATE"[^>]*value="([^"]*)"', re.IGNORECASE)
EVENTVALIDATION_PATTERN = re.compile(r'name="__EVENTVALIDATION"[^>]*value="([^"]*)"', re.IGNORECASE)
VIEWSTATEGENERATOR_PATTERN = re.compile(r'name="__VIEWSTATEGENERATOR"[^>]*value="([^"]*)"', re.IGNORECASE)
DOCUMENT_LINK_PATTERN = re.compile(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)

PLANNER_REPORT_TITLES = re.compile(
    r"\b(planners?\s+report|planner(?:'s)?\s+report|planning\s+report|officer(?:'s)?\s+report|"
    r"chief\s+executive(?:'s)?\s+report|manager(?:'s)?\s+report|case\s+officer\s+report)\b",
    re.IGNORECASE,
)
REPORT_NEGATIVE_TITLES = re.compile(
    r"\b(fi\s+report|engineer(?:'s)?\s+report|traffic|noise|landscape|arboricultur|archaeolog|flood)\b",
    re.IGNORECASE,
)


def extract_idocs_url(details_html: str) -> str | None:
    match = IDOCS_URL_PATTERN.search(details_html)
    if not match:
        return None
    return html_lib.unescape(match.group(1)).replace("&amp;", "&").strip()


def parse_copyright_page(page_html: str) -> dict[str, str]:
    def value(pattern: re.Pattern) -> str:
        match = pattern.search(page_html)
        return html_lib.unescape(match.group(1)) if match else ""

    return {
        "__VIEWSTATE": value(VIEWSTATE_PATTERN),
        "__EVENTVALIDATION": value(EVENTVALIDATION_PATTERN),
        "__VIEWSTATEGENERATOR": value(VIEWSTATEGENERATOR_PATTERN),
    }


def build_agree_payload(state: dict[str, str]) -> dict[str, str]:
    return {
        "__EVENTTARGET": "chkAgree",
        "__EVENTARGUMENT": "",
        "__LASTFOCUS": "",
        "__VIEWSTATE": state.get("__VIEWSTATE", ""),
        "__VIEWSTATEGENERATOR": state.get("__VIEWSTATEGENERATOR", ""),
        "__EVENTVALIDATION": state.get("__EVENTVALIDATION", ""),
        "chkAgree": "on",
    }


DOCUMENT_ROW_PATTERN = re.compile(
    r"<tr[^>]*>(.*?)</tr>",
    re.IGNORECASE | re.DOTALL,
)
DOCUMENT_CELL_PATTERN = re.compile(r"<td[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
VIEW_FILES_PATTERN = re.compile(
    r"ViewFiles\.aspx\?docid=(\d+)&format=([a-z]+)",
    re.IGNORECASE,
)


def parse_document_rows(document_page_html: str) -> list[dict[str, str]]:
    documents: list[dict[str, str]] = []
    for row_html in DOCUMENT_ROW_PATTERN.findall(document_page_html):
        view_match = VIEW_FILES_PATTERN.search(row_html)
        if not view_match:
            continue
        cells = [
            html_lib.unescape(re.sub(r"<[^>]+>", "", cell)).strip()
            for cell in DOCUMENT_CELL_PATTERN.findall(row_html)
        ]
        cell_text = [re.sub(r"\s+", " ", cell).strip() for cell in cells]
        documents.append({
            "type": cell_text[0] if len(cell_text) > 0 else "",
            "comment": cell_text[1] if len(cell_text) > 1 else "",
            "files": cell_text[2] if len(cell_text) > 2 else "",
            "size": cell_text[3] if len(cell_text) > 3 else "",
            "docid": view_match.group(1),
            "format": view_match.group(2),
        })
    return documents


def classify_planner_report(title: str) -> bool:
    if not PLANNER_REPORT_TITLES.search(title):
        return False
    if REPORT_NEGATIVE_TITLES.search(title):
        return False
    return True


def application_ref_from_url(url: str) -> str | None:
    match = re.search(r"AppFileRefDetails/([^/]+)", url)
    return match.group(1) if match else None


def build_cohort(cases: pd.DataFrame, council: str, limit: int, seed: int = 20260905, refusals_only: bool = False, received_year_min: int | None = None, received_year_max: int | None = None) -> pd.DataFrame:
    frame = cases[cases["PlanningAuthority"].astype(str) == council].copy()
    if received_year_min is not None or received_year_max is not None:
        if "ReceivedDate" in frame.columns:
            years = pd.to_datetime(frame["ReceivedDate"], errors="coerce").dt.year
            if received_year_min is not None:
                frame = frame[years >= received_year_min]
            if received_year_max is not None:
                frame = frame[years <= received_year_max]
    if refusals_only and "Decision" in frame.columns:
        frame = frame[frame["Decision"].fillna("").astype(str).str.upper().str.contains("REFUS")]
    urls = frame["fi_resolved_url"].fillna(frame.get("LinkAppDetails", "")).astype(str)
    frame["_ref"] = urls.map(application_ref_from_url)
    frame = frame[frame["_ref"].notna()].copy()
    frame["_order"] = [hash(f"{seed}|{ref}") for ref in frame["_ref"]]
    return frame.sort_values("_order").head(limit)


def build_view_files_payload(state: dict[str, str]) -> dict[str, str]:
    return {
        "__EVENTTARGET": "",
        "__EVENTARGUMENT": "",
        "__LASTFOCUS": "",
        "__VIEWSTATE": state.get("__VIEWSTATE", ""),
        "__VIEWSTATEGENERATOR": state.get("__VIEWSTATEGENERATOR", ""),
        "__EVENTVALIDATION": state.get("__EVENTVALIDATION", ""),
        "chkAgree": "on",
        "btnViewFiles": "View Files",
    }


VIEW_PDF_PATTERN = re.compile(r"ViewPdf\.aspx\?[^\"'\s]+?\.pdf", re.IGNORECASE)
FILES_PDF_PATTERN = re.compile(r"(?:src|href)=\"[^\"]*?(?:files[/\\][^\"#]+?\.pdf)", re.IGNORECASE)


def find_pdf_url(view_files_html: str) -> str | None:
    match = VIEW_PDF_PATTERN.search(view_files_html)
    if not match:
        return None
    return html_lib.unescape(match.group(0)).replace("&amp;", "&")


def find_files_pdf(view_pdf_html: str) -> str | None:
    match = FILES_PDF_PATTERN.search(view_pdf_html)
    if not match:
        return None
    start = match.group(0).find("files")
    value = match.group(0)[start:]
    return html_lib.unescape(value).replace("\\", "/")


class PlannerReportClient:
    """Polite client for the ePlan -> iDocs planner-report flow."""

    def __init__(self, session=None, delay_seconds: float = 1.0, user_agent: str | None = None):
        import requests

        self.session = session or requests.Session()
        self.delay = delay_seconds
        self.session.headers.update({
            "User-Agent": user_agent or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            ),
        })

    def _get(self, url: str) -> str:
        response = self.session.get(url, timeout=60)
        response.raise_for_status()
        time.sleep(self.delay)
        return response.text

    def _post(self, url: str, payload: dict[str, str]) -> str:
        response = self.session.post(url, data=payload, timeout=60)
        response.raise_for_status()
        time.sleep(self.delay)
        return response.text

    def fetch_document_list(self, details_html: str, idocs_url: str | None = None) -> list[dict[str, str]]:
        target = idocs_url or extract_idocs_url(details_html)
        if not target:
            return []
        target = re.sub(r"^http://", "https://", target, flags=re.IGNORECASE)
        copyright_html = self._get(target)
        if "listFiles.aspx" in target or "DocumentsDG" in copyright_html:
            rows = parse_document_rows(copyright_html)
            base = target[: target.rfind("/") + 1]
            for row in rows:
                row["url"] = f"{base}ViewFiles.aspx?docid={row['docid']}&format={row['format']}"
                row["pdf_url"] = f"{base}ViewFiles.aspx?docid={row['docid']}&format=pdf"
            return rows
        state = parse_copyright_page(copyright_html)
        agreed_html = self._post(target, build_agree_payload(state))
        if 'name="btnViewFiles"' not in agreed_html:
            return []
        agreed_state = parse_copyright_page(agreed_html)
        document_html = self._post(target, build_view_files_payload(agreed_state))
        rows = parse_document_rows(document_html)
        base = target[: target.rfind("/") + 1]
        for row in rows:
            row["url"] = f"{base}ViewFiles.aspx?docid={row['docid']}&format={row['format']}"
            row["pdf_url"] = f"{base}ViewFiles.aspx?docid={row['docid']}&format=pdf"
        return rows

    def download(self, url: str, output_path: Path) -> bool:
        """Follow the ViewFiles -> ViewPdf -> files/ hops to the actual PDF and save it."""
        base = url[: url.rfind("/") + 1]
        viewer_html = self.session.get(url, timeout=120).text
        pdf_url = find_pdf_url(viewer_html)
        if not pdf_url:
            return False
        view_pdf = self.session.get(base + pdf_url, timeout=180)
        content = view_pdf.content
        if content.startswith(b"%PDF"):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(content)
            time.sleep(self.delay)
            return True
        files_pdf = find_files_pdf(view_pdf.text)
        if not files_pdf:
            return False
        final_url = base[: base.rstrip("/").rfind("/") + 1] if files_pdf.startswith("files/") else base
        response = self.session.get(base.rstrip("/") + "/" + files_pdf.lstrip("./\\"), timeout=180)
        if response.status_code != 200 or not response.content.startswith(b"%PDF"):
            return False
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)
        time.sleep(self.delay)
        return True
