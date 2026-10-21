"""Runner: BER compact extraction + field audit verdict.

Streams the 1.56GB BERPublicsearch.txt once, keeping development-relevant
rows (multi-dwelling MPRN, new-dwelling purposes, final ratings, year
>=2014) into a compact parquet. Also reports the field audit: which
geographic fields survived anonymisation.
"""
from __future__ import annotations

import json
import os
import sys
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

ZIP_PATH = Path(os.environ.get("BER_ZIP_PATH", "BERPublicSearch.zip"))
OUT_PATH = settings.RAW_DIR / "ber" / "ber_compact.parquet"
KEEP_COLUMNS = ["CountyName", "DwellingTypeDescr", "Year_of_Construction", "TypeofRating",
                "PurposeOfRating", "DateOfAssessment", "MultiDwellingMPRN", "GroundFloorArea(sq m)",
                "EnergyRating", "BerRating", "NoStoreys"]

if __name__ == "__main__":
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    stats = {"rows": 0, "kept": 0, "mprn_filled": 0, "sa_filled": 0,
             "new_dwelling_purpose": 0, "final_or_provisional": 0}
    rows = []
    with zipfile.ZipFile(ZIP_PATH) as archive:
        with archive.open("BERPublicsearch.txt") as handle:
            header = handle.readline().decode("utf-8", errors="ignore").rstrip("\n").split("\t")
            index = {name: i for i, name in enumerate(header)}
            for line in handle:
                parts = line.decode("utf-8", errors="ignore").rstrip("\n").split("\t")
                if len(parts) < 190:
                    continue
                stats["rows"] += 1
                year = parts[index["Year_of_Construction"]].strip()
                rating_type = parts[index["TypeofRating"]].strip()
                purpose = parts[index["PurposeOfRating"]].strip()
                mprn = parts[index["MultiDwellingMPRN"]].strip()
                sa = parts[index["SA_Code"]].strip()
                if mprn and mprn.upper() != "NO":
                    stats["mprn_filled"] += 1
                if sa:
                    stats["sa_filled"] += 1
                new_purpose = "new dwelling" in purpose.lower()
                if new_purpose:
                    stats["new_dwelling_purpose"] += 1
                finalish = rating_type in ("Final", "Provisional")
                if finalish:
                    stats["final_or_provisional"] += 1
                try:
                    year_int = int(year)
                except ValueError:
                    year_int = 0
                keep = (new_purpose or (finalish and year_int >= 2014) or (mprn and mprn.upper() != "NO" and year_int >= 2014))
                if not keep:
                    continue
                row = {}
                for column in KEEP_COLUMNS:
                    row[column] = parts[index[column]].strip()
                rows.append(row)
                stats["kept"] += 1
                if len(rows) >= 200000:
                    chunk = pd.DataFrame(rows)
                    chunk.to_csv(OUT_PATH.with_suffix(".csv"), index=False, mode="a", header=not OUT_PATH.with_suffix(".csv").exists())
                    rows = []
    if rows:
        chunk = pd.DataFrame(rows)
        chunk.to_csv(OUT_PATH.with_suffix(".csv"), index=False, mode="a", header=not OUT_PATH.with_suffix(".csv").exists())
    (settings.RAW_DIR / "ber" / "ber_compact_report.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(json.dumps(stats, indent=2))
