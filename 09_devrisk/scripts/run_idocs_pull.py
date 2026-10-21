"""Phase 2: pull iDocs document ledgers + decision-doc images (patchright only).

Reads hosts.json from phase 1. For each scheme: two-step flow
(chkAgree + btnViewFiles) -> parse listFiles table -> save ledger JSON ->
download JPEG pages for Decision/Order/Condition documents.

Resume-safe via state.json (schemes in done are skipped).
"""
from __future__ import annotations

import json
import re
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from patchright.sync_api import sync_playwright  # noqa: E402

from devrisk import settings  # noqa: E402

OUT = settings.SILVER_DIR / "idocs"
OUT.mkdir(parents=True, exist_ok=True)
DOCS = OUT / "docs"
DOCS.mkdir(parents=True, exist_ok=True)
STATE = OUT / "state.json"
HOSTS_PATH = OUT / "hosts.json"

DECISION_TYPES = re.compile(r"decision|order|condition", re.I)


def main() -> None:
    state = {}
    if STATE.exists():
        state = json.loads(STATE.read_text(encoding="utf-8"))
    hosts = json.loads(HOSTS_PATH.read_text(encoding="utf-8"))
    with zipfile.ZipFile(settings.SILVER_DIR / "audit_packs" / "PACK_24_residual_forensics.zip") as z:
        df = pd.read_csv(z.open("residual_forensics_cohort.csv"))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        try:
            for _, row in df.iterrows():
                key = row["case_key"]
                if key in state.get("done", {}):
                    continue
                entry = hosts.get(key)
                if not entry:
                    state.setdefault("done", {})[key] = {"status": "no_host"}
                    print(key, "-> no_host", flush=True)
                    continue
                host, app_id = entry
                url = f"https://{host}/idocswebDPSS/copyright.aspx?catalog=planning&id={app_id}"
                result = {"case_key": key, "host": host, "app_id": app_id, "docs": []}
                page = browser.new_page()
                try:
                    page.goto(url, timeout=120000)
                    page.check("#chkAgree")
                    time.sleep(2)
                    page.click("#btnViewFiles")
                    page.wait_for_load_state("networkidle", timeout=60000)
                    html = page.content()
                    for m in re.finditer(r"<tr[^>]*>.*?</tr>", html, re.S):
                        tr = m.group(0)
                        docid_m = re.search(r"docid=(\d+)", tr)
                        if not docid_m:
                            continue
                        cells = [re.sub(r"<[^>]+>", "", c).replace("&nbsp;", "").strip()
                                 for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
                        cells = [re.sub(r"\s+", " ", c) for c in cells]
                        doc = {"docid": docid_m.group(1),
                               "type": cells[0] if cells else "",
                               "comment": cells[1] if len(cells) > 1 else "",
                               "n_files": cells[2] if len(cells) > 2 else "",
                               "size": cells[3] if len(cells) > 3 else ""}
                        result["docs"].append(doc)
                    result["status"] = "ok"
                    page.close()
                except Exception as exc:
                    result["status"] = "error"
                    result["error"] = str(exc)[:200]
                    try:
                        page.close()
                    except Exception:
                        pass
                decision = [d for d in result["docs"] if DECISION_TYPES.search(d["type"] + " " + d["comment"])]
                print(key, "->", result["status"], "docs:", len(result["docs"]),
                      "decision-docs:", len(decision), flush=True)
                ledger_path = OUT / f"ledger_{key.replace(' ', '_').replace('/', '_')[:80]}.json"
                ledger_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
                state.setdefault("done", {})[key] = {k: v for k, v in result.items() if k != "docs"}
                state["done"][key]["decision_docids"] = [d["docid"] for d in decision]
                STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
                time.sleep(1)
        finally:
            browser.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
