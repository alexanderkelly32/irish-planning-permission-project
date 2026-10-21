"""Runner: BER gate test - dev clusters + county-year corroboration.

1. MPRN clusters: group kept rows by MultiDwellingMPRN; match to pool
   schemes by county + cluster size vs units + year window.
2. County-year completion waves: new-dwelling-purpose assessment dates
   per county+construction year; corroborate scheme CCC dates.
Gate: share of schemes whose CCC is corroborated within 90 days.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

if __name__ == "__main__":
    frame = pd.read_csv(settings.RAW_DIR / "ber" / "ber_compact.csv", low_memory=False, dtype=str)
    frame["DateOfAssessment"] = pd.to_datetime(frame["DateOfAssessment"], utc=True, errors="coerce")
    frame["year"] = pd.to_numeric(frame["Year_of_Construction"], errors="coerce")
    frame["county"] = frame["CountyName"].str.strip().str.lower()
    frame["county_norm"] = frame["county"].str.replace(r"^co\.?\s*", "", regex=True).str.replace(r"\s*\d+$", "", regex=True)
    report = {"rows": int(len(frame))}

    # ---- MPRN clusters ----
    mprn = frame[frame["MultiDwellingMPRN"].str.upper().ne("NO") & frame["MultiDwellingMPRN"].ne("")].copy()
    clusters = mprn.groupby("MultiDwellingMPRN").agg(
        county=("county_norm", "first"),
        n_dwellings=("MultiDwellingMPRN", "size"),
        first_assessment=("DateOfAssessment", "min"),
        last_assessment=("DateOfAssessment", "max"),
        median_year=("year", "median"),
    ).reset_index()
    report["mprn_clusters"] = int(len(clusters))

    completion = pd.read_csv(settings.SILVER_DIR / "completion_targets.csv")
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = register[["case_key", "PlanningAuthority", "NumResidentialUnits"]].drop_duplicates("case_key")
    scheme = completion.merge(labels[["case_key", "activation_days"]], left_on="scheme_id", right_on="case_key", how="left").drop(columns=["case_key"])
    scheme = scheme.merge(reg, left_on="scheme_id", right_on="case_key", how="left").drop(columns=["case_key"])
    scheme["county"] = scheme["PlanningAuthority"].astype(str).str.lower().str.extract(
        r"(carlow|cavan|clare|cork|donegal|dublin|galway|kerry|kildare|kilkenny|laois|leitrim|limerick|longford|louth|mayo|meath|monaghan|offaly|roscommon|sligo|tipperary|waterford|westmeath|wexford|wicklow)")[0]
    scheme["ccc_abs"] = pd.to_datetime(scheme["commencement"], utc=True, errors="coerce") + pd.to_timedelta(scheme["t_first_ccc"], unit="D")
    scheme["units"] = pd.to_numeric(scheme["NumResidentialUnits"], errors="coerce")

    matched_schemes = 0
    corroborated = 0
    for _, s in scheme.iterrows():
        if pd.isna(s["ccc_abs"]):
            continue
        candidates = clusters[clusters["county"] == s["county"]]
        if pd.notna(s["units"]):
            candidates = candidates[candidates["n_dwellings"].between(s["units"] * 0.4, s["units"] * 2.5)]
        if len(candidates) == 0:
            continue
        matched_schemes += 1
        best = candidates.iloc[(candidates["first_assessment"] - s["ccc_abs"]).abs().argsort()[:1]]
        gap = abs((best["first_assessment"].iloc[0] - s["ccc_abs"]).days)
        if gap <= 90:
            corroborated += 1

    report["mprn_corroboration"] = {
        "schemes_matched": matched_schemes,
        "schemes_corroborated_90d": corroborated,
        "share_of_pool": round(corroborated / max(1, len(scheme)), 3),
    }

    # ---- County-year waves ----
    new = frame[frame["PurposeOfRating"].str.lower().str.contains("new dwelling", na=False)].copy()
    new = new[new["year"].between(2015, 2026)]
    waves = new.groupby(["county_norm", "year"])["DateOfAssessment"].agg(
        first="min", last="max", n="size").reset_index()
    corroborated_county = 0
    for _, s in scheme.iterrows():
        if pd.isna(s["ccc_abs"]) or pd.isna(s["county"]):
            continue
        wave = waves[(waves["county_norm"] == s["county"]) & (waves["year"].between(s["ccc_abs"].year - 1, s["ccc_abs"].year + 1))]
        if len(wave) and abs((wave["first"].min() - s["ccc_abs"]).days) <= 180:
            corroborated_county += 1
    report["county_wave_corroboration"] = {
        "schemes_corroborated_180d": corroborated_county,
        "share_of_pool": round(corroborated_county / max(1, len(scheme)), 3),
    }

    out = settings.SILVER_DIR / "ber_gate_test.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
