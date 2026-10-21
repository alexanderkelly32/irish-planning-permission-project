"""Runner: pull taking-in-charge (TIC) pages for all 22 sources in the matrix.

Fetches each authority's TIC page/PDF, stores raw content + extracted text,
and logs per-source status. Matching estate names to schemes is the next
stage. Polite: 1.2s delay, resume-safe.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

from devrisk import settings  # noqa: E402

TIC_SOURCES = {
    "carlow": "https://carlow.ie/planning-and-building/development-management/taking-charge-estates-request",
    "clare": "https://www.clarecoco.ie/ga/node/416",
    "dublin_city": "https://www.dublincity.ie/planning-and-land-use/development-contributions-and-security-bonds/bonds-and-taking-charge",
    "fingal": "https://www.fingal.ie/housing-fingal/taking-charge-information",
    "galway_city": "https://www.galwaycity.ie/services/planning-and-building/taking-in-charge-of-estates",
    "galway_county": "https://www.galway.ie/en/planning-building/development-management/taking-charge-completed-residential-developments",
    "kerry": "https://www.kerrycoco.ie/planning/development-management/housing-estates/",
    "kildare": "https://kildarecoco.ie/AllServices/BuildingandDevelopmentControl/DevelopmentControl/ListofEstatesTakeninCharge/",
    "kilkenny": "https://kilkennycoco.ie/eng/services/planning/planning-applications/taking-in-charge-of-housing-estates-process/list-of-estates-taken-in-charge.html",
    "leitrim": "https://www.leitrim.ie/council/services/planning-building/unfinished-estates-taking-in-charge/",
    "limerick": "https://www.limerick.ie/council/services/planning-and-placemaking/taking-in-charge-of-housing-estates/taking-in-charge",
    "longford": "https://www.longfordcoco.ie/services/planning/taking-in-charge/",
    "louth": "https://www.louthcoco.ie/services/planning/taking-in-charge/",
    "meath": "https://www.meath.ie/council/council-services/planning-and-building/taking-charge-of-roads-estates-0",
    "monaghan": "https://monaghan.ie/planning/taking-in-charge/",
    "roscommon": "https://www.roscommoncoco.ie/en/services/planning/search-planning-applications/planning-leaflets/15-a-guide-to-taking-in-charge-of-completed-residential-developments.pdf",
    "sligo": "https://www.sligococo.ie/Services/RoadsandParking/Roads/EstatesTakeninCharge/",
    "south_dublin": "https://sdcc.ie/en/services/planning-building-control/bonds-taking-in-charge/",
    "waterford": "https://waterfordcouncil.ie/services/planning/estate-management/taking-in-charge/",
    "westmeath": "https://www.westmeathcoco.ie/en/ourservices/planning/takingincharge/",
    "wexford": "https://www.wexfordcoco.ie/planning/building-control/taking-in-charge/list-of-taken-in-charge-estates",
    "wicklow": "https://www.wicklow.ie/Living/Services/Planning/Taking-in-Charge-of-a-Housing-Estate",
}

OUT_DIR = settings.SILVER_DIR / "tic_pages"
STATE_PATH = OUT_DIR / "state.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) planning-risk-review/1.0 (local research)"}


def extract_text(content: bytes, content_type: str) -> str:
    import io

    import fitz

    if "pdf" in (content_type or ""):
        document = fitz.open(stream=content, filetype="pdf")
        text = "\n".join(page.get_text() for page in document)
        document.close()
        return text.strip()
    import re

    text = content.decode("utf-8", errors="replace")
    text = re.sub(r"<script[\s\S]*?</script>", " ", text)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = {"done": {}, "failed": {}}
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

    for authority, url in TIC_SOURCES.items():
        if authority in state["done"]:
            continue
        try:
            response = requests.get(url, timeout=60, headers=HEADERS)
            content_type = response.headers.get("content-type", "")
            suffix = ".pdf" if "pdf" in content_type else ".html"
            raw_path = OUT_DIR / f"{authority}_tic{suffix}"
            raw_path.write_bytes(response.content)
            text = extract_text(response.content, content_type)
            text_path = OUT_DIR / f"{authority}_tic.txt"
            text_path.write_text(text, encoding="utf-8", errors="ignore")
            state["done"][authority] = {
                "status": response.status_code,
                "content_type": content_type,
                "chars": len(text),
                "url": url,
            }
        except Exception as error:  # noqa: BLE001
            state["failed"][authority] = f"{type(error).__name__}: {str(error)[:150]}"
        STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
        print(authority, state["done"].get(authority, state["failed"].get(authority)), flush=True)

    summary = {
        "done": len(state["done"]),
        "failed": len(state["failed"]),
        "with_substantial_text": int(sum(1 for v in state["done"].values() if v["chars"] > 800)),
        "out_dir": str(OUT_DIR),
        "failures": state["failed"],
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
