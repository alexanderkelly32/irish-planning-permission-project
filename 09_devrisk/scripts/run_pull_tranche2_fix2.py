"""Runner: endpoint fixes for the four blocked tranche-2 sources."""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
report: dict = {}


def get(url: str, timeout: int = 60, referer: str = "") -> bytes:
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def post_json(url: str, payload: dict, timeout: int = 90) -> bytes:
    request = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json", "User-Agent": UA},
                                     method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


# ---- 1. BER Fingal: page HTML -> itemId -> download API v1 ----
try:
    page = get("https://data.fingal.ie/datasets/FingalCoCo::ber-ratings-building-certs-2020-2024-fcc",
               timeout=90, referer="https://data.fingal.ie/").decode("utf-8", errors="ignore")
    ids = re.findall(r'"(itemId|id)":\s*"([a-f0-9]{32})"', page)
    item_ids = sorted(set(i for _, i in ids))
    report["ber_page"] = {"len": len(page), "item_ids": item_ids[:3]}
    if item_ids:
        item_id = item_ids[0]
        for url in (
            f"https://data.fingal.ie/api/download/v1/items/{item_id}/csv?layers=0",
            f"https://www.arcgis.com/sharing/rest/content/items/{item_id}/data",
        ):
            try:
                content = get(url, timeout=600, referer="https://data.fingal.ie/")
                if len(content) > 10_000:
                    out_dir = settings.RAW_DIR / "ber_fingal"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    (out_dir / "ber_2020_2024.csv").write_bytes(content)
                    report["ber_download"] = {"url": url, "bytes": len(content)}
                    break
                report.setdefault("ber_tried", []).append({"url": url[:80], "bytes": len(content)})
            except Exception as exc:
                report.setdefault("ber_errors", []).append({"url": url[:80], "error": str(exc)})
except Exception as exc:
    report["ber_page_error"] = str(exc)

# ---- 2. TED API: corrected query syntax ----
variants = [
    {"query": "CPV=45000000 AND place-of-performance=IE",
     "fields": ["publication-number", "publication-date", "title", "buyer-name", "place-of-performance", "cpv-codes", "notice-type"],
     "page": 1, "limit": 100},
    {"query": "CPV=45000000 AND buyer-country=IE",
     "fields": ["publication-number", "publication-date", "title"],
     "page": 1, "limit": 100},
    {"query": "CPV=45210000",
     "fields": ["publication-number", "publication-date", "title"],
     "page": 1, "limit": 100},
]
ted_rows = []
for i, variant in enumerate(variants):
    try:
        data = json.loads(post_json("https://api.ted.europa.eu/v3/notices/search", variant))
        notices = data.get("notices") or data.get("results") or []
        report[f"ted_variant_{i}"] = {"rows": len(notices), "meta": {k: str(v)[:40] for k, v in list(data.items())[:4]}}
        ted_rows.extend(notices)
        if notices:
            break
    except Exception as exc:
        report[f"ted_variant_{i}_error"] = str(exc)
if ted_rows:
    out = settings.RAW_DIR / "ted" / "ted_construction_ie.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for row in ted_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    report["ted_saved"] = len(ted_rows)

# ---- 3. gov.ie: publications search page (server-rendered) ----
try:
    html = get("https://www.gov.ie/en/publications/?q=social+housing+construction+status+report",
               timeout=90).decode("utf-8", errors="ignore")
    links = sorted(set(re.findall(r'href="(/en/publication/[^"]+)"', html)))
    report["gov_publication_links"] = links[:6]
    pdf_links = sorted(set(re.findall(r'href="(/[^"]+\.pdf[^"]*)"', html)))
    out_dir = settings.RAW_DIR / "shcsr"
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    for href in (pdf_links[:8] + []):
        try:
            content = get(f"https://www.gov.ie{href.split('?')[0]}", timeout=300)
            name = re.sub(r"[^A-Za-z0-9._-]+", "_", href)[:80] + ".pdf"
            (out_dir / name).write_bytes(content)
            saved += 1
        except Exception:
            continue
        time.sleep(1.0)
    # Follow publication pages for attached PDFs.
    for href in links[:5]:
        try:
            page_html = get(f"https://www.gov.ie{href}", timeout=90).decode("utf-8", errors="ignore")
            attached = sorted(set(re.findall(r'href="([^"]+\.pdf[^"]*)"', page_html)))
            for pdf in attached[:3]:
                pdf_url = pdf if pdf.startswith("http") else f"https://www.gov.ie{pdf}"
                try:
                    content = get(pdf_url, timeout=300)
                    name = re.sub(r"[^A-Za-z0-9._-]+", "_", pdf_url)[:90] + ".pdf"
                    (out_dir / name).write_bytes(content)
                    saved += 1
                except Exception:
                    continue
                time.sleep(1.0)
        except Exception as exc:
            report.setdefault("gov_page_errors", []).append({"href": href[:60], "error": str(exc)})
    report["shcsr"] = {"pdf_links_found": len(pdf_links), "publication_links": len(links), "saved": saved}
except Exception as exc:
    report["shcsr_error"] = str(exc)

# ---- 4. excavations.ie: retry with backoff, both protocols ----
for scheme in ("https://", "http://"):
    for attempt in range(2):
        try:
            html = get(f"{scheme}excavations.ie/search/", timeout=120).decode("utf-8", errors="ignore")
            (settings.RAW_DIR / "excavations" / f"probe_{scheme.replace(':', '')}.html").write_text(html, encoding="utf-8")
            report["excavations"] = {"scheme": scheme, "len": len(html)}
            break
        except Exception as exc:
            report.setdefault("excavations_errors", []).append(f"{scheme} attempt {attempt}: {exc}")
            time.sleep(5.0)
    if "excavations" in report:
        break

out = settings.SILVER_DIR / "tranche2_fix2_report.json"
out.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
