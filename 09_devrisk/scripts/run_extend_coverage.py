"""Runner: extend linkage coverage to EVERY granted GE10 scheme in the register.

1. All-granted-GE10 cohort: GrantDate where present, else DecisionDate for
   granted/conditional decisions (535 rows recovered), else excluded.
2. Conservative BCMS exact-reference linking over the whole cohort.
3. PPR linking via confirmed-BCMS address sets + register fallback.

Longitudinal pain labels remain mature-only (grant 2016-2022, >=36m
follow-up); this run is about linkage coverage and submission-time
scoreability for the full granted GE10 universe.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.entity_resolution.ppr_matching import (  # noqa: E402
    build_register_fallback_sets,
    build_scheme_address_sets,
    confidence_band_ppr,
    generate_ppr_candidates,
    prepare_ppr,
    score_ppr_candidate,
)
from devrisk.entity_resolution.scoring import normalize_reference  # noqa: E402

CENSOR = "2026-09-27"


def build_all_granted_cohort(register: pd.DataFrame) -> pd.DataFrame:
    units = pd.to_numeric(register["NumResidentialUnits"], errors="coerce")
    decision = register["Decision"].fillna("").astype(str).str.upper()
    granted_flag = decision.str.contains("GRANT|CONDITION", regex=True) & ~decision.str.contains("REFUS")
    frame = register[units.ge(10) & granted_flag].copy()
    frame["grant_date_dt"] = pd.to_datetime(frame["GrantDate"], utc=True, errors="coerce")
    decision_date = pd.to_datetime(frame["DecisionDate"], utc=True, errors="coerce")
    fallback = frame["grant_date_dt"].isna() & decision_date.notna()
    frame.loc[fallback, "grant_date_dt"] = decision_date[fallback]
    frame = frame[frame["grant_date_dt"].notna()].copy()
    frame["grant_year"] = frame["grant_date_dt"].dt.year
    frame["grant_date_fallback"] = fallback.astype(int)
    return frame.reset_index(drop=True)


def _ref_variants(value: str) -> set[str]:
    """Normalised reference variants: full, slash-separated year+ref, P-prefixed,
    digit core, register year-strip.

    Handles register '161483' vs BCMS '16/483' / 'P16/483' / '483' formats.
    """
    import re

    variants = {normalize_reference(value)}
    stripped = normalize_reference(value)
    for pattern in (r"^p(\d{2})[/\-.](\d{2,})$", r"^(\d{2})[/\-.](\d{2,})$"):
        match = re.match(pattern, stripped)
        if match:
            year, rest = match.group(1), match.group(2)
            variants.add(year + rest)
            variants.add(rest)
    core = _digit_core(stripped)
    if core and len(core) >= 3:
        variants.add(core)
    # Register side: 5-6 digit numbers whose leading 2 digits are a year.
    if re.fullmatch(r"\d{5,6}", stripped):
        head = stripped[:2]
        if "14" <= head <= "26":
            variants.add(stripped[2:])
    return {variant for variant in variants if variant and len(variant) >= 3}


def conservative_bcms_links(cohort: pd.DataFrame, bcms: pd.DataFrame) -> pd.DataFrame:
    bcms_ref = bcms["planning_reference"].fillna("").astype(str)
    ref_index: dict[str, list[int]] = {}
    for idx, ref in bcms_ref.items():
        for variant in _ref_variants(ref):
            ref_index.setdefault(variant, []).append(idx)

    rows = []
    for _, application in cohort.iterrows():
        app_norm = normalize_reference(application["ApplicationNumber"])
        if not app_norm or len(app_norm) < 3:
            continue
        variants = _ref_variants(app_norm)
        candidates_idx: set[int] = set()
        for variant in variants:
            candidates_idx |= set(ref_index.get(variant, []))
        if not candidates_idx:
            continue
        app_county = _county_from_authority(application.get("PlanningAuthority"))
        for idx in candidates_idx:
            candidate = bcms.iloc[idx]
            if app_county:
                county = str(candidate.get("county") or "").lower()
                if county and county != app_county:
                    continue
            distance = None
            s_east = pd.to_numeric(pd.Series([application.get("ITMEasting")]), errors="coerce").iloc[0]
            s_north = pd.to_numeric(pd.Series([application.get("ITMNorthing")]), errors="coerce").iloc[0]
            if not pd.isna(s_east) and not pd.isna(candidate.get("itm_easting")):
                distance = float(np.hypot(candidate["itm_easting"] - s_east, candidate["itm_northing"] - s_north))
            band = "confirmed" if (distance is None or distance <= 1000.0) else "probable"
            rows.append({
                "scheme_id": str(application["case_key"]),
                "bcms_event_id": candidate["bcms_event_id"],
                "match_method": "planning_reference_variant",
                "confidence_band": band,
                "distance_metres": round(distance, 1) if distance is not None else None,
                "bcms_planning_reference": candidate["planning_reference"],
                "bcms_address": candidate["address_full"],
                "commencement_date": candidate["commencement_date_dt"],
            })
    return pd.DataFrame(rows)


def _digit_core(value: str) -> str:
    import re

    matches = re.findall(r"\d+", value or "")
    return max(matches, key=len) if matches else ""


def _county_from_authority(authority: object) -> str:
    text = str(authority or "").lower()
    for county in ("carlow", "cavan", "clare", "cork", "donegal", "dublin", "galway", "kerry",
                   "kildare", "kilkenny", "laois", "leitrim", "limerick", "longford", "louth",
                   "mayo", "meath", "monaghan", "offaly", "roscommon", "sligo", "tipperary",
                   "waterford", "westmeath", "wexford", "wicklow"):
        if county in text:
            return county
    return ""


if __name__ == "__main__":
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    cohort = build_all_granted_cohort(register)
    cohort.to_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet", index=False)
    print(f"all-granted GE10 cohort: {len(cohort)} (grant-date fallback used on {int(cohort['grant_date_fallback'].sum())} rows)", flush=True)

    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    bcms_links = conservative_bcms_links(cohort, bcms)
    bcms_links.to_csv(settings.SILVER_DIR / "bcms_links_all_granted.csv", index=False)
    bcms_schemes = int(bcms_links[bcms_links["confidence_band"] == "confirmed"]["scheme_id"].nunique())
    print(f"BCMS confirmed-link schemes: {bcms_schemes}/{len(cohort)} ({bcms_schemes / len(cohort) * 100:.1f}%)", flush=True)

    ppr = pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet")
    ppr_prepared = prepare_ppr(ppr)
    address_sets = build_scheme_address_sets(bcms, bcms_links)
    fallback_sets = build_register_fallback_sets(cohort, set(address_sets.keys()))
    address_sets = {**address_sets, **fallback_sets}
    print(f"address sets: {len(address_sets)}", flush=True)

    rows = []
    for scheme_id, address_set in address_sets.items():
        candidates = generate_ppr_candidates(address_set, ppr_prepared)
        for _, candidate in candidates.head(40).iterrows():
            features = score_ppr_candidate(address_set, candidate)
            band, reasons = confidence_band_ppr(features)
            rows.append({
                "scheme_id": scheme_id,
                "ppr_source_row_id": candidate["source_row_id"],
                "confidence_band": band,
                "reasons": "; ".join(reasons),
                **features,
            })
    ppr_links = pd.DataFrame(rows)
    ppr_links.to_csv(settings.SILVER_DIR / "ppr_links_all_granted.csv", index=False)
    ppr_schemes = int(ppr_links[ppr_links["confidence_band"] == "confirmed"]["scheme_id"].nunique())
    print(f"PPR confirmed-link schemes: {ppr_schemes}/{len(cohort)} ({ppr_schemes / len(cohort) * 100:.1f}%)", flush=True)

    summary = {
        "as_of": CENSOR,
        "ge10_register_rows": int((pd.to_numeric(register["NumResidentialUnits"], errors="coerce") >= 10).sum()),
        "all_granted_ge10": int(len(cohort)),
        "grant_date_fallback_rows": int(cohort["grant_date_fallback"].sum()),
        "by_grant_year": cohort["grant_year"].value_counts().sort_index().to_dict(),
        "bcms_confirmed_schemes": bcms_schemes,
        "bcms_coverage_pct": round(bcms_schemes / len(cohort) * 100, 1),
        "ppr_confirmed_schemes": ppr_schemes,
        "ppr_coverage_pct": round(ppr_schemes / len(cohort) * 100, 1),
        "note": "longitudinal pain labels remain mature-only (grant 2016-2022); recent grants are linked but label-pending",
    }
    out = settings.SILVER_DIR / "coverage_all_granted_summary.json"
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
