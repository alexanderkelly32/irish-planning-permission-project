#!/usr/bin/env python3
"""Build display metadata for the frozen comparable-case reference pack.

The v4-full scoring path uses `model_v4/comparable_reference.joblib`, whose
bucket matrices are ordered by (received_date_dt, case_key) within each
application bucket. That artifact is frozen and is NOT modified here.

This script rebuilds the same row ordering from the same source data and
attaches display metadata (application reference, dates, units, decision,
description, and inspector refusal rationale where extracted) so the product
can show the 20 nearest comparables by name instead of as anonymous rows.

The output, `model_v4/comparable_metadata.joblib`, is display-only: it is not
read by the scoring path and cannot change any model prediction.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current" / "model_v4" / "comparable_metadata.joblib"
RECENT_OUT = ROOT / "05_policy" / "current" / "model_v4" / "recent_precedents_reference.joblib"
FROZEN = ROOT / "05_policy" / "current" / "model_v4" / "comparable_reference.joblib"
REFUSAL_MASTER = ROOT / "03_refusal" / "current" / "refusal_reasons_cases_master.csv"
GE10_REFUSALS = ROOT / "03_refusal" / "current" / "greater_than_10_units_with_refusal_reasons_master.csv"
LLM_NEW = ROOT / "03_refusal" / "current" / "refusal_reasons_cases_llm_new.csv"
RECENT_YEARS = 5

sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from build_8020_regime_experiment import CUTOFF, build_data  # noqa: E402
from build_dublin_submission_model import normalize_application_number  # noqa: E402


def _norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def _load_refusal_rationale() -> pd.DataFrame:
    frames = []
    if REFUSAL_MASTER.exists():
        canonical = pd.read_csv(REFUSAL_MASTER, low_memory=False)
        canonical["_join"] = canonical["council"].map(_norm) + "__" + canonical["application_number"].map(_norm)
        canonical = canonical.dropna(subset=["_join"]).drop_duplicates("_join", keep="first")
        frames.append(canonical[["_join", "reason_count", "reasons_joined", "case_top_primary_tag"]])
    if GE10_REFUSALS.exists():
        ge10 = pd.read_csv(GE10_REFUSALS, low_memory=False)
        ge10["_join"] = ge10["PlanningAuthority"].map(_norm) + "__" + ge10["ApplicationNumber"].map(_norm)
        ge10 = ge10.dropna(subset=["_join"]).drop_duplicates("_join", keep="first")
        ge10 = ge10.rename(columns={"reason_count": "reason_count", "reasons_joined": "reasons_joined", "case_top_primary_tag": "case_top_primary_tag"})
        ge10 = ge10[["_join", "reason_count", "reasons_joined", "case_top_primary_tag"]]
        frames.append(ge10)
    if LLM_NEW.exists():
        llm_new = pd.read_csv(LLM_NEW, low_memory=False)
        llm_new["_join"] = llm_new["council"].map(_norm) + "__" + llm_new["application_number"].map(_norm)
        llm_new = llm_new.dropna(subset=["_join"]).drop_duplicates("_join", keep="first")
        llm_new = llm_new[["_join", "reason_count", "reasons_joined", "case_top_primary_tag"]]
        frames.append(llm_new)
    if not frames:
        return pd.DataFrame(columns=["_join", "reason_count", "reasons_joined", "case_top_primary_tag"])
    merged = pd.concat(frames, ignore_index=True)
    merged["reason_count"] = pd.to_numeric(merged["reason_count"], errors="coerce").fillna(0)
    merged = merged.sort_values("reason_count", ascending=False).drop_duplicates("_join", keep="first")
    return merged[["_join", "reason_count", "reasons_joined", "case_top_primary_tag"]]


def main() -> None:
    frozen = joblib.load(FROZEN)
    data, train, _test, _y = build_data()
    reference = train.sort_values(["received_date_dt", "case_key"]).copy()
    rationale = _load_refusal_rationale()

    units_map = dict(zip(reference["case_key"], reference["units"]))
    reference["_units"] = reference["case_key"].map(units_map)

    reference["_join"] = reference["PlanningAuthority"].map(_norm) + "__" + reference["ApplicationNumber"].map(normalize_application_number).map(_norm)
    reference = reference.merge(rationale, on="_join", how="left")

    buckets: dict[str, dict] = {}
    for bucket, frame in reference.groupby("application_bucket", sort=False):
        if len(frame) < 100:
            continue
        frozen_bucket = frozen["buckets"].get(str(bucket))
        if frozen_bucket is None:
            raise SystemExit(f"bucket {bucket!r} missing from frozen comparable reference")
        if len(frame) != frozen_bucket["matrix"].shape[0]:
            raise SystemExit(f"bucket {bucket!r} row count {len(frame)} != frozen {frozen_bucket['matrix'].shape[0]}")
        if not np.array_equal(frame["PlanningAuthority"].fillna("").astype(str).to_numpy(), frozen_bucket["authorities"]):
            raise SystemExit(f"bucket {bucket!r} authority order diverges from frozen reference - alignment broken")
        if not np.array_equal(frame["target_refused"].to_numpy(dtype=int), frozen_bucket["targets"]):
            raise SystemExit(f"bucket {bucket!r} target order diverges from frozen reference - alignment broken")

        received = frame["received_date_dt"].dt.tz_localize(None) if frame["received_date_dt"].dt.tz is not None else frame["received_date_dt"]
        decision = pd.to_datetime(frame["DecisionDate"], errors="coerce")
        buckets[str(bucket)] = {
            "case_key": frame["case_key"].astype(str).to_numpy(),
            "application_number": frame["ApplicationNumber"].astype(str).to_numpy(),
            "authority": frame["PlanningAuthority"].fillna("").astype(str).to_numpy(),
            "received_date": received.dt.strftime("%Y-%m-%d").to_numpy(),
            "received_year": received.dt.year.to_numpy(),
            "decision_date": decision.dt.strftime("%Y-%m-%d").to_numpy(),
            "decision": frame["Decision"].fillna("").astype(str).to_numpy(),
            "target": frame["target_refused"].to_numpy(dtype=int),
            "units": pd.to_numeric(frame["_units"], errors="coerce").to_numpy(),
            "description": frame["description_stripped"].fillna("").astype(str).to_numpy(),
            "reason_count": pd.to_numeric(frame["reason_count"], errors="coerce").fillna(0).astype(int).to_numpy(),
            "reasons_joined": frame["reasons_joined"].fillna("").astype(str).to_numpy(),
            "top_primary_tag": frame["case_top_primary_tag"].fillna("").astype(str).to_numpy(),
        }

    payload = {
        "kind": "comparable_display_metadata",
        "frozen_reference": str(FROZEN),
        "training_cutoff_exclusive": str(CUTOFF),
        "row_order": "received_date_dt, case_key (identical to comparable_reference.joblib)",
        "buckets": buckets,
        "note": "Display-only. Not read by the scoring path. Rationales come from the retagged refusal-reasons master (post-submission documents of historical cases).",
    }
    joblib.dump(payload, OUT)
    print("saved comparable_metadata:", OUT)
    for bucket, frame in buckets.items():
        print(f"  {bucket}: {len(frame['case_key'])} rows, {int(frame['reason_count'].sum())} with extracted rationale")

    build_recent_pack(data, frozen["vectorizer"], rationale)
    print("saved recent_precedents_reference:", RECENT_OUT)


def build_recent_pack(data: pd.DataFrame, vectorizer, rationale: pd.DataFrame) -> None:
    """Recent 5-year-window precedent pack for the display matcher.

    Rows received since (2024 - RECENT_YEARS) so a submission year from 2024
    onwards always has a full 5-year window. Query time applies the exact
    window (submission_year - 5 <= received <= submission_year) and drops
    undecided rows. The TF-IDF matrices reuse the FROZEN comparable
    vectorizer; they are display-only and never feed the scoring path.
    """
    recent = data[pd.to_datetime(data["received_date_dt"]).dt.year >= 2024 - RECENT_YEARS].copy()
    recent["_join"] = recent["PlanningAuthority"].map(_norm) + "__" + recent["ApplicationNumber"].map(normalize_application_number).map(_norm)
    recent = recent.merge(rationale, on="_join", how="left")
    recent["_site_sqm"] = pd.to_numeric(recent["AreaofSite"], errors="coerce") * 10000.0
    recent["_units"] = pd.to_numeric(recent["units"], errors="coerce")
    received = recent["received_date_dt"].dt.tz_localize(None) if recent["received_date_dt"].dt.tz is not None else recent["received_date_dt"]
    decision = pd.to_datetime(recent["DecisionDate"], errors="coerce")
    buckets: dict[str, dict] = {}
    for bucket, frame in recent.groupby("application_bucket", sort=False):
        matrix = vectorizer.transform(frame["description_stripped"].fillna("").astype(str))
        buckets[str(bucket)] = {
            "case_key": frame["case_key"].astype(str).to_numpy(),
            "application_number": frame["ApplicationNumber"].astype(str).to_numpy(),
            "authority": frame["PlanningAuthority"].fillna("").astype(str).to_numpy(),
            "received_date": received.loc[frame.index].dt.strftime("%Y-%m-%d").to_numpy(),
            "received_year": received.loc[frame.index].dt.year.to_numpy(),
            "decision_date": decision.loc[frame.index].dt.strftime("%Y-%m-%d").to_numpy(),
            "decision": frame["Decision"].fillna("").astype(str).to_numpy(),
            "target": frame["target_refused"].to_numpy(),
            "units": frame["_units"].to_numpy(),
            "site_sqm": frame["_site_sqm"].to_numpy(),
            "description": frame["description_stripped"].fillna("").astype(str).to_numpy(),
            "reason_count": pd.to_numeric(frame["reason_count"], errors="coerce").fillna(0).astype(int).to_numpy(),
            "reasons_joined": frame["reasons_joined"].fillna("").astype(str).to_numpy(),
            "top_primary_tag": frame["case_top_primary_tag"].fillna("").astype(str).to_numpy(),
            "matrix": matrix,
        }
    payload = {
        "kind": "recent_precedents_reference",
        "window_years": RECENT_YEARS,
        "anchor_year": 2024,
        "vectorizer_frozen": True,
        "rationale_sources": [str(REFUSAL_MASTER), str(GE10_REFUSALS)],
        "buckets": buckets,
        "note": "Display-only matcher reference. Not read by the scoring path. Undecided rows are excluded at query time.",
    }
    joblib.dump(payload, RECENT_OUT)
    for bucket, frame in buckets.items():
        print(f"  recent {bucket}: {len(frame['case_key'])} rows, {int(frame['reason_count'].sum())} with extracted rationale")


if __name__ == "__main__":
    main()
