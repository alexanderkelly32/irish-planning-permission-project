"""Runner: excavations.ie probe (archaeology records).

Free national archive of excavation summaries (dates, client, site). Probes
the public search endpoint shape and saves whatever is retrievable for later
parsing (site-entry dates, developer/client names).
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

OUT_DIR = settings.RAW_DIR / "excavations"
USER_AGENT = "Mozilla/5.0 planning-risk-review/1.0 (local personal research)"

if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report: dict = {}
    for url in (
        "https://excavations.ie/search/",
        "https://excavations.ie/",
    ):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8", errors="ignore")
            (OUT_DIR / f"probe_{url.split('/')[2]}.html").write_text(body, encoding="utf-8")
            forms = re.findall(r"<form[^>]*action=\"([^\"]+)\"", body, re.IGNORECASE)[:3]
            inputs = re.findall(r"<input[^>]*name=\"([^\"]+)\"", body, re.IGNORECASE)[:15]
            report[url] = {"len": len(body), "forms": forms, "inputs": inputs}
        except Exception as exc:
            report[url] = {"error": str(exc)}
        time.sleep(1.0)
    print(json.dumps(report, indent=2), flush=True)
