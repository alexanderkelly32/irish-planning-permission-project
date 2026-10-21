"""Authority document connector interface (brief sections 7.2, 11).

Connectors sit behind one interface: list documents for an application,
fetch a document into content-addressed storage, extract native text with OCR
fallback. The pilot connects 2-4 authorities only; no national scrape. This
module ships the interface plus a local-file connector used by tests and a
registry of connector metadata (terms, rate limits, permitted reuse).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .. import settings
from ..provenance import sha256_file


class DocumentRecord(Protocol):
    application_reference: str
    document_type: str
    source_url: str
    file_hash: str
    retrieval_date: str
    access_outcome: str


class AuthorityConnector(Protocol):
    name: str

    def list_documents(self, application_reference: str) -> list[dict[str, Any]]: ...

    def fetch_document(self, application_reference: str, document_id: str) -> Path: ...

    def extract_text(self, document_path: Path) -> dict[str, Any]: ...


class LocalFileConnector:
    """Filesystem connector for tests and manual research collections."""

    name = "local"

    def __init__(self, root: Path):
        self.root = Path(root)

    def list_documents(self, application_reference: str) -> list[dict[str, Any]]:
        app_dir = self.root / application_reference
        if not app_dir.exists():
            return []
        return [
            {
                "application_reference": application_reference,
                "document_id": str(path.name),
                "document_type": path.suffix.lstrip("."),
                "source_url": str(path),
                "file_hash": sha256_file(path),
                "retrieval_date": "",
                "access_outcome": "available",
            }
            for path in sorted(app_dir.iterdir()) if path.is_file()
        ]

    def fetch_document(self, application_reference: str, document_id: str) -> Path:
        path = self.root / application_reference / document_id
        if not path.exists():
            raise FileNotFoundError(path)
        return path

    def extract_text(self, document_path: Path) -> dict[str, Any]:
        path = Path(document_path)
        if path.suffix.lower() in {".txt", ".md"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            return {"native_text": text, "ocr_pages": [], "quality": "native"}
        return {"native_text": "", "ocr_pages": [], "quality": "unsupported_type"}


CONNECTOR_REGISTRY: dict[str, dict[str, Any]] = {
    "local": {"class": LocalFileConnector, "notes": "tests and manual collections only"},
    # Authority connectors join here after per-portal terms/rate-limit review
    # (brief 8.4). Existing repo tooling (02_development/scripts/
    # planner_report_downloader.py, 04_fi/scripts/pull_fi_documents.py) is the
    # integration starting point for eplanning-based authorities.
}


def content_addressed_store(document_path: Path, store_root: Path) -> Path:
    """Copy a fetched document into sha256/ab/cd/<hash>.<ext> storage."""
    import shutil

    digest = sha256_file(document_path)
    target = store_root / "sha256" / digest[:2] / digest[2:4] / f"{digest}.{document_path.suffix.lstrip('.')}"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(document_path, target)
    return target
