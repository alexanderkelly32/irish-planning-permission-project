#!/usr/bin/env python3
"""Scrape the 31 councils' current development-plan PDFs from the index.

Parses irish_planning_development_plan_index.md, fetches each authority's
current plan portal, collects PDF links that look like written statements or
adopted-plan volumes, and downloads them (resume-safe). Councils whose portals
need JavaScript or expose no direct PDF links are logged as MANUAL.

Outputs: 05_policy/current/council_plan_corpus_manifest.csv + download log.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "02_development" / "current" / "irish_planning_development_plan_index.md"
DOWNLOAD_ROOT = ROOT / "05_policy" / "documents" / "downloaded"
OUT_DIR = ROOT / "05_policy" / "current" / "council_plan_corpus_2026-09-20"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}

PDF_NAME_HINTS = re.compile(
    r"(written\s*statement|volume\s*1|adopted\s*plan|development\s*plan|county\s*plan|city\s*plan)",
    re.IGNORECASE,
)
PDF_HREF = re.compile(r'href=["\']([^"\']+\.pdf[^"\']*)["\']', re.IGNORECASE)


def parse_index() -> list[dict]:
    text = INDEX.read_text(encoding="utf-8")
    rows = []
    for line in text.splitlines():
        if not line.startswith("| **") or " —" not in line:
            continue
        cell = line[2:-2]
        parts = cell.split("|")
        if len(parts) < 2:
            continue
        authority = parts[0].strip().strip("**").replace("**", "").strip()
        portal_match = re.search(r"\[([^\]]+)\]\((https?://[^)]+)\)", parts[1])
        if not portal_match:
            continue
        portal_url = portal_match.group(2)
        rows.append({"authority": authority, "portal_url": portal_url})
    return rows


def slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = OUT_DIR / "download_log.jsonl"
    done = set()
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip():
                try:
                    item = json.loads(line)
                    if item.get("status") in {"ok", "no_pdfs", "manual"}:
                        done.add(item.get("authority", ""))
                except json.JSONDecodeError:
                    continue

    manifest = []
    for entry in parse_index():
        authority = entry["authority"]
        if authority in done:
            continue
        record = {"authority": authority, "portal_url": entry["portal_url"], "status": "", "pdfs": [], "note": ""}
        try:
            response = requests.get(entry["portal_url"], headers=HEADERS, timeout=45)
            html = response.text
            pdfs = []
            for href in PDF_HREF.findall(html):
                absolute = urljoin(entry["portal_url"], href)
                name = absolute.split("/")[-1].split("?")[0]
                if PDF_NAME_HINTS.search(name):
                    pdfs.append(absolute)
            pdfs = list(dict.fromkeys(pdfs))[:12]
            if not pdfs:
                record["status"] = "no_pdfs"
                record["note"] = "portal had no matching direct PDF links (JS portal or index page)"
            else:
                council_dir = DOWNLOAD_ROOT / slug(authority)
                council_dir.mkdir(parents=True, exist_ok=True)
                for pdf_url in pdfs:
                    name = pdf_url.split("/")[-1].split("?")[0]
                    target = council_dir / name
                    try:
                        content = requests.get(pdf_url, headers=HEADERS, timeout=120).content
                        if len(content) > 200_000:
                            target.write_bytes(content)
                            record["pdfs"].append(str(target))
                    except Exception as exc:
                        record["note"] += f"{name}: {str(exc)[:60]}; "
                record["status"] = "ok"
        except Exception as exc:
            record["status"] = "manual"
            record["note"] = str(exc)[:160]
        with log_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
        manifest.append(record)
        print(json.dumps({"authority": authority, "status": record["status"], "pdfs": len(record["pdfs"])}), flush=True)
        time.sleep(1.0)

    pd = __import__("pandas")
    pd.DataFrame(manifest).to_csv(OUT_DIR / "council_plan_corpus_manifest.csv", index=False)
    print(json.dumps({"processed": len(manifest)}, indent=2))


if __name__ == "__main__":
    main()
