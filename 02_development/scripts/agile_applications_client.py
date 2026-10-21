"""Playwright-based document client for agileapplications citizen portals.

The portal is a JavaScript SPA: document data loads through
planningapi.agileapplications.ie with X-Client/X-Service/X-Product headers the
app sets internally, so plain requests are rejected. This client drives a
headless browser, captures the document-list API response, classifies document
types, and downloads files through the authenticated browser context.

Interface mirrors PlannerReportClient: fetch_document_list(url) -> list[dict],
download(pdf_url, output) -> bool.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DETAILS_URL_PATTERN = re.compile(r"agileapplications\.ie/[^/]+/application-details/(\d+)")
DOCUMENT_LIST_PATTERN = re.compile(r"planningapi\.agileapplications\.ie/api/application/\d+/document$")
DOWNLOAD_PATTERN = re.compile(r"planningapi\.agileapplications\.ie/api/(?:application/\d+/)?(?:document|file)[^\s\"']*")


def application_id_from_url(url: str) -> str | None:
    match = DETAILS_URL_PATTERN.search(url)
    return match.group(1) if match else None


def client_code_from_url(url: str) -> str | None:
    match = re.search(r"agileapplications\.ie/([^/]+)/", url)
    if not match:
        return None
    return match.group(1).upper()


def classify_document(doc: dict) -> str | None:
    """Map agile document metadata to a type label; None when unclassifiable.

    The portal's own type lives in ``mediaDescription`` (e.g. 'Decision',
    'Planners Report', 'Report Received from External Body').
    """
    media = str(doc.get("mediaDescription") or doc.get("description") or "").lower()
    name = str(doc.get("name") or doc.get("documentName") or "").lower()
    combined = f"{media} {name}"
    if re.search(r"decision", combined):
        return "Decision Notice"
    if re.search(r"planner'?s? report|officer'?s? report", combined):
        return "Planners Report"
    if re.search(r"report", combined):
        return "Report"
    if re.search(r"drawing|site layout|elevation|floor plan", combined):
        return "Drawing"
    return None


class AgileApplicationsClient:
    def __init__(self, headless: bool = True, timeout_ms: int = 90000) -> None:
        self.headless = headless
        self.timeout_ms = timeout_ms
        self._last_documents: list[dict] = []
        self._last_downloads: dict[str, str] = {}

    def fetch_document_list(self, url: str) -> list[dict]:
        from playwright.sync_api import sync_playwright

        self._last_documents = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context()
            page = context.new_page()
            captured: dict = {}

            def on_response(response):
                if DOCUMENT_LIST_PATTERN.search(response.url):
                    try:
                        payload = response.json()
                        if isinstance(payload, list):
                            captured["documents"] = payload
                    except Exception:
                        pass

            page.on("response", on_response)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                page.wait_for_timeout(18000)
            finally:
                browser.close()

        documents = captured.get("documents", [])
        classified = []
        for entry in documents:
            doc_type = classify_document(entry)
            if doc_type is None:
                continue
            classified.append({
                "type": doc_type,
                "name": str(entry.get("name") or entry.get("documentName") or ""),
                "docid": str(entry.get("documentId") or entry.get("id") or ""),
                "documentHash": str(entry.get("documentHash") or ""),
                "url": url,
            })
        self._last_documents = classified
        return classified

    def download(self, details_url: str, document_hash: str, output: Path) -> bool:
        """Download one document by hash through the authenticated page context.

        The API requires the X-Client/X-Service/X-Product headers that the SPA
        attaches from sessionStorage, so the fetch runs inside the page.
        """
        import base64

        from playwright.sync_api import sync_playwright

        output.parent.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            page = browser.new_page()
            try:
                page.goto(details_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                page.wait_for_timeout(12000)
                result = page.evaluate(
                    """async (hash) => {
                        const client = sessionStorage.getItem('sas-auth-client') || '';
                        const service = sessionStorage.getItem('sas-auth-service') || '';
                        const product = sessionStorage.getItem('sas-auth-product') || '';
                        const api = (sessionStorage.getItem('planning-api-url') || 'https://planningapi.agileapplications.ie').replace(/\\/$/, '');
                        const response = await fetch(api + '/api/application/document/' + hash, {
                            headers: {'X-Client': client, 'X-Service': service, 'X-Product': product,
                                      'Accept': 'application/json, text/plain, */*'},
                            credentials: 'include',
                        });
                        if (!response.ok) return null;
                        const buffer = await response.arrayBuffer();
                        const bytes = new Uint8Array(buffer);
                        let binary = '';
                        const chunk = 0x8000;
                        for (let i = 0; i < bytes.length; i += chunk) {
                            binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
                        }
                        return btoa(binary);
                    }""",
                    document_hash,
                )
            finally:
                browser.close()
        if not result:
            return False
        output.write_bytes(base64.b64decode(result))
        return output.exists() and output.stat().st_size > 0
