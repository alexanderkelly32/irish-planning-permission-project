"""Zero-day pull: FI letters + grant/decision reasons + appeal docs.

Per clean scheme (2018-2023, iDocs councils): fetch doc types matching
F.I. Request/Received, Notification of Decision, Chief Executives Order,
Final Grant/Schedule (grant reasons), and any Appeal doc (party/grounds).
Texts saved to silver/usp/pull_docs/{case_key}/{docid}.json with
type/comment/text/chars. Resume-safe via silver/usp/pull_state.json.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from patchright.sync_api import sync_playwright  # noqa: E402

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "usp" / "pull_docs"
OUT.mkdir(parents=True, exist_ok=True)
STATE = SILVER / "usp" / "pull_state.json"

TARGET_TYPES = re.compile(
    r"f\.?i\.? (request|received)|further information|notification of decision|"
    r"chief executives order|final grant|schedule of conditions|appeal", re.I)


def main() -> None:
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"done": {}}
    clean = pd.read_csv(SILVER / "dq" / "labels_clean.csv", dtype=str)
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "PlanningAuthority", "ApplicationNumber", "GrantDate"])
    reg = reg.drop_duplicates("case_key")
    reg["grant_dt"] = pd.to_datetime(reg["GrantDate"], utc=True, errors="coerce").dt.tz_localize(None)
    hosts = json.loads((SILVER / "idocs" / "council_hosts.json").read_text(encoding="utf-8"))
    cohort = reg[reg["case_key"].isin(set(clean["case_key"]))]
    cohort = cohort[cohort["grant_dt"].dt.year.between(2018, 2023)]
    cohort = cohort[cohort["PlanningAuthority"].map(hosts).notna()]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        try:
            for _, r in cohort.iterrows():
                key = r["case_key"]
                if key in state["done"]:
                    continue
                host = hosts.get(r["PlanningAuthority"])
                app_id = str(r["ApplicationNumber"]).strip()
                scheme_dir = OUT / key[:80]
                scheme_dir.mkdir(parents=True, exist_ok=True)
                page = browser.new_page()
                docs = []
                try:
                    page.goto(f"https://{host}/idocswebDPSS/copyright.aspx?catalog=planning&id={app_id}",
                              timeout=120000)
                    page.check("#chkAgree")
                    time.sleep(1)
                    page.click("#btnViewFiles")
                    page.wait_for_load_state("domcontentloaded", timeout=60000)
                    time.sleep(2)
                    html = page.content()
                    for m in re.finditer(r"<tr[^>]*>.*?</tr>", html, re.S):
                        tr = m.group(0)
                        docid_m = re.search(r"docid=(\d+)", tr)
                        if not docid_m:
                            continue
                        cells = [re.sub(r"<[^>]+>", "", c).replace("&nbsp;", "").strip()
                                 for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
                        cells = [re.sub(r"\s+", " ", c) for c in cells]
                        docs.append({"docid": docid_m.group(1), "type": cells[0] if cells else "",
                                     "comment": cells[1] if len(cells) > 1 else ""})
                except Exception as exc:
                    state["done"][key] = {"status": "flow_error", "error": str(exc)[:80]}
                    page.close()
                    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
                    continue
                n_saved = 0
                for doc in docs:
                    if not TARGET_TYPES.search(doc["type"] + " " + doc["comment"]):
                        continue
                    docid = doc["docid"]
                    out_json = scheme_dir / f"{docid}.json"
                    if out_json.exists():
                        n_saved += 1
                        continue
                    try:
                        page.goto(f"https://{host}/idocswebDPSS/ViewFiles.aspx?docid={docid}&format=jpeg",
                                  timeout=120000)
                        src = ""
                        for _ in range(10):
                            time.sleep(1)
                            frame = page.query_selector("#frame1")
                            src = frame.get_attribute("src") if frame else ""
                            if "file=" in src:
                                break
                        mp = re.search(r"file=([^&\s]+\.pdf)", src)
                        if mp:
                            blob = page.context.request.get(
                                f"https://{host}/idocswebDPSS/files/{mp.group(1)}", timeout=120000)
                            if blob.ok:
                                import fitz
                                doc_pdf = fitz.open(stream=blob.body(), filetype="pdf")
                                text = " ".join(pg.get_text() for pg in doc_pdf)
                                if len(text.strip()) < 300:
                                    from rapidocr_onnxruntime import RapidOCR
                                    engine = RapidOCR()
                                    parts = []
                                    for i, pg in enumerate(doc_pdf):
                                        if i >= 6:
                                            break
                                        pix = pg.get_pixmap(dpi=150)
                                        res, _ = engine(pix.tobytes("png"))
                                        if res:
                                            parts.append(" ".join(l[1] for l in res))
                                    text = "\n".join(parts)
                                out_json.write_text(json.dumps(
                                    {"docid": docid, "type": doc["type"], "comment": doc["comment"],
                                     "chars": len(text), "text": text}, indent=2), encoding="utf-8")
                                n_saved += 1
                    except Exception:
                        continue
                page.close()
                state["done"][key] = {"status": "ok", "n_target_docs": n_saved}
                STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
                print(key, "docs:", n_saved, flush=True)
                time.sleep(0.5)
        finally:
            browser.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
