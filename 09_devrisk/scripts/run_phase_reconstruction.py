"""Phase reconstruction pilot (iDocs drawings) - reopened.

For the 9 shortlisted estates: pull site-layout/phasing drawings via the
now-working iDocs flow, extract phase/unit evidence from doc text, and
validate reconstructed phase denominators against BCMS ground-truth phase
units (CN_Units_for_phase). No modelling. Verdict: can phase/unit
boundaries be recovered at >=95% audited precision?
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
OUT = SILVER / "phase_pilot"
OUT.mkdir(parents=True, exist_ok=True)

ESTATES = [
    ("Limerick 21531", "eplan.limerick.ie", "21531"),
    ("Kildare 18711", "idocsweb.kildarecoco.ie", "18711"),
    ("Tipperary 20171", "TipperaryCoCo.ePlanning.ie", "20171"),
    ("Kildare 181027", "idocsweb.kildarecoco.ie", "181027"),
    ("Kildare 18541", "idocsweb.kildarecoco.ie", "18541"),
    ("Waterford 21836", "WaterfordCouncil.ePlanning.ie", "21836"),
    ("Wicklow 181193", "WicklowCoCo.ePlanning.ie", "181193"),
    ("Galway City 18127", "galwaycity.eplanning.ie", "18127"),
    ("Meath 22930", "idocswebdpss.meathcoco.ie", "22930"),
]
DRAW_TYPES = re.compile(r"site layout|layout plan|phasing|master plan|overall site|drawings|floor plan|"
                        r"plans, sections|elevation|section|site plan|site location", re.I)


def build_ground_truth() -> pd.DataFrame:
    raw = pd.read_csv(settings.RAW_DIR / "bcms_buildingscnscccs.csv",
                      usecols=["IDs", "CN_Units_for_phase", "CN_Phase_for_this_Notice",
                               "CN_Total_Number_of_Dwelling_Units"],
                      low_memory=False, dtype=str)
    ev = pd.read_parquet(SILVER / "bcms_events_silver.parquet",
                         columns=["bcms_event_id", "source_row_id"])
    ev["IDs"] = ev["source_row_id"].str.split("__").str[0]
    raw = raw.merge(ev[["IDs", "bcms_event_id"]], on="IDs", how="inner")
    raw["units"] = pd.to_numeric(raw["CN_Units_for_phase"], errors="coerce")
    links = pd.read_csv(SILVER / "bcms_links_all_granted.csv", dtype=str)
    raw = raw.merge(links[["bcms_event_id", "scheme_id"]], on="bcms_event_id", how="inner")
    return raw


def main() -> None:
    truth = build_ground_truth()
    truth.to_csv(OUT / "bcms_phase_ground_truth.csv", index=False)
    print("ground truth rows:", len(truth), "schemes:", truth["scheme_id"].nunique(), flush=True)

    pull_results = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        try:
            for name, host, app_id in ESTATES:
                entry = {"name": name, "host": host, "app_id": app_id, "docs": []}
                page = browser.new_page()
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
                        entry["docs"].append({"docid": docid_m.group(1),
                                              "type": cells[0] if cells else "",
                                              "comment": cells[1] if len(cells) > 1 else "",
                                              "n_files": cells[2] if len(cells) > 2 else ""})
                    entry["status"] = "ledger_ok"
                except Exception as exc:
                    entry["status"] = f"flow_error: {str(exc)[:80]}"
                    page.close()
                    pull_results[name] = entry
                    print(name, entry["status"], flush=True)
                    continue
                scheme_dir = OUT / name.replace(" ", "_")
                scheme_dir.mkdir(exist_ok=True)
                texts = {}
                for doc in entry["docs"]:
                    if not DRAW_TYPES.search(doc["type"] + " " + doc["comment"]):
                        continue
                    docid = doc["docid"]
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
                                pdf_path = scheme_dir / f"{docid}.pdf"
                                pdf_path.write_bytes(blob.body())
                                import fitz
                                doc_pdf = fitz.open(pdf_path)
                                text = " ".join(pg.get_text() for pg in doc_pdf)
                                if len(text.strip()) < 200:
                                    from rapidocr_onnxruntime import RapidOCR
                                    engine = RapidOCR()
                                    parts = []
                                    for i, pg in enumerate(doc_pdf):
                                        if i >= 2:
                                            break
                                        pix = pg.get_pixmap(dpi=150)
                                        result, _ = engine(pix.tobytes("png"))
                                        if result:
                                            parts.append(" ".join(l[1] for l in result))
                                    text = "\n".join(parts)
                                texts[docid] = {"type": doc["type"], "comment": doc["comment"],
                                                "chars": len(text), "text": text[:6000]}
                    except Exception as exc:
                        texts[docid] = {"type": doc.get("type", ""), "comment": doc.get("comment", ""),
                                        "error": str(exc)[:80]}
                page.close()
                (scheme_dir / "drawing_texts.json").write_text(json.dumps(texts, indent=2), encoding="utf-8")
                entry["n_drawing_docs"] = len(texts)
                entry["n_with_text"] = sum(1 for v in texts.values() if v.get("chars", 0) > 200)
                pull_results[name] = entry
                print(name, "ledger docs:", len(entry["docs"]), "drawing docs:", len(texts),
                      "with text:", entry["n_with_text"], flush=True)
        finally:
            browser.close()
    (OUT / "pull_results.json").write_text(json.dumps(pull_results, indent=2), encoding="utf-8")

    extract = {}
    for name, host, app_id in ESTATES:
        d = OUT / name.replace(" ", "_") / "drawing_texts.json"
        if not d.exists():
            extract[name] = {"status": "no_texts"}
            continue
        texts = json.loads(d.read_text(encoding="utf-8"))
        phases = {}
        for docid, v in texts.items():
            blob = f"{v.get('type', '')} {v.get('comment', '')} {v.get('text', '')}"
            for m in re.finditer(r"phase\s*([A-Za-z0-9])", blob, re.I):
                phases.setdefault(m.group(1).upper(), set())
                window = blob[max(0, m.start() - 60):m.start() + 200]
                for um in re.finditer(r"(\d{1,3})\s*(?:no\.?|units|houses|dwellings|residential)", window, re.I):
                    phases[m.group(1).upper()].add(int(um.group(1)))
        extract[name] = {"status": "ok", "phases_found": sorted(phases.keys()),
                         "per_phase_unit_mentions": {k: sorted(list(v))[:6] for k, v in phases.items()}}
    (OUT / "extraction.json").write_text(json.dumps(extract, indent=2), encoding="utf-8")
    print(json.dumps(extract, indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
