"""Runner: download the actual TIC LIST documents and parse estate entries.

Scans saved TIC HTML pages for document links whose names suggest a list
(taken-in-charge / estates / TIC), downloads them (resumable), extracts text
(PDF via fitz, XLSX via pandas), parses estate-name entries and matches to
cohort schemes.
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".vendor"))

import pandas as pd  # noqa: E402
import requests  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.entity_resolution.scoring import address_tokens  # noqa: E402

PAGES_DIR = settings.SILVER_DIR / "tic_pages"
LISTS_DIR = settings.SILVER_DIR / "tic_lists"
STATE_PATH = LISTS_DIR / "state.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) planning-risk-review/1.0 (local research)"}

LIST_NAME_RE = re.compile(r"(taken|take).{0,12}charge|estates.{0,20}(taken|charge)|TIC", re.IGNORECASE)


def find_list_links(html: str, base: str) -> list[str]:
    hrefs = re.findall(r'href="([^"]+)"', html, re.IGNORECASE)
    out = []
    for href in hrefs:
        if re.search(r"\.(pdf|xlsx?|docx?|csv)", href, re.IGNORECASE) and LIST_NAME_RE.search(href):
            out.append(urljoin(base, href.replace("&amp;", "&")))
    return out


def extract_document_text(content: bytes, suffix: str) -> str:
    import fitz

    if suffix == ".pdf":
        document = fitz.open(stream=content, filetype="pdf")
        text = "\n".join(page.get_text() for page in document)
        document.close()
        return text
    if suffix in (".xlsx", ".xls"):
        frame = pd.read_excel(io.BytesIO(content), header=None)
        return "\n".join(" | ".join(str(v) for v in row if pd.notna(v)) for _, row in frame.iterrows())
    if suffix in (".docx",):
        text = content.decode("utf-8", errors="replace")
        return re.sub(r"<[^>]+>", " ", text)
    return content.decode("utf-8", errors="replace")


def parse_entries(text: str, authority: str) -> list[dict]:
    entries = []
    for line in re.split(r"[\n;•|]", text):
        line = line.strip()
        if not (6 < len(line) < 160):
            continue
        if re.search(r"^\s*([A-Z][A-Za-z'&.()\- ]{3,60})\s*(?:estate|park|manor|heights|wood|groves|drive|lawn|crescent|close|view|lodge|gardens|walk|court|avenue|green|fields|grange|abbey|hill|vale|rise|dene|glen)\b", line, re.IGNORECASE):
            match = re.search(r"^\s*([A-Z][A-Za-z'&.()\- ]{3,60})", line)
            if match:
                entries.append({"authority": authority, "estate_name": match.group(1).strip().strip(",-. "), "raw_line": line[:160]})
    return entries


if __name__ == "__main__":
    LISTS_DIR.mkdir(parents=True, exist_ok=True)
    state = {"done": {}, "failed": {}}
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

    html_files = {p.stem.replace("_tic", ""): p for p in PAGES_DIR.glob("*_tic.html")}
    base_urls = {
        "clare": "https://www.clarecoco.ie/ga/node/416",
        "galway_county": "https://www.galway.ie/en/planning-building/development-management/taking-charge-completed-residential-developments",
        "kildare": "https://kildarecoco.ie/AllServices/BuildingandDevelopmentControl/DevelopmentControl/ListofEstatesTakeninCharge/",
        "monaghan": "https://monaghan.ie/planning/taking-in-charge/",
        "waterford": "https://waterfordcouncil.ie/services/planning/estate-management/taking-in-charge/",
        "wexford": "https://www.wexfordcoco.ie/planning/building-control/taking-in-charge/list-of-taken-in-charge-estates",
        "westmeath": "https://www.westmeathcoco.ie/en/ourservices/planning/takingincharge/",
        "dublin_city": "https://www.dublincity.ie/planning-and-land-use/development-contributions-and-security-bonds/bonds-and-taking-charge",
        "fingal": "https://www.fingal.ie/housing-fingal/taking-charge-information",
        "louth": "https://www.louthcoco.ie/services/planning/taking-in-charge/",
        "limerick": "https://www.limerick.ie/council/services/planning-and-placemaking/taking-in-charge-of-housing-estates/taking-in-charge",
        "leitrim": "https://www.leitrim.ie/council/services/planning-building/unfinished-estates-taking-in-charge/",
    }

    records = []
    for authority, html_path in html_files.items():
        html = html_path.read_text(encoding="utf-8", errors="ignore")
        for url in find_list_links(html, base_urls.get(authority, "")):
            key = f"{authority}__{url[-80:]}"
            if key in state["done"] or key in state["failed"]:
                continue
            try:
                response = requests.get(url, timeout=90, headers=HEADERS)
                suffix = Path(url.split("?")[0]).suffix.lower()
                text = extract_document_text(response.content, suffix)
                (LISTS_DIR / f"{authority}_{len(state['done'])}{suffix}").write_bytes(response.content)
                text_path = LISTS_DIR / f"{authority}_{len(state['done'])}.txt"
                text_path.write_text(text, encoding="utf-8", errors="ignore")
                state["done"][key] = {"chars": len(text), "url": url}
                records.extend(parse_entries(text, authority))
            except Exception as error:  # noqa: BLE001
                state["failed"][key] = f"{type(error).__name__}: {str(error)[:120]}"
            STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
            time.sleep(1.0)

    entries = pd.DataFrame(records).drop_duplicates(subset=["authority", "estate_name"])
    entries.to_csv(LISTS_DIR / "tic_list_entries.csv", index=False)

    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    mature = cohort[cohort["grant_year"].between(2016, 2022)].copy()
    mature["addr_tokens"] = mature["DevelopmentAddress"].fillna("").map(address_tokens)
    matches = []
    for _, entry in entries.iterrows():
        tokens = address_tokens(entry["estate_name"])
        if not tokens:
            continue
        for _, scheme in mature.iterrows():
            overlap = tokens & set(scheme["addr_tokens"])
            if len(overlap) >= max(1, min(2, len(tokens))):
                matches.append({
                    "scheme_id": str(scheme["case_key"]),
                    "authority": entry["authority"],
                    "tic_estate_name": entry["estate_name"],
                    "scheme_address": str(scheme["DevelopmentAddress"])[:80],
                    "token_overlap": len(overlap),
                })
    matched = pd.DataFrame(matches).drop_duplicates(subset=["scheme_id", "tic_estate_name"])
    matched.to_csv(settings.SILVER_DIR / "scheme_tic_matches.csv", index=False)

    summary = {
        "list_docs_downloaded": int(len(state["done"])),
        "failed_docs": int(len(state["failed"])),
        "entries_parsed": int(len(entries)),
        "matched_schemes": int(matched["scheme_id"].nunique()) if len(matched) else 0,
        "note": "candidate matches only; verify before using as labels",
    }
    (LISTS_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
