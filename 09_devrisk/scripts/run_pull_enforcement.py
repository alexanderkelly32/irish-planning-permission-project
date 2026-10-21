"""Runner: enforcement-notice page harvest across the 31 authorities.

The matrix's enforcement column notes per-authority access without URLs, so
this stage fetches each council's planning-enforcement page (URL-pattern
guesses), stores text, and logs which authorities publish actual lists.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

from devrisk import settings  # noqa: E402

OUT_DIR = settings.SILVER_DIR / "enforcement_pages"
STATE_PATH = OUT_DIR / "state.json"

ENFORCEMENT_URLS = {
    "carlow": "https://carlow.ie/planning-and-building/development-management/planning-enforcement/",
    "cavan": "https://www.cavancoco.ie/services/planning-building/planning-enforcement/",
    "clare": "https://www.clarecoco.ie/services/planning/enforcement/",
    "cork_city": "https://www.corkcity.ie/en/council-services/services/planning/planning-enforcement/",
    "cork_county": "https://www.corkcoco.ie/en/resident/planning/planning-enforcement/",
    "donegal": "https://www.donegalcoco.ie/services/planning/planningenforcement/",
    "dublin_city": "https://www.dublincity.ie/residential/planning/planning-applications/planning-enforcement",
    "dlr": "https://www.dlrcoco.ie/en/planning/planning-enforcement",
    "fingal": "https://www.fingal.ie/planning-enforcement",
    "galway_city": "https://www.galwaycity.ie/planning-enforcement",
    "galway_county": "https://www.galway.ie/en/services/planning/planning-enforcement/",
    "kerry": "https://www.kerrycoco.ie/planning/enforcement/",
    "kildare": "https://kildarecoco.ie/AllServices/Planning/PlanningEnforcement/",
    "kilkenny": "https://kilkennycoco.ie/eng/services/planning/planning-enforcement/",
    "laois": "https://laois.ie/departments/planning/planning-enforcement/",
    "leitrim": "https://www.leitrim.ie/council/services/planning-building/planning-enforcement/",
    "limerick": "https://www.limerick.ie/council/services/planning-and-placemaking/planning-enforcement",
    "longford": "https://www.longfordcoco.ie/services/planning/planning-enforcement/",
    "louth": "https://www.louthcoco.ie/services/planning/planning-enforcement/",
    "mayo": "https://www.mayo.ie/en-ie/your-council/services/planning/planning-enforcement",
    "meath": "https://www.meath.ie/council/council-services/planning-and-building/planning-enforcement",
    "monaghan": "https://monaghan.ie/planning/planning-enforcement/",
    "offaly": "https://www.offaly.ie/eng/Services/Planning/Planning_Enforcement/",
    "roscommon": "https://www.roscommoncoco.ie/en/services/planning/planning-enforcement/",
    "sligo": "https://www.sligococo.ie/Services/Planning/PlanningEnforcement/",
    "south_dublin": "https://www.sdcc.ie/en/services/planning-building-control/planning-enforcement/",
    "tipperary": "https://www.tipperarycoco.ie/planning/planning-enforcement",
    "waterford": "https://waterfordcouncil.ie/services/planning/planning-enforcement/",
    "westmeath": "https://www.westmeathcoco.ie/en/ourservices/planning/planningenforcement/",
    "wexford": "https://www.wexfordcoco.ie/planning/planning-enforcement",
    "wicklow": "https://www.wicklow.ie/Living/Services/Planning/Planning-Enforcement",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) planning-risk-review/1.0 (local research)"}


def clean_html(text: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", text)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = {"done": {}, "failed": {}}
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

    for authority, url in ENFORCEMENT_URLS.items():
        if authority in state["done"] or authority in state["failed"]:
            continue
        try:
            response = requests.get(url, timeout=45, headers=HEADERS, allow_redirects=True)
            text = clean_html(response.text)
            text_path = OUT_DIR / f"{authority}_enforcement.txt"
            text_path.write_text(text, encoding="utf-8", errors="ignore")
            has_list = bool(re.search(r"(list|register|notices? issued)", text, re.IGNORECASE)) and len(text) > 800
            state["done"][authority] = {"status": response.status_code, "chars": len(text), "looks_like_list": has_list}
        except Exception as error:  # noqa: BLE001
            state["failed"][authority] = f"{type(error).__name__}: {str(error)[:120]}"
        STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
        print(authority, state["done"].get(authority, state["failed"].get(authority)), flush=True)

    summary = {
        "done": len(state["done"]),
        "failed": len(state["failed"]),
        "looks_like_list": int(sum(1 for v in state["done"].values() if v.get("looks_like_list"))),
        "out_dir": str(OUT_DIR),
        "failures": state["failed"],
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
