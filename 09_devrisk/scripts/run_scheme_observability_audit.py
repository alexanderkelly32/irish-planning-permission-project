"""Final observability audit: project-specific readiness traces in held data.

For the 48-scheme fast/slow residual cohort: search all locally held
material (ledgers, document texts, register) for scheme-specific traces:
- landowner identity vs applicant (consent docs)
- demolition/enabling works
- phasing dependency
- utility connection references
- contractor/builder names
- tender/procurement references
- forward-purchase/AHB references
- sales launch evidence
- amendment/replacement of an active permission
Report coverage + fast/slow separation per signal. No model fit.
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

IDOCS = settings.SILVER_DIR / "idocs"
DOCS = IDOCS / "docs"

SIGNALS = {
    "landowner_consent_doc": re.compile(r"land ?owner consent|ownership", re.I),
    "demolition": re.compile(r"demolition|demolish", re.I),
    "phasing": re.compile(r"phas(?:e|ing)", re.I),
    "utility_connection": re.compile(r"irish water|uisce|esb|electric ireland|gas networks|energia|connection|watermain", re.I),
    "contractor": re.compile(r"contractor|builders ltd|construction ltd|building ltd|contract", re.I),
    "tender_procurement": re.compile(r"tender|procurement|priced bill|boq", re.I),
    "forward_purchase_ahb": re.compile(r"forward purchase|forward fund|approved housing body|ahb|cl[uú]id|respond|tuath|oaklee|co-?operative housing", re.I),
    "sales_launch": re.compile(r"sales launch|coming soon|show ?house|launching|marketing suite|to let|for sale", re.I),
    "amendment_replacement": re.compile(r"amendment|revision of|replacement of|alteration of|substitut|split-phase|renewal", re.I),
    "fi_request": re.compile(r"f\.?i\.?|further information", re.I),
    "appeal": re.compile(r"appeal", re.I),
}


def main() -> None:
    with zipfile.ZipFile(settings.SILVER_DIR / "audit_packs" / "PACK_24_residual_forensics.zip") as z:
        cohort = pd.read_csv(z.open("residual_forensics_cohort.csv"))
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                               columns=["case_key", "ApplicantForename", "ApplicantSurname",
                                        "DevelopmentDescription", "NumResidentialUnits"])
    register["applicant"] = (register["ApplicantForename"].fillna("") + " " +
                             register["ApplicantSurname"].fillna("")).str.strip()

    ledger_texts = {}
    for lp in IDOCS.glob("ledger_*.json"):
        d = json.loads(lp.read_text(encoding="utf-8"))
        key = d.get("case_key") or lp.stem[len("ledger_"):].replace("_", " ")
        types = " | ".join(f"{x['type']} {x['comment']}" for x in d.get("docs", []))
        ledger_texts[key] = types

    doc_texts = {}
    for scheme_dir in DOCS.glob("*/readiness"):
        ck = scheme_dir.parent.name
        blob = []
        for dj in scheme_dir.glob("*.json"):
            try:
                d = json.loads(dj.read_text(encoding="utf-8"))
            except Exception:
                continue
            if d.get("status") == "ok" and d.get("text"):
                blob.append(d["text"])
        if blob:
            doc_texts[ck] = " ".join(blob)

    rows = []
    for _, row in cohort.iterrows():
        key = row["case_key"]
        desc = str(register.loc[register["case_key"] == key, "DevelopmentDescription"].iloc[0]) if (register["case_key"] == key).any() else ""
        applicant = str(register.loc[register["case_key"] == key, "applicant"].iloc[0]) if (register["case_key"] == key).any() else ""
        ledger = ledger_texts.get(key, "") + " " + ledger_texts.get(key.replace(" ", "_"), "")
        texts = doc_texts.get(key, "") + " " + doc_texts.get(key.replace(" ", "_"), "")
        blob = desc + " | " + ledger + " | " + texts[:40000]
        entry = {"case_key": key, "authority": row["authority"], "residual_group": row["residual_group"],
                 "units": row["units"], "actual_days": row["actual_days"],
                 "n_ledger_chars": len(ledger), "n_text_chars": len(texts)}
        for name, pattern in SIGNALS.items():
            entry[name] = int(bool(pattern.search(blob)))
        landowner_m = re.search(r"land ?owner consent[^\n|]{0,60}([A-Z][A-Za-z' -]{4,40})", ledger, re.I)
        entry["landowner_name_found"] = 1 if landowner_m else 0
        entry["landowner_differs_applicant"] = int(bool(
            landowner_m is not None and applicant and
            landowner_m.group(1).strip().lower() not in applicant.lower() and
            applicant.lower() not in landowner_m.group(1).strip().lower()))
        rows.append(entry)
    frame = pd.DataFrame(rows)
    frame.to_csv(IDOCS / "observability_audit.csv", index=False)

    fast = frame[frame["residual_group"].astype(str).str.contains("fast", case=False, na=False)]
    slow = frame[frame["residual_group"].astype(str).str.contains("slow", case=False, na=False)]
    report = {"n_fast": int(len(fast)), "n_slow": int(len(slow)), "signals": {}}
    for name in SIGNALS:
        cov = frame[name].mean()
        f_rate = fast[name].mean() if len(fast) else float("nan")
        s_rate = slow[name].mean() if len(slow) else float("nan")
        report["signals"][name] = {
            "coverage": round(float(cov), 3),
            "fast_rate": round(float(f_rate), 3),
            "slow_rate": round(float(s_rate), 3),
            "delta": round(float(s_rate - f_rate), 3),
        }
    report["signals"]["landowner_name_found"] = {
        "coverage": round(float(frame["landowner_name_found"].mean()), 3),
        "fast_rate": round(float(fast["landowner_name_found"].mean()), 3) if len(fast) else None,
        "slow_rate": round(float(slow["landowner_name_found"].mean()), 3) if len(slow) else None,
    }
    report["signals"]["landowner_differs_applicant"] = {
        "coverage": round(float(frame["landowner_differs_applicant"].mean()), 3),
        "fast_rate": round(float(fast["landowner_differs_applicant"].mean()), 3) if len(fast) else None,
        "slow_rate": round(float(slow["landowner_differs_applicant"].mean()), 3) if len(slow) else None,
    }
    out = IDOCS / "observability_audit_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
