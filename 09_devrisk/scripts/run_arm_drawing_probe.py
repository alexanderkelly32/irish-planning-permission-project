"""Probe: drawing pages in the ARM decision PDFs (last free map source)."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, r"09_devrisk")
sys.path.insert(0, r".vendor")

import fitz  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

BASE = settings.ROOT / "02_development" / "source_data"
DIRS = [BASE / "granted_arm_decisions", BASE / "refused_arm_decisions"]
register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
app_to_case = dict(zip(register["ApplicationNumber"].astype(str), register["case_key"].astype(str)))
multi = pd.read_csv(settings.SILVER_DIR / "phase_master.csv")
multi_devs = set(multi["development_id"].astype(str))

report = {"pdfs": 0, "multi_phase_pdfs": 0, "drawing_pages": 0, "pages_detail": []}
for directory in DIRS:
    for pdf in directory.rglob("*.pdf"):
        report["pdfs"] += 1
        match = re.match(r"^(\d+)_(?:decision|arm)", pdf.name)
        if not match:
            continue
        case_key = app_to_case.get(match.group(1))
        if case_key not in multi_devs:
            continue
        report["multi_phase_pdfs"] += 1
        try:
            with fitz.open(pdf) as doc:
                for page_index, page in enumerate(doc):
                    if page_index >= 20:
                        break
                    if len(page.get_drawings()) >= 50:
                        report["drawing_pages"] += 1
                        report["pages_detail"].append({"pdf": pdf.name, "page": page_index})
        except Exception:
            continue

(settings.SILVER_DIR / "arm_drawing_probe.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
