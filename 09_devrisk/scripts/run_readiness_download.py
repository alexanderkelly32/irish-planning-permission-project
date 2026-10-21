"""Runner: post-grant readiness document download + text (Wicklow-first).

For ledger-backed schemes: in-session iDocs flow, download all
readiness-relevant documents (correspondence, bonds/financial, compliance,
FI-received, submissions, time extensions), extract text (native text via
pymupdf; RapidOCR fallback for image-only PDFs; djvu via dpsserv tiles).
Saves docs/{scheme}/readiness/{docid}.json {type, comment, text, chars}.

Resume-safe: state.json["readiness_done"].
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
STATE = OUT / "state.json"

READINESS_TYPES = re.compile(
    r"correspondence|compliance|bond|condition|submission|f\.?i\.|further information|"
    r"time extension|taking in charge|naming|name plaque|revised", re.I)
EXCLUDE_TYPES = re.compile(r"drawing|map|site notice|newspaper|layout|plan\b|elevation|section|"
                           r"application form|cover letter|fee receipt|acknowledgement / validation|"
                           r"land owner|notification|decision|EIAR|NIS|assessment report|traffic", re.I)


def target_docs(doc: dict) -> bool:
    blob = doc["type"] + " " + doc["comment"]
    return bool(READINESS_TYPES.search(blob)) and not bool(EXCLUDE_TYPES.search(doc["type"]))


def text_from_pdf_bytes(body: bytes, out_path: Path) -> str:
    out_path.write_bytes(body)
    import fitz
    doc = fitz.open(out_path)
    lines = [l for pg in doc for l in pg.get_text().splitlines() if l.strip()]
    substantive = [l for l in lines
                   if not re.search(r"inspection purposes only|planning department|copyright", l, re.I)]
    text = " ".join(substantive)
    if len(text.strip()) > 200:
        return text
    from rapidocr_onnxruntime import RapidOCR
    engine = RapidOCR()
    parts = []
    for i, pg in enumerate(doc):
        if i >= 6:
            break
        pix = pg.get_pixmap(dpi=180)
        result, _ = engine(pix.tobytes("png"))
        if result:
            parts.append(" ".join(line[1] for line in result))
    return "\n".join(parts)


def main() -> None:
    only_wicklow = "--wicklow" in sys.argv
    state = json.loads(STATE.read_text(encoding="utf-8"))
    rd = state.setdefault("readiness_done", {})
    ledgers = sorted(OUT.glob("ledger_*.json"))
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        try:
            for ledger_path in ledgers:
                key = ledger_path.name[len("ledger_"):-5]
                if only_wicklow and not key.startswith("Wicklow"):
                    continue
                if key in rd:
                    continue
                data = json.loads(ledger_path.read_text(encoding="utf-8"))
                host, app_id = data["host"], data["app_id"]
                scheme_dir = DOCS / key[:80] / "readiness"
                scheme_dir.mkdir(parents=True, exist_ok=True)
                targets = [d for d in data["docs"] if target_docs(d)]
                page = browser.new_page()
                done = 0
                try:
                    page.goto(f"https://{host}/idocswebDPSS/copyright.aspx?catalog=planning&id={app_id}", timeout=120000)
                    page.check("#chkAgree")
                    time.sleep(1)
                    page.click("#btnViewFiles")
                    page.wait_for_load_state("domcontentloaded", timeout=60000)
                    time.sleep(2)
                except Exception as exc:
                    rd[key] = {"status": "error", "error": f"list: {str(exc)[:80]}"}
                    print(key, "list error", str(exc)[:80], flush=True)
                    page.close()
                    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
                    continue
                for doc in targets:
                    docid = doc["docid"]
                    out_json = scheme_dir / f"{docid}.json"
                    if out_json.exists():
                        done += 1
                        continue
                    try:
                        page.goto(f"https://{host}/idocswebDPSS/ViewFiles.aspx?docid={docid}&format=jpeg", timeout=120000)
                        src = ""
                        for _ in range(12):
                            time.sleep(1)
                            frame = page.query_selector("#frame1")
                            src = frame.get_attribute("src") if frame else ""
                            if "file=" in src:
                                break
                        mp = re.search(r"file=([^&\s]+\.pdf)", src)
                        md = re.search(r"file=([^&\s]+\.djvu)", src)
                        entry = {"docid": docid, "type": doc["type"], "comment": doc["comment"]}
                        if mp:
                            uuid = mp.group(1)
                            blob = page.context.request.get(f"https://{host}/idocswebDPSS/files/{uuid}", timeout=120000)
                            if not blob.ok:
                                entry["status"] = "download_failed"
                            else:
                                entry["text"] = text_from_pdf_bytes(blob.body(), scheme_dir / f"{docid}.pdf")
                                entry["status"] = "ok"
                                entry["chars"] = len(entry["text"])
                        elif md:
                            from rapidocr_onnxruntime import RapidOCR
                            engine = RapidOCR()
                            uuid = md.group(1)
                            parts = []
                            for pno in range(1, 30):
                                url = (f"https://{host}/DPSS/dpsserv.dll/docs/{uuid}.djvu/"
                                       f"page%3D{pno}%3Bzoom%3D50%3Bjpeg")
                                blob = page.context.request.get(url, timeout=120000)
                                if not blob.ok or len(blob.body()) < 5000:
                                    break
                                result, _ = engine(blob.body())
                                if result:
                                    parts.append(" ".join(line[1] for line in result))
                            entry["text"] = "\n".join(parts)
                            entry["status"] = "ok"
                            entry["chars"] = len(entry["text"])
                        else:
                            entry["status"] = "no_frame_src"
                        out_json.write_text(json.dumps(entry, indent=2), encoding="utf-8")
                        done += 1
                    except Exception as exc:
                        out_json.write_text(json.dumps(
                            {"docid": docid, "status": "error", "error": str(exc)[:80]}, indent=2), encoding="utf-8")
                page.close()
                rd[key] = {"status": "ok", "n_targets": len(targets), "n_done": done}
                print(key, "targets:", len(targets), "processed:", done, flush=True)
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
