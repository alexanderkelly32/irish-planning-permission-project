"""Runner: E5 - infrastructure readiness pulls.

1. FSC/DAC national dataset from data.gov.ie (NBCO, 41k records).
2. Uisce Eireann capacity registers via scrapling (WWTP status pages).
3. Road-opening licences (Fingal + SDCC) from data.gov.ie.
Background-safe; saves raw with reports.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

OUT_DIR = settings.RAW_DIR / "infrastructure"
USER_AGENT = "Mozilla/5.0 planning-risk-review/1.0"

PACKAGE_IDS = {
    "fsc_dac": "applications",  # NBCO FSC/DAC dataset
    "road_licences_sdcc": "road-opening-licences-sdcc",
}

if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report: dict = {}

    def api(path: str) -> dict:
        request = urllib.request.Request(f"https://data.gov.ie/api/3/action/{path}", headers={"User-Agent": USER_AGENT})
        return json.loads(urllib.request.urlopen(request, timeout=60).read().decode("utf-8"))

    for name, package_id in PACKAGE_IDS.items():
        try:
            package = api(f"package_show?id={package_id}")
            resources = package["result"]["resources"]
            report[name] = {"resources": [{"name": r["name"], "format": r.get("format"), "url": r.get("url", "")[:120]} for r in resources[:6]]}
            for resource in resources[:2]:
                url = resource.get("url", "")
                if not url or not re.search(r"csv|xlsx", url, re.I):
                    continue
                try:
                    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                    content = urllib.request.urlopen(request, timeout=600).read()
                    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", resource.get("name", "file"))[:60]
                    (OUT_DIR / f"{name}_{safe}").write_bytes(content)
                    report[name].setdefault("downloaded", []).append({"bytes": len(content)})
                except Exception as exc:
                    report[name].setdefault("errors", []).append(str(exc)[:120])
        except Exception as exc:
            report[name] = {"error": str(exc)[:160]}

    # Uisce capacity register via scrapling
    try:
        from scrapling import StealthyFetcher  # noqa: E402

        page = StealthyFetcher.fetch(
            "https://www.water.ie/connections/developer-services/capacity-registers/wastewater-treatment-capacity-register",
            timeout=90000)
        text = page.html_content
        statuses = re.findall(r"(green|amber|red|available|not available|under pressure)", text, re.I)
        report["uisce_register"] = {"len": len(text), "status_mentions": {s.lower(): statuses.count(s.lower()) for s in set(statuses)},
                                    "saved": str(OUT_DIR / "uisce_capacity_register.html")}
        (OUT_DIR / "uisce_capacity_register.html").write_text(text, encoding="utf-8")
    except Exception as exc:
        report["uisce_register"] = {"error": str(exc)[:160]}

    out = settings.SILVER_DIR / "infrastructure_pull_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
