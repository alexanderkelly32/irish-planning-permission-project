#!/usr/bin/env python3
"""Clean the 2026 register pull and report data quality."""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "00_base" / "source_data" / "register_2026.jsonl"
OUT = ROOT / "00_base" / "source_data" / "register_2026.parquet"

sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from build_dublin_submission_model import decision_to_submission_target, strip_text_leakage_clues  # noqa: E402
from build_raw_planning_benchmarks import residential_bucket  # noqa: E402

rows = [json.loads(line) for line in SRC.read_text(encoding="utf-8").splitlines() if line.strip()]
df = pd.DataFrame(rows)
for col in ("ReceivedDate", "DecisionDate", "WithdrawnDate", "DecisionDueDate", "GrantDate", "AppealDecisionDate", "AppealSubmittedDate", "FIRequestDate", "FIRecDate", "ExpiryDate"):
    if col in df.columns:
        df[col] = pd.to_datetime(pd.to_numeric(df[col], errors="coerce"), unit="ms", utc=True, errors="coerce")
df.to_parquet(OUT, index=False)
print("raw rows:", len(df))
print("received range:", df["ReceivedDate"].min(), "->", df["ReceivedDate"].max())
print("monthly received:")
print(df.groupby(df["ReceivedDate"].dt.to_period("M")).size().tail(12).to_string())

units = pd.to_numeric(df["NumResidentialUnits"], errors="coerce")
terms = r"\b(?:apartment|apartments|dwelling|dwellings|house|houses|residential|home|extension|retention|change of use|one-off|one off)\b"
residential = units.gt(0) | df["OneOffHouse"].fillna("").astype(str).str.strip().str.lower().isin({"y", "yes", "one", "single house"})
residential |= df["DevelopmentDescription"].fillna("").astype(str).str.contains(terms, case=False, regex=True)
df["is_residential"] = residential
print("residential share:", round(float(residential.mean()), 4), "->", int(residential.sum()), "rows")

decided = df["Decision"].fillna("").astype(str).str.upper().str.contains(r"REFUS|GRANT|CONDITIONAL|UNCONDITIONAL", regex=True)
print("decided share:", round(float(decided.mean()), 4))
mapped = df["Decision"].map(decision_to_submission_target)
df["target_refused"] = mapped.map(lambda v: v[0] if isinstance(v, tuple) else v)
df["target_mapping_status"] = mapped.map(lambda v: v[1] if isinstance(v, tuple) else "")
res = df[residential & decided]
print("residential+decided:", len(res), "refusal rate:", round(float(res["target_refused"].mean()), 4))
print("decided refusal rate (all types):", round(float(df.loc[decided, "target_refused"].mean()), 4))
print("decision value counts (2026):")
print(df["Decision"].value_counts(dropna=False).head(10).to_string())
