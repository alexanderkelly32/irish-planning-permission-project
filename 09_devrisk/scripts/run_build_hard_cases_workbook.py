"""Runner: hard-cases workbook - only the schemes auto-matching cannot solve.

Categories: no BCMS link, town/road-only BCMS address, single-token estate
name without eircode, multi-estate/SDZ/SHD schemes. Human fills estate names
here; everything else was auto-solved.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import re as _re  # noqa: E402

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.entity_resolution.ppr_matching import STOPWORDS  # noqa: E402
from devrisk.entity_resolution.scoring import uncommon_place_tokens  # noqa: E402

COUNTY_WORDS = {
    "carlow", "cavan", "clare", "cork", "donegal", "dublin", "galway", "kerry",
    "kildare", "kilkenny", "laois", "leitrim", "limerick", "longford", "louth",
    "mayo", "meath", "monaghan", "offaly", "roscommon", "sligo", "tipperary",
    "waterford", "westmeath", "wexford", "wicklow",
}


def _clean_tokens(text: str) -> set[str]:
    return {t for t in uncommon_place_tokens(str(text or ""), STOPWORDS) if _re.fullmatch(r"[a-z0-9]+", t)}


if __name__ == "__main__":
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    mature = cohort[cohort["grant_year"].between(2016, 2022)].copy()
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    links = pd.read_csv(settings.SILVER_DIR / "bcms_links_all_granted.csv")
    confirmed = links[links["confidence_band"] == "confirmed"]

    have_sales = set()
    for path in ("ppr_links_all_granted.csv", "scheme_sales_verified.csv", "scheme_sales_auto.csv"):
        p = settings.SILVER_DIR / path
        if p.exists():
            frame = pd.read_csv(p)
            if "confidence_band" in frame.columns:
                have_sales |= set(frame[frame["confidence_band"] == "confirmed"]["scheme_id"])
            else:
                have_sales |= set(frame["scheme_id"])

    linked_events = confirmed.merge(
        bcms[["bcms_event_id", "address_full", "eircode", "town", "street", "project_name"]],
        on="bcms_event_id", how="inner",
    )

    rows = []
    for _, scheme in mature.iterrows():
        scheme_id = str(scheme["case_key"])
        if scheme_id in have_sales:
            continue
        description = str(scheme.get("DevelopmentDescription") or "").lower()
        group = linked_events[linked_events["scheme_id"] == scheme_id]

        reason = ""
        if any(p in description for p in ("strategic development zone", "strategic housing development", " sdz", " shd")):
            reason = "SDZ/SHD area scheme"
        elif group.empty:
            reason = "no BCMS link"
        else:
            towns = set()
            for value in group["town"].dropna().astype(str):
                towns |= _clean_tokens(value)
            eircodes = {str(v).strip().upper().replace(" ", "") for v in group["eircode"].dropna().astype(str) if str(v).strip()}
            name_sets = set()
            for _, notice in group.iterrows():
                street_tokens = _clean_tokens(str(notice["street"] or ""))
                for text in (str(notice["address_full"] or ""), str(notice["project_name"] or "")):
                    tokens = _clean_tokens(text) - COUNTY_WORDS - towns - street_tokens
                    if tokens:
                        name_sets.add(frozenset(tokens))
            multi = False
            sets = list(name_sets)
            for i in range(len(sets)):
                for j in range(i + 1, len(sets)):
                    a, b = sets[i], sets[j]
                    overlap = len(a & b) / max(1, min(len(a), len(b)))
                    if a != b and overlap < 0.5 and not (a <= b or b <= a):
                        multi = True
            if multi:
                reason = "multi-estate BCMS notices"
            elif not sets:
                reason = "town/road-only BCMS address"
            elif all(len(s) < 2 for s in sets) and not eircodes:
                reason = "single-token estate name, no eircode"

        if not reason:
            continue
        rows.append({
            "scheme_id": scheme_id,
            "authority": scheme["PlanningAuthority"],
            "grant_year": scheme["grant_year"],
            "units": pd.to_numeric(pd.Series([scheme.get("NumResidentialUnits")]), errors="coerce").iloc[0],
            "register_address": str(scheme.get("DevelopmentAddress") or "")[:90],
            "description": description[:130],
            "bcms_address": (str(group["address_full"].iloc[0])[:70] if not group.empty else ""),
            "bcms_project_name": (str(group["project_name"].dropna().iloc[0])[:60] if not group.empty and group["project_name"].notna().any() else ""),
            "bcms_eircode": (" | ".join(group["eircode"].dropna().astype(str).unique()[:3]) if not group.empty else ""),
            "reason": reason,
            "estate_name_1": "",
            "estate_name_2": "",
            "eircode": "",
            "sellable_units": "",
            "is_build_to_sell": "",
            "notes": "",
        })

    workbook = pd.DataFrame(rows).sort_values(["reason", "units"], ascending=[True, False])
    out = settings.SILVER_DIR / "sales_workbook_HARD_CASES.csv"
    workbook.to_csv(out, index=False)
    print(f"hard-cases workbook -> {out} ({len(workbook)} rows)")
    print(workbook["reason"].value_counts().to_dict())
