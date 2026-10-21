"""Scaled condition-schedule pull for the pre-grant conditions experiment.

Pulls ONLY grant/schedule documents per clean granted scheme (iDocs two-step
flow), parses condition families (financial/arch/ecol/uisce/roads/phasing/
pre-commencement counts) and saves silver/conditions/condition_corpus.csv.
Resume-safe via silver/conditions/state.json.
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
OUT = SILVER / "conditions"
OUT.mkdir(parents=True, exist_ok=True)
STATE = OUT / "state.json"

GRANT_TYPES = re.compile(r"final grant|schedule of conditions|chief executives order", re.I)
EXCLUDE = re.compile(r"post decision|notification of decision", re.I)

NUMBER_LINE_RE = re.compile(r"^\s*(\d{1,2}|l)\s*[\.\)]\s*$", re.I)
NUMBER_INLINE_RE = re.compile(r"^\s*(\d{1,2}|l)[\.\)]\s*\(?[a-z]?\)?\s*[A-Z(]", re.I)
PAGE_FOOTER_RE = re.compile(r"page\s*\d+?\s*of\s*\d+|inspection purposes only", re.I)
SPLIT_RE = re.compile(r"(\d{1,2}|l)\.\s*\(?([a-z])?\)?\s*([A-Z])")
PRE_COMM_RE = re.compile(r"prior to (?:the )?(?:commencement|any development|construction)|"
                         r"before (?:any )?(?:development|construction|works) commenc", re.I)
FAMILY_RE = {
    "financial": r"contribution|bond|security|financial|levy",
    "arch_ecol": r"archaeolog|ecolog|habitat|bat |bird|tree|natura|landscap",
    "uisce_drainage": r"uisce|irish water|water supply|wastewater|sewer|drainage|attenuation|surface water",
    "roads": r"road|access|footpath|cycle|traffic|junction|roundabout|car park",
    "phasing": r"phas",
}


def parse_conditions(text: str) -> list[str]:
    text = SPLIT_RE.sub(lambda m: f"\n{m.group(1)}.{m.group(2) or ''}{m.group(3)}", text or "")
    m = re.search(r"schedule of conditions|conditions attached|GENERAL", text, re.I)
    body = text[m.start():] if m else text
    conds, current = [], []
    for line in body.splitlines():
        if NUMBER_LINE_RE.match(line) or NUMBER_INLINE_RE.match(line):
            if current:
                conds.append(re.sub(r"\s+", " ", " ".join(current)).strip())
                current = []
        current.append(re.sub(NUMBER_LINE_RE, "", line).strip())
    if current:
        conds.append(re.sub(r"\s+", " ", " ".join(current)).strip())
    return [c for c in conds if len(c) > 40 and not PAGE_FOOTER_RE.search(c)]


def main() -> None:
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"done": {}}
    clean = pd.read_csv(SILVER / "dq" / "labels_clean.csv", dtype=str)
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                               columns=["case_key", "PlanningAuthority", "ApplicationNumber",
                                        "GrantDate", "NumResidentialUnits", "DevelopmentDescription"])
    register["grant_dt"] = pd.to_datetime(register["GrantDate"], utc=True, errors="coerce").dt.tz_localize(None)
    register = register.drop_duplicates("case_key")
    hosts = json.loads((SILVER / "idocs" / "council_hosts.json").read_text(encoding="utf-8"))
    cohort = register[register["case_key"].isin(set(clean["case_key"]))]
    cohort = cohort[cohort["grant_dt"].dt.year.between(2017, 2023)]
    cohort = cohort[cohort["PlanningAuthority"].map(hosts).notna() & (cohort["PlanningAuthority"].map(hosts) != "")]
    corpus = OUT / "condition_corpus.csv"
    done_rows = []
    if corpus.exists():
        done_rows = pd.read_csv(corpus, dtype=str)["case_key"].tolist()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        try:
            for _, r in cohort.iterrows():
                key = r["case_key"]
                if key in done_rows or key in state["done"]:
                    continue
                host = hosts.get(r["PlanningAuthority"])
                app_id = str(r["ApplicationNumber"]).strip()
                page = browser.new_page()
                texts = []
                try:
                    page.goto(f"https://{host}/idocswebDPSS/copyright.aspx?catalog=planning&id={app_id}",
                              timeout=120000)
                    page.check("#chkAgree")
                    time.sleep(1)
                    page.click("#btnViewFiles")
                    page.wait_for_load_state("domcontentloaded", timeout=60000)
                    time.sleep(2)
                    html = page.content()
                    docs = []
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
                    for doc in docs:
                        if not GRANT_TYPES.search(doc["type"]) or EXCLUDE.search(doc["type"]):
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
                                    texts.append(text)
                        except Exception:
                            continue
                    page.close()
                except Exception as exc:
                    page.close()
                    state["done"][key] = {"status": "flow_error", "error": str(exc)[:80]}
                    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
                    continue
                full = "\n".join(texts)
                conds = parse_conditions(full)
                row = {"case_key": key, "n_conditions": len(conds),
                       "n_precommencement": sum(1 for c in conds if PRE_COMM_RE.search(c))}
                for fam, pat in FAMILY_RE.items():
                    row[f"n_{fam}"] = sum(1 for c in conds if re.search(pat, c, re.I))
                row["chars"] = len(full)
                row.update({"authority": r["PlanningAuthority"], "units": r["NumResidentialUnits"],
                            "grant_year": r["grant_dt"].year})
                state["done"][key] = {"status": "ok", "n_conditions": len(conds)}
                STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
                done_rows.append(key)
                pd.DataFrame([{**row, "case_key": key}]).to_csv(corpus, mode="a",
                                                                 header=not corpus.exists(), index=False)
                print(key, "conditions:", len(conds), flush=True)
                time.sleep(0.5)
        finally:
            browser.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
