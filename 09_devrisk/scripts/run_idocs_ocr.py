"""Phase 3: download grant/conditions PDFs in-session + extract text.

Flow per scheme: copyright -> chkAgree -> View Files -> ViewFiles.aspx?docid=X
-> read iframe src (ViewPdf.aspx?file=UUID.pdf) -> download files/UUID.pdf via
the session context. Text via pymupdf; RapidOCR fallback for image-only pages.
Outputs: docs/{scheme}/{docid}.pdf + {scheme}_text.json.
Resume-safe via state.json["pdf_done"].
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from patchright.sync_api import sync_playwright  # noqa: E402

from devrisk import settings  # noqa: E402

OUT = settings.SILVER_DIR / "idocs"
DOCS = OUT / "docs"
DOCS.mkdir(parents=True, exist_ok=True)
STATE = OUT / "state.json"

GRANT_TYPES = re.compile(r"^(final grant|schedule of conditions|decision order|order granting|grant of permission|chief executives order|planners report)", re.I)
EXCLUDE_TYPES = re.compile(r"post decision|notification of decision|correspondence", re.I)


def target_docs(doc: dict) -> bool:
    t = doc["type"].strip()
    return bool(GRANT_TYPES.search(t)) and not bool(EXCLUDE_TYPES.search(t))


def ocr_pdf_if_empty(pdf_path: Path) -> str:
    import fitz
    doc = fitz.open(pdf_path)
    lines = [l for pg in doc for l in pg.get_text().splitlines() if l.strip()]
    substantive = [l for l in lines
                   if not re.search(r"inspection purposes only|planning department|copyright", l, re.I)]
    text = " ".join(substantive)
    if len(text.strip()) > 300:
        return text
    from rapidocr_onnxruntime import RapidOCR
    engine = RapidOCR()
    parts = []
    for i, pg in enumerate(doc):
        if i >= 15:
            break
        pix = pg.get_pixmap(dpi=200)
        result, _ = engine(pix.tobytes("png"))
        if result:
            parts.append(" ".join(line[1] for line in result))
        print(f"    OCR page {i + 1}/{min(len(doc), 15)}", flush=True)
    return "\n".join(parts)


def main() -> None:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    pdf_done = state.setdefault("pdf_done", {})
    ledgers = sorted(OUT.glob("ledger_*.json"))
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        try:
            for ledger_path in ledgers:
                key = ledger_path.name[len("ledger_"):-5]
                prev = pdf_done.get(key, {})
                if key in pdf_done and prev.get("chars", 0) >= 3000:
                    continue
                data = json.loads(ledger_path.read_text(encoding="utf-8"))
                host, app_id = data["host"], data["app_id"]
                scheme_dir = DOCS / key[:80]
                scheme_dir.mkdir(parents=True, exist_ok=True)
                page = browser.new_page()
                texts = {}
                try:
                    page.goto(f"https://{host}/idocswebDPSS/copyright.aspx?catalog=planning&id={app_id}", timeout=120000)
                    page.check("#chkAgree")
                    time.sleep(2)
                    page.click("#btnViewFiles")
                    page.wait_for_load_state("networkidle", timeout=60000)
                except Exception as exc:
                    pdf_done[key] = {"status": "error", "error": f"list step: {str(exc)[:80]}"}
                    print(key, "-> list error", str(exc)[:80], flush=True)
                    page.close()
                    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
                    continue
                for doc in data["docs"]:
                    if not target_docs(doc):
                        continue
                    docid = doc["docid"]
                    try:
                        page.goto(f"https://{host}/idocswebDPSS/ViewFiles.aspx?docid={docid}&format=jpeg", timeout=120000)
                        time.sleep(5)
                        page.wait_for_load_state("networkidle", timeout=60000)
                        frame = page.query_selector("#frame1")
                        src = frame.get_attribute("src") if frame else ""
                        mp = re.search(r"file=([^&\s]+\.pdf)", src)
                        md = re.search(r"file=([^&\s]+\.djvu)", src)
                        if mp:
                            uuid = mp.group(1)
                            blob = page.context.request.get(f"https://{host}/idocswebDPSS/files/{uuid}", timeout=120000)
                            if not blob.ok:
                                texts[f"{docid}_{doc['type']}"] = {"status": "download_failed"}
                                continue
                            pdf_path = scheme_dir / f"{docid}.pdf"
                            pdf_path.write_bytes(blob.body())
                            text = ocr_pdf_if_empty(pdf_path)
                            texts[f"{docid}_{doc['type']}"] = {"status": "ok", "chars": len(text), "text": text}
                        elif md:
                            from rapidocr_onnxruntime import RapidOCR
                            engine = RapidOCR()
                            uuid = md.group(1)
                            parts = []
                            for page_no in range(1, 40):
                                url = (f"https://{host}/DPSS/dpsserv.dll/docs/{uuid}.djvu/"
                                       f"page%3D{page_no}%3Bzoom%3D50%3Bjpeg")
                                blob = page.context.request.get(url, timeout=120000)
                                if not blob.ok or len(blob.body()) < 5000:
                                    break
                                result, _ = engine(blob.body())
                                if result:
                                    parts.append(" ".join(line[1] for line in result))
                                print(f"    djvu page {page_no}", flush=True)
                            text = "\n".join(parts)
                            texts[f"{docid}_{doc['type']}"] = {"status": "ok", "chars": len(text), "text": text}
                        else:
                            texts[f"{docid}_{doc['type']}"] = {"status": "no_pdf_src"}
                    except Exception as exc:
                        texts[f"{docid}_{doc['type']}"] = {"status": "error", "error": str(exc)[:80]}
                page.close()
                (scheme_dir / f"{key}_text.json").write_text(json.dumps(texts, indent=2), encoding="utf-8")
                n_ok = sum(1 for v in texts.values() if v.get("status") == "ok")
                chars = sum(v.get("chars", 0) for v in texts.values())
                pdf_done[key] = {"status": "ok", "n_docs_target": len([d for d in data["docs"] if target_docs(d)]),
                                 "n_pdfs": n_ok, "chars": chars}
                print(key, "-> pdfs:", n_ok, "chars:", chars, flush=True)
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
