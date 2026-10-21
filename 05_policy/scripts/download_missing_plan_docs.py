#!/usr/bin/env python3
"""Download the located missing council plan documents into staging."""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[2]
STAGING = ROOT / "05_policy" / "documents" / "staging"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "en-IE,en;q=0.9",
}

SLIGO_BASE = "https://www.sligococo.ie"
WEXFORD_BASE = "https://www.wexfordcoco.ie"

TARGETS = {
    "sligo": [
        SLIGO_BASE + "/cdp/Sligo%20CDP%202024-2030%20-%20Volume%201%20-%20Core%20Strategy%20(updated%20after%20Variation%20No.1).pdf",
        SLIGO_BASE + "/cdp/Sligo%20CDP%202024-2030%20-%20Volume%203%20-%20General%20policies%20(updated%20after%20Variation%20No.%201).pdf",
        SLIGO_BASE + "/cdp/5.%20Appendix%20A%20-%20Infrastructural%20Assessment.pdf",
        SLIGO_BASE + "/cdp/6.%20Appendices%20B%20to%20I%20(combined).pdf",
        SLIGO_BASE + "/cdp/8.%20Housing%20Strategy.pdf",
        SLIGO_BASE + "/cdp/9.%20Sligo%20Local%20Transport%20Plan.pdf",
        SLIGO_BASE + "/cdp/11.%20Record%20of%20Protected%20Structures%202024-2030%20(unchanged%20since%202017).pdf",
    ],
    "wexford": [
        WEXFORD_BASE + "/sites/default/files/content/Book-1-CE-Report-on-Submissions-OPR-SRA-EMRA-and-Volume-1-Written-Statement.pdf",
        WEXFORD_BASE + "/sites/default/files/content/Book-2-Section-1-Volume-2-Development-Management-Manual.pdf",
        WEXFORD_BASE + "/sites/default/files/content/Book-2-Section-2-Volume-3-Bunclody-Town-Settlement-Plan.pdf",
        WEXFORD_BASE + "/sites/default/files/content/Book-2-Section-3-Volume-3-Rosslare-Harbour-and-Kilrane-Settlement-Plan.pdf",
        WEXFORD_BASE + "/sites/default/files/content/Book-2-Section-4-Volume-3-Castlebridge-Specific-Objectives.pdf",
        WEXFORD_BASE + "/sites/default/files/content/Book-2-Section-5-Volume-3-Rosslare-Strand-Specific-Objectives.pdf",
        WEXFORD_BASE + "/sites/default/files/content/Book-4-Section-2-Volume-9-Housing-Strategy.pdf",
        WEXFORD_BASE + "/sites/default/files/content/Book-4-Section-3-Volume-11-Strategic-Flood-Risk-Assessment.pdf",
        WEXFORD_BASE + "/sites/default/files/content/Book-3-CE-Report-Volume-5-Record-Of-Protected-Structures.pdf",
    ],
    "offaly": [
        "https://www.offaly.ie/app/uploads/Chapter-1-Introduction_as-varied-1.pdf",
        "https://www.offaly.ie/app/uploads/Chapter-2-Core-Strategy_as-varied.pdf",
        "https://www.offaly.ie/app/uploads/Chapter-3-Climate-Action-Energy_as-varied-1.pdf",
        "https://www.offaly.ie/app/uploads/Chapter-4-Biodiversity-and-Landscape_as-varied-1.pdf",
        "https://www.offaly.ie/app/uploads/Chapter-5-Economic-Development-Strategy.pdf",
        "https://www.offaly.ie/app/uploads/Chapter-6-Tourism-and-Recreational-Development.pdf",
        "https://www.offaly.ie/app/uploads/Chapter-7-Retail-Town-Centre-Strategy-and-Regeneration.pdf",
        "https://www.offaly.ie/app/uploads/Chapter-8-Sustainable-Transport-Strategy.pdf",
        "https://www.offaly.ie/app/uploads/Chapter-9-Social-Inclusion-Community-and-Cultural-Development.pdf",
        "https://www.offaly.ie/app/uploads/Chapter-10-Built-Heritage.pdf",
        "https://www.offaly.ie/app/uploads/Chapter-11-Water-Services-and-Environment.pdf",
        "https://www.offaly.ie/app/uploads/Chapter-12-Land-Use-Zoning-Objectives.pdf",
        "https://www.offaly.ie/app/uploads/Chapter-13-Development-Management-Standards_as-varied.pdf",
        "https://www.offaly.ie/app/uploads/Chapter-14-Implementation-and-Monitoring.pdf",
        "https://www.offaly.ie/app/uploads/Appendix-1-Transport-Modal-Shift-in-Portrait-1.pdf",
        "https://www.offaly.ie/app/uploads/Appendix-2-Settlement-Capacity-Audit-1.pdf",
        "https://www.offaly.ie/app/uploads/Housing-Strategy-and-Housing-Needs-Demand-Assessment.pdf",
        "https://www.offaly.ie/app/uploads/Record-of-Protected-Structures_current-version.pdf",
    ],
    "waterford": [
        f"https://waterfordcouncil.ie/app/uploads/2023/09/WCCCDP-2022-2028-Vol-1-Chapter-{n}.pdf"
        for n in (1, 2, 3, 5, 6, 7, 8, 9, 10, 11)
    ] + [
        "https://waterfordcouncil.ie/app/uploads/2023/09/WCccDP-2022-2028-Vol-1-Chapter-4.pdf",
    ],
    "kerry": [
        "http://docstore.kerrycoco.ie/KCCWebsite/planning/devplan/volonewritten.pdf",
        "http://docstore.kerrycoco.ie/KCCWebsite/planning/devplan/vol2updated.pdf",
        "http://docstore.kerrycoco.ie/KCCWebsite/planning/devplan/volthreenew.pdf",
        "http://docstore.kerrycoco.ie/KCCWebsite/planning/devplan/vol4updated.pdf",
        "http://docstore.kerrycoco.ie/KCCWebsite/planning/devplan/vol6updated.pdf",
        "http://docstore.kerrycoco.ie/KCCWebsite/planning/devplan/voloneappendix.pdf",
    ],
    "donegal": [
        "https://www.donegalcocodocs.ie/docs/CDP2024-2030-AsVaried31.08.26WebVersion.pdf",
        "https://www.donegaldevplan.ie/s/Location-Siting-and-Design-Guide-2024-2030-with-front-cover.pdf",
    ],
    "carlow": [
        "https://consult.carlow.ie/en/system/files/materials/2011/Variation%20No.%204%20Report%20.pdf",
        "https://consult.carlow.ie/en/system/files/materials/907/CE%20Report%20NPF%20Housing%20Growth%20Targets.pdf",
    ],
    "roscommon": [
        "https://www.rosdevplan.ie/rccdevpdfs/final/RCC-Dev-Plan-2022-2028-Volume-I.pdf",
        "https://www.rosdevplan.ie/rccdevpdfs/final/RCC-Dev-Plan-2022-2028-Volume-II.pdf",
        "https://www.rosdevplan.ie/rccdevpdfs/final/RCC-Dev-Plan-Housing-Strategy-and-Housing-Need-Demand-Assessment.pdf",
        "https://www.rosdevplan.ie/rccdevpdfs/final/RCC-Dev-Plan-Record-of-Protected-Structures.pdf",
        "https://www.rosdevplan.ie/rccdevpdfs/final/RCC-Dev-Plan-Retail-Strategy.pdf",
        "https://www.rosdevplan.ie/rccdevpdfs/final/RCC-Dev-Plan-Renewable-Energy-Strategy.pdf",
    ],
}


def safe_name(url: str) -> str:
    name = Path(urlparse(url).path).name
    name = re.sub(r"[^\w\-. ]", "_", name)
    return name[:120]


def main() -> None:
    STAGING.mkdir(parents=True, exist_ok=True)
    results = []
    session = requests.Session()
    for slug, urls in TARGETS.items():
        for url in urls:
            name = safe_name(url)
            out = STAGING / slug / f"staged__{name}"
            if out.exists():
                results.append({"council": slug, "file": name, "status": "exists"})
                continue
            verify = slug != "sligo"
            try:
                response = session.get(url, headers=HEADERS, timeout=180, verify=verify)
            except requests.exceptions.SSLError:
                response = session.get(url, headers=HEADERS, timeout=180, verify=False)
            except requests.RequestException as exc:
                results.append({"council": slug, "file": name, "status": f"error {type(exc).__name__}"})
                print(json.dumps(results[-1]), flush=True)
                continue
            if response.status_code != 200:
                results.append({"council": slug, "file": name, "status": f"http {response.status_code}"})
                print(json.dumps(results[-1]), flush=True)
                continue
            data = response.content
            if not data.startswith(b"%PDF"):
                results.append({"council": slug, "file": name, "status": f"not_pdf {data[:16]!r}"})
                print(json.dumps(results[-1]), flush=True)
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()[:12]
            results.append({"council": slug, "file": name, "status": "downloaded", "bytes": len(data), "sha256": digest})
            print(json.dumps(results[-1]), flush=True)
            time.sleep(0.3)
    ok = [r for r in results if r["status"] in ("downloaded", "exists")]
    print(json.dumps({"downloaded_ok": len(ok), "total": len(results)}))


if __name__ == "__main__":
    main()
