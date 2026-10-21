"""Runner: tranche-2 puller fixes (BER Fingal ArcGIS Hub API, TED v3 syntax
variants, gov.ie HTML search, excavations retry)."""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

UA = "Mozilla/5.0 planning-risk-review/1.0 (local personal research)"


def get(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def post(url: str, payload: dict, timeout: int = 90) -> bytes:
    request = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json", "User-Agent": UA},
                                     method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


report: dict = {}

# ---- BER Fingal via ArcGIS Hub API v3 ----
try:
    meta = json.loads(get("https://hub.arcgis.com/api/v3/datasets/FingalCoCo::ber-ratings-building-certs-2020-2024-fcc", timeout=90))
    report["ber_meta"] = {"keys": list(meta.keys())[:8]}
    data_links = meta.get("data", {}).get("links", [])
    csv_link = next((link["href"] for link in data_links if "csv" in link.get("href", "").lower() or "download" in link.get("href", "").lower()), None)
    if csv_link:
        out_dir = settings.RAW_DIR / "ber_fingal"
        out_dir.mkdir(parents=True, exist_ok=True)
        content = get(csv_link, timeout=600)
        (out_dir / "ber_2020_2024.csv").write_bytes(content)
        report["ber_download"] = {"bytes": len(content), "url": csv_link[:120]}
except Exception as exc:
    report["ber_error"] = str(exc)

# ---- TED v3 syntax variants ----
ted_rows = []
for variant in (
    {"query": "CPV=45000000", "fields": ["publication-number", "publication-date", "title", "buyer-name", "place-of-performance", "cpv-codes"], "page": 1, "limit": 100},
    {"query": 'CPV:"45000000" AND place-of-performance:IE', "fields": ["publication-number", "publication-date", "title"], "page": 1, "limit": 100},
):
    try:
        data = json.loads(post("https://api.ted.europa.eu/v3/notices/search", variant))
        notices = data.get("notices") or data.get("results") or []
        report[f"ted_variant_{len(report)}"] = {"rows": len(notices), "keys": list(data.keys())[:6]}
        ted_rows.extend(notices)
        if notices:
            break
    except Exception as exc:
        report[f"ted_variant_error"] = str(exc)
if ted_rows:
    out = settings.RAW_DIR / "ted" / "ted_construction_ie.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for row in ted_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    report["ted_saved"] = len(ted_rows)

# ---- gov.ie HTML search for SHCSR ----
try:
    html = get("https://www.gov.ie/en/search/?query=Social%20Housing%20Construction%20Status%20Report", timeout=90).decode("utf-8", errors="ignore")
    pdfs = sorted(set(re.findall(r'href="(/[^"]+\.pdf)"', html)))
    out_dir = settings.RAW_DIR / "shcsr"
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    for href in pdfs[:6]:
        try:
            content = get(f"https://www.gov.ie{href}", timeout=300)
            name = re.sub(r"[^A-Za-z0-9._-]+", "_", href)[:80] + ".pdf"
            (out_dir / name).write_bytes(content)
            saved += 1
        except Exception:
            continue
        time.sleep(1.0)
    report["shcsr"] = {"pdf_links_found": len(pdfs), "saved": saved, "sample": pdfs[:3]}
except Exception as exc:
    report["shcsr_error"] = str(exc)

# ---- excavations retry ----
try:
    html = get("https://excavations.ie/search/", timeout=120).decode("utf-8", errors="ignore")
    (settings.RAW_DIR / "excavations" / "probe_search.html").write_text(html, encoding="utf-8")
    report["excavations"] = {"len": len(html)}
except Exception as exc:
    report["excavations_error"] = str(exc)

out = settings.SILVER_DIR / "tranche2_fix_report.json"
out.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
