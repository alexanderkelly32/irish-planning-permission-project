"""Gate 1: parser precision audit (self-audit vs description text + pack).

Cross-checks parsed design fields against the description text for the
1,676 design versions: units-in-text, storeys-in-text, apartment/house
flags, creche/open-space/demolition/PartV/parking/phasing flags.
Saves the audit pack with audit columns for human verification.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "optimiser"


def main() -> None:
    frame = pd.read_csv(OUT / "design_versions.csv")
    d = frame["DevelopmentDescription"].fillna("").str.lower()
    checks = {}
    units_text = d.str.extract(r"(\d{2,4})\s*(?:no\.?|residential units|dwellings|houses|units)", expand=False)
    checks["units_text_match"] = (pd.to_numeric(units_text, errors="coerce") == frame["units"]).mean()
    storeys_text = d.str.extract(r"(\d+)[ -]storey", expand=False).astype(float)
    checks["storeys_match"] = (storeys_text == frame["storeys"]).mean()
    checks["apartment_flag_match"] = (d.str.contains("apartment|duplex", regex=True).astype(int) == frame["apartment"]).mean()
    checks["house_flag_match"] = (d.str.contains(r"house|dwelling|terrace|semi", regex=True).astype(int) == frame["house"]).mean()
    for flag, pat in [("creche", r"creche"), ("open_space", r"open space|amenity|play area"),
                      ("demolition", r"demolition"), ("part_v", r"part v|social housing|affordable"),
                      ("parking_mention", r"parking|car park"), ("phasing", r"phase"),
                      ("access_mention", r"access|junction")]:
        checks[f"{flag}_flag_match"] = (d.str.contains(pat, regex=True).astype(int) == frame[flag]).mean()
    report = {"n_versions": int(len(frame)),
              "checks": {k: round(float(v), 3) for k, v in checks.items()},
              "note": "flags are presence-parsers by construction; the informative checks are units-in-text and storeys agreement"}
    audit = pd.read_csv(OUT / "audit_pack_pairs.csv")
    audit["units_text_a"] = audit["desc_a"].fillna("").str.lower().str.extract(r"(\d{2,4})\s*(?:no\.?|residential units|dwellings|houses|units)", expand=False)
    audit["units_text_b"] = audit["desc_b"].fillna("").str.lower().str.extract(r"(\d{2,4})\s*(?:no\.?|residential units|dwellings|houses|units)", expand=False)
    audit.to_csv(OUT / "audit_pack_pairs.csv", index=False)
    (OUT / "gate1_audit_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
