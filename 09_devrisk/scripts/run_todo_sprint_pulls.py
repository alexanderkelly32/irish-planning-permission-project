"""Runner: SHCSR harvester + Uisce county pages (scrapling, background-safe).

1. SHCSR: scrape the gov.ie publications search page (unblocked by
   scrapling) for the quarterly Social Housing Construction Status
   Report PDFs, download, save.
2. Uisce: fetch the per-county wastewater capacity register pages, parse
   plant name + status mentions, save a WWTP-status lookup.
3. Excavations: fetch the search page, save for parser work.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scrapling import StealthyFetcher  # noqa: E402

from devrisk import settings  # noqa: E402

OUT_DIR = settings.RAW_DIR / "infrastructure"

COUNTIES = ["carlow", "cavan", "clare", "cork", "cork-city", "donegal", "dublin", "fingal",
            "galway", "kerry", "kildare", "kilkenny", "laois", "leitrim", "limerick", "longford",
            "louth", "mayo", "meath", "monaghan", "offaly", "roscommon", "sligo", "tipperary",
            "waterford", "westmeath", "wexford", "wicklow"]


if __name__ == "__main__":
    report: dict = {}
    fetcher = StealthyFetcher()

    # ---- SHCSR ----
    try:
        page = fetcher.fetch("https://www.gov.ie/en/publications/?q=social+housing+construction+status+report", timeout=90000)
        pdfs = sorted(set(re.findall(r'href="([^"]+\.pdf[^"]*)"', page.html_content)))
        saved = 0
        out_dir = settings.RAW_DIR / "shcsr"
        out_dir.mkdir(parents=True, exist_ok=True)
        for href in pdfs[:12]:
            url = href if href.startswith("http") else f"https://www.gov.ie{href}"
            try:
                blob = fetcher.fetch(url, timeout=180000)
                if len(blob.body) > 5000:
                    (out_dir / f"shcsr_{saved}.pdf").write_bytes(blob.body)
                    saved += 1
            except Exception:
                continue
        report["shcsr"] = {"pdfs_found": len(pdfs), "saved": saved}
    except Exception as exc:
        report["shcsr"] = {"error": str(exc)[:140]}

    # ---- Uisce county pages ----
    try:
        uisce_dir = OUT_DIR / "uisce_counties"
        uisce_dir.mkdir(parents=True, exist_ok=True)
        statuses = {}
        for county in COUNTIES:  # all counties; resume-safe by file presence
            target = uisce_dir / f"{county}.html"
            if target.exists():
                continue
            try:
                page = fetcher.fetch(
                    f"https://www.water.ie/connections/developer-services/capacity-registers/wastewater-treatment-capacity-register/{county}/",
                    timeout=90000)
                text = page.html_content
                target.write_text(text, encoding="utf-8")
                statuses[county] = {
                    "available": len(re.findall(r"capacity available|available capacity|green", text, re.I)),
                    "constrained": len(re.findall(r"constrained|not available|under pressure|amber|red", text, re.I)),
                    "len": len(text),
                }
            except Exception as exc:
                statuses[county] = {"error": str(exc)[:100]}
        report["uisce_counties"] = statuses
    except Exception as exc:
        report["uisce_counties"] = {"error": str(exc)[:140]}

    # ---- Excavations page ----
    try:
        page = fetcher.fetch("https://excavations.ie/search/", timeout=90000)
        (OUT_DIR / "excavations_search.html").write_text(page.html_content, encoding="utf-8")
        report["excavations"] = {"len": len(page.html_content)}
    except Exception as exc:
        report["excavations"] = {"error": str(exc)[:140]}

    out = settings.SILVER_DIR / "todo_sprint_pulls.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
