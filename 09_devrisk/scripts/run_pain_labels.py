"""Runner: build pain_v1 labels for the full mature-granted pool.

Conservative confirmed BCMS links across the whole pool:
  - exact planning-reference match (normalised application number equals or is
    contained in the BCMS CN_Planning_Permission_Number), AND
  - county agreement where both present, AND
  - no spatial conflict (distance <= 1000 m where both sides have geo).
Timing components then come from first confirmed commencement and first
completion record. Writes pain_labels_pool.csv + prevalence summary.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.entity_resolution.scoring import normalize_reference  # noqa: E402
from devrisk.labels.pain import build_components, component_prevalence  # noqa: E402

CENSOR_DATE = "2026-09-27"


def conservative_links(register: pd.DataFrame, bcms: pd.DataFrame) -> pd.DataFrame:
    rows = []
    bcms_ref = bcms["planning_reference"].fillna("").astype(str).map(normalize_reference)
    bcms_county = bcms["county"].fillna("").astype(str).str.lower()
    bcms_east = pd.to_numeric(bcms["itm_easting"], errors="coerce")
    bcms_north = pd.to_numeric(bcms["itm_northing"], errors="coerce")
    for _, application in register.iterrows():
        app_norm = normalize_reference(application["ApplicationNumber"])
        if not app_norm or len(app_norm) < 3:
            continue
        hit = bcms_ref.apply(
            lambda ref: bool(ref) and (ref == app_norm or (len(app_norm) >= 4 and app_norm in ref))
        )
        if not hit.any():
            continue
        candidates = bcms[hit.values]
        app_county = _county_from_authority(application.get("PlanningAuthority"))
        if app_county:
            county_ok = candidates["county"].fillna("").astype(str).str.lower().isin(
                [app_county, ""]
            )
            candidates = candidates[county_ok]
        if candidates.empty:
            continue
        s_east = pd.to_numeric(pd.Series([application.get("ITMEasting")]), errors="coerce").iloc[0]
        s_north = pd.to_numeric(pd.Series([application.get("ITMNorthing")]), errors="coerce").iloc[0]
        has_geo = not pd.isna(s_east) and not pd.isna(s_north)
        for _, candidate in candidates.iterrows():
            distance = None
            if has_geo and not pd.isna(candidate["itm_easting"]) and not pd.isna(candidate["itm_northing"]):
                distance = float(np.hypot(candidate["itm_easting"] - s_east, candidate["itm_northing"] - s_north))
            conflict = distance is not None and distance > 1000.0
            band = "confirmed" if not conflict else "probable"
            rows.append({
                "scheme_id": str(application["case_key"]),
                "bcms_event_id": candidate["bcms_event_id"],
                "match_method": "exact_planning_reference",
                "confidence_band": band,
                "distance_metres": round(distance, 1) if distance is not None else None,
                "bcms_planning_reference": candidate["planning_reference"],
                "bcms_address": candidate["address_full"],
                "commencement_date": candidate["commencement_date_dt"],
            })
    return pd.DataFrame(rows)


def _county_from_authority(authority: object) -> str:
    text = str(authority or "").lower()
    for county in ("carlow", "cavan", "clare", "cork", "donegal", "dublin", "galway", "kerry",
                   "kildare", "kilkenny", "laois", "leitrim", "limerick", "longford", "louth",
                   "mayo", "meath", "monaghan", "offaly", "roscommon", "sligo", "tipperary",
                   "waterford", "westmeath", "wexford", "wicklow"):
        if county in text:
            return county
    return ""


def _enrich_fi_topics(labels: pd.DataFrame) -> pd.DataFrame:
    """Join 04_fi request-item counts (label-side enrichment, not features).

    The 04_fi case keys are snake_case ('carlow_county_council_17154'); match
    on (compact council name, application number) against scheme case keys.
    """
    import re

    fi_path = settings.ROOT / "04_fi" / "current" / "fi_request_items_long.csv"
    if not fi_path.exists():
        return labels.assign(fi_item_count=np.nan, fi_doc_count=np.nan)
    fi = pd.read_csv(fi_path, usecols=["case_key", "document_index", "item_index_within_document"], low_memory=False)

    def parse_fi_key(value: str) -> tuple[str, str] | None:
        match = re.match(r"^(.*)_(\d+)$", str(value).strip())
        if not match:
            return None
        council = re.sub(r"[^a-z]", "", match.group(1).lower())
        return council, match.group(2)

    parsed = fi["case_key"].map(parse_fi_key).dropna()
    fi = fi.loc[parsed.index]
    fi["_council"] = [pair[0] for pair in parsed]
    fi["_appno"] = [pair[1] for pair in parsed]

    def scheme_key(value: str) -> tuple[str, str]:
        council, appno = str(value).split("__", 1)
        return re.sub(r"[^a-z]", "", council.lower()), appno

    scheme_keys = labels["scheme_id"].map(scheme_key)
    labels["_council"] = [pair[0] for pair in scheme_keys]
    labels["_appno"] = [pair[1] for pair in scheme_keys]

    item_counts = fi.groupby(["_council", "_appno"]).size().rename("fi_item_count")
    doc_counts = fi.groupby(["_council", "_appno"])["document_index"].nunique().rename("fi_doc_count")
    labels = labels.merge(item_counts.to_frame(), on=["_council", "_appno"], how="left")
    labels = labels.merge(doc_counts.to_frame(), on=["_council", "_appno"], how="left")
    return labels.drop(columns=["_council", "_appno"])


if __name__ == "__main__":
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    pool = pd.read_parquet(settings.SILVER_DIR / "pilot_candidates_pool.parquet")
    cohort = register[register["case_key"].isin(pool["case_key"])].drop_duplicates("case_key").copy()
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")

    links = conservative_links(cohort, bcms)
    links.to_csv(settings.SILVER_DIR / "bcms_links_conservative_pool.csv", index=False)

    exit_labels = None
    exit_path = settings.SILVER_DIR / "exit_labels_pool.csv"
    if exit_path.exists():
        exit_labels = pd.read_csv(exit_path)

    labels = build_components(
        cohort, bcms, links, censor_date=CENSOR_DATE,
        exit_labels=exit_labels, rule_version="pain_v2",
    )
    labels = _enrich_fi_topics(labels)
    labels.to_csv(settings.SILVER_DIR / "pain_labels_pool.csv", index=False)

    summary = component_prevalence(labels)
    summary["cohort_rows"] = int(len(cohort))
    summary["confirmed_link_schemes"] = int(links["scheme_id"].nunique()) if len(links) else 0
    summary["confirmed_link_rows"] = int(len(links))
    summary["linkage_coverage"] = round(summary["confirmed_link_schemes"] / max(1, len(cohort)), 4)
    summary["label_rule_version"] = "pain_v2"
    summary["censor_date"] = CENSOR_DATE
    if exit_labels is not None:
        summary["sales_linked_schemes"] = int((exit_labels["sales_linked"] > 0).sum())
        summary["slow_exit_24m_defined"] = int(exit_labels["slow_exit_24m"].notna().sum())
        summary["below_market_25pct"] = int(exit_labels["below_market_25pct"].fillna(0).sum())
    out = settings.SILVER_DIR / "pain_labels_pool_summary.json"
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
