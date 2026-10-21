#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "02_development" / "source_data" / "ground_source_extracted_final_wide_comprehensive_master.csv"
DEFAULT_OUTPUT_DIR = ROOT / "10_energy" / "source_data"
SOLAR_PRIOR = ROOT / "07_solar" / "source_data" / "likely_solar_farms.csv"
DC_PRIOR = ROOT / "08_data_centres" / "source_data" / "likely_data_centres.csv"

TYPE_PATTERNS: Dict[str, List[Tuple[str, re.Pattern]]] = {
    "wind": [
        ("wind_farm", re.compile(r"wind ?farm", re.I)),
        ("wind_turbine", re.compile(r"wind turbine", re.I)),
        ("wind_energy", re.compile(r"wind energy", re.I)),
    ],
    "solar": [
        ("solar", re.compile(r"\bsolar\b", re.I)),
        ("photovoltaic", re.compile(r"photovoltaic", re.I)),
        ("pv", re.compile(r"\bpv\b", re.I)),
    ],
    "bess": [
        ("bess", re.compile(r"\bbess\b", re.I)),
        ("battery_storage", re.compile(r"battery (?:energy )?storage", re.I)),
        ("storage_system", re.compile(r"energy storage system|storage facility", re.I)),
    ],
    "data_centre": [
        ("data_centre", re.compile(r"data ?cent[re]{2}|data hall|data processing", re.I)),
    ],
    "biogas": [
        ("biogas", re.compile(r"biogas", re.I)),
        ("anaerobic_digestion", re.compile(r"anaerobic digest", re.I)),
        ("biomethane", re.compile(r"biomethane", re.I)),
    ],
    "hydro": [
        ("hydro", re.compile(r"hydro ?electric|hydropower|hydro scheme", re.I)),
    ],
    "chp": [
        ("chp", re.compile(r"\bchp\b|combined heat and power|cogeneration", re.I)),
        ("energy_centre", re.compile(r"energy centre|district heating", re.I)),
    ],
    "grid": [
        ("substation", re.compile(r"sub[- ]?station", re.I)),
        ("overhead_line", re.compile(r"overhead line|\bOHL\b", re.I)),
        ("underground_cable", re.compile(r"underground (?:electricity )?cable", re.I)),
        ("transmission", re.compile(r"transmission line|transmission network", re.I)),
        ("grid_connection", re.compile(r"grid connection|connect(?:ed)? to the (?:national )?grid", re.I)),
        ("interconnector", re.compile(r"interconnector", re.I)),
        ("kv_line", re.compile(r"\b(?:38|110|220|400)\s*kV\b", re.I)),
    ],
    "demand": [
        ("ev_charging", re.compile(r"ev charging|electric vehicle charg", re.I)),
    ],
}

TYPE_PRECEDENCE = ["wind", "solar", "bess", "data_centre", "biogas", "hydro", "chp", "grid", "demand"]

MINOR_PATTERNS: Dict[str, re.Pattern] = {
    "wind": re.compile(
        r"domestic|dwelling|private (?:residence|house)|replacement (?:of )?(?:an existing|a) turbine|micro ?wind",
        re.I,
    ),
    "solar": re.compile(r"roof|rooftop|mounted to|domestic|dwelling|garage|farmyard|shed", re.I),
    "bess": re.compile(r"domestic|residential|home battery|dwelling", re.I),
    "grid": re.compile(
        r"domestic|dwelling|connection for (?:a )?single|service connection|temporary",
        re.I,
    ),
}

MW_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:MWp|MWac|MWdc|MW|megawatts?)", re.I)
MWH_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*MWh", re.I)
MVA_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*MVA", re.I)
KV_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*kV", re.I)
TURBINE_RE = re.compile(r"(\d+)\s*(?:no\.?\.?\s*)?(?:of\s+)?(?:wind\s+)?turbines?", re.I)
HA_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:ha|hectares)\b", re.I)


def _nums(pattern: re.Pattern, text: str) -> List[float]:
    return [float(m.replace(",", "")) for m in pattern.findall(text)]


def normalise_decision(raw: object) -> str:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "undecided"
    s = str(raw).strip()
    if not s:
        return "undecided"
    t = s.lower()
    if "split decision" in t or ("&" in s and ("grant" in t and "refus" in t)):
        return "split"
    if "grant" in t or "unconditional" in t or "conditional" in t or "part 8 approved" in t or "approval" in t:
        return "grant"
    if "refus" in t:
        return "refuse"
    if "invalid" in t or "declared inva" in t or "returned application" in t:
        return "invalid"
    if "exempt" in t:
        return "exempt"
    if "withdraw" in t:
        return "withdrawn"
    if "additional information" in t or "req ai" in t or "seek clarification" in t or "extension of time" in t:
        return "additional_info"
    if "quashed" in t:
        return "other"
    return "other"


def parse_capacity(description: str, energy_type: str) -> Dict[str, object]:
    d = description or ""
    mw_vals = _nums(MW_RE, d)
    mwh_vals = _nums(MWH_RE, d)
    mva_vals = _nums(MVA_RE, d)
    kv_vals = _nums(KV_RE, d)
    turbine_vals = _nums(TURBINE_RE, d)
    if energy_type == "grid" and not mw_vals and mva_vals:
        mw_vals = mva_vals
    return {
        "capacity_mw": max(mw_vals) if mw_vals else None,
        "capacity_mwh": max(mwh_vals) if mwh_vals else None,
        "voltage_kv": max(kv_vals) if kv_vals else None,
        "turbine_count": max(turbine_vals) if turbine_vals else None,
        "all_mw_values": "|".join(f"{v:g}" for v in sorted(set(mw_vals))),
    }


GRID_HEAD_RE = re.compile(
    r"substation|overhead line|\bOHL\b|transmission|interconnector|reinforcement|underground cable|\b(?:38|110|220|400)\s*kV\b",
    re.I,
)


TELECOM_FP_RE = re.compile(r"telecommunications? support|telecom|antenna", re.I)
WIND_CORE_RE = re.compile(r"wind ?farm|wind turbine", re.I)


def classify_type(description: str) -> Tuple[str, List[str]]:
    d = " ".join((description or "").split())
    tags: List[str] = []
    for t in TYPE_PRECEDENCE:
        found = [label for label, pat in TYPE_PATTERNS[t] if pat.search(d)]
        if not found:
            continue
        if t == "wind" and TELECOM_FP_RE.search(d) and not WIND_CORE_RE.search(d):
            return "wind_fp", found
        if t == "grid" and not GRID_HEAD_RE.search(d[:160]):
            return "grid_minor", found
        if t == "demand":
            return "demand", found
        return t, found
    return "other", tags


def is_utility_scale(energy_type: str, capacity_mw: Optional[float], capacity_mwh: Optional[float],
                     turbine_count: Optional[float], voltage_kv: Optional[float],
                     description: str) -> bool:
    d = (description or "").lower()
    if energy_type == "wind":
        if MINOR_PATTERNS["wind"].search(d):
            return False
        if capacity_mw is not None and capacity_mw >= 0.5:
            return True
        return bool(turbine_count and turbine_count >= 2) or "wind farm" in d
    if energy_type == "solar":
        if capacity_mw is not None and capacity_mw >= 1.0:
            return True
        return "solar farm" in d or "solar park" in d or "ground mounted" in d
    if energy_type == "bess":
        if MINOR_PATTERNS["bess"].search(d):
            return False
        return (capacity_mw is not None and capacity_mw >= 5.0) or (
            capacity_mwh is not None and capacity_mwh >= 10.0
        ) or "grid scale" in d or "grid-scale" in d
    if energy_type == "biogas":
        return capacity_mw is not None and capacity_mw >= 0.2
    if energy_type == "hydro":
        return capacity_mw is not None and capacity_mw >= 0.1
    if energy_type == "chp":
        return capacity_mw is not None and capacity_mw >= 0.5
    if energy_type == "grid":
        if MINOR_PATTERNS["grid"].search(d):
            return False
        if voltage_kv is not None and voltage_kv >= 38.0:
            return True
        return bool(GRID_HEAD_RE.search(d[:160]))
    if energy_type == "data_centre":
        return True
    return False


OUTPUT_COLUMNS = [
    "case_key",
    "energy_type",
    "energy_tags",
    "is_utility_scale",
    "capacity_mw",
    "capacity_mwh",
    "voltage_kv",
    "turbine_count",
    "all_mw_values",
    "outcome",
    "decision_raw",
    "planning_authority",
    "application_number",
    "application_type",
    "received_date",
    "decision_date",
    "grant_date",
    "development_address",
    "itm_easting",
    "itm_northing",
    "area_of_site",
    "appeal_status",
    "appeal_decision",
    "link_app_details",
    "development_description",
]


def load_prior(path: Path) -> Optional[set]:
    if not path.exists():
        return None
    df = pd.read_csv(path, dtype=str, low_memory=False)
    return set(df["case_key"].dropna().astype(str))


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract the energy-infrastructure cohort from the planning register.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    usecols = [
        "case_key", "PlanningAuthority", "ApplicationNumber", "ApplicationType",
        "ApplicationStatus", "Decision", "ReceivedDate", "DecisionDate", "GrantDate",
        "DevelopmentDescription", "DevelopmentAddress", "ITMEasting", "ITMNorthing",
        "AreaofSite", "AppealStatus", "AppealDecision", "LinkAppDetails",
    ]
    rename = {
        "PlanningAuthority": "planning_authority",
        "ApplicationNumber": "application_number",
        "ApplicationType": "application_type",
        "ApplicationStatus": "application_status",
        "Decision": "decision_raw",
        "ReceivedDate": "received_date",
        "DecisionDate": "decision_date",
        "GrantDate": "grant_date",
        "DevelopmentDescription": "development_description",
        "DevelopmentAddress": "development_address",
        "ITMEasting": "itm_easting",
        "ITMNorthing": "itm_northing",
        "AreaofSite": "area_of_site",
        "AppealStatus": "appeal_status",
        "AppealDecision": "appeal_decision",
        "LinkAppDetails": "link_app_details",
    }

    solar_prior = load_prior(SOLAR_PRIOR) or set()
    dc_prior = load_prior(DC_PRIOR) or set()

    chunks = pd.read_csv(args.input, usecols=usecols, dtype=str, low_memory=False, chunksize=100000)
    hits: List[pd.DataFrame] = []
    for chunk in chunks:
        desc = chunk["DevelopmentDescription"].fillna("").str.lower()
        mask = pd.Series(False, index=chunk.index)
        for patterns in TYPE_PATTERNS.values():
            for _label, pat in patterns:
                mask |= desc.str.contains(pat)
        mask |= chunk["case_key"].isin(solar_prior) | chunk["case_key"].isin(dc_prior)
        hits.append(chunk[mask])

    df = pd.concat(hits, ignore_index=True)
    df = df.rename(columns=rename)

    type_rows: List[Dict[str, object]] = []
    for row in df.to_dict("records"):
        description = str(row.get("development_description") or "")
        energy_type, tags = classify_type(description)
        cap = parse_capacity(description, energy_type)
        utility = is_utility_scale(
            energy_type, cap["capacity_mw"], cap["capacity_mwh"], cap["turbine_count"],
            cap["voltage_kv"], description,
        )
        if row.get("case_key") in solar_prior and energy_type == "other":
            energy_type = "solar"
            tags = ["solar_prior"]
        if row.get("case_key") in dc_prior and energy_type == "other":
            energy_type = "data_centre"
            tags = ["dc_prior"]
        out: Dict[str, object] = {}
        for col in OUTPUT_COLUMNS:
            if col in row:
                out[col] = row.get(col)
        out["energy_type"] = energy_type
        out["energy_tags"] = "|".join(tags)
        out["is_utility_scale"] = utility
        out.update(cap)
        out["outcome"] = normalise_decision(row.get("decision_raw"))
        type_rows.append(out)

    result = pd.DataFrame(type_rows, columns=OUTPUT_COLUMNS)
    result["is_utility_scale"] = result["is_utility_scale"].astype(bool)

    result.to_csv(args.output_dir / "energy_mentions_all.csv", index=False)
    cohort = result[~result["energy_type"].isin(["demand", "grid_minor", "wind_fp"])]
    cohort.to_csv(args.output_dir / "energy_cohort.csv", index=False)
    utility = cohort[cohort["is_utility_scale"]]
    utility.to_csv(args.output_dir / "energy_utility_scale.csv", index=False)
    dc = cohort[cohort["energy_type"] == "data_centre"]
    dc.to_csv(args.output_dir / "data_centre_demand_context.csv", index=False)

    summary = {
        "mentions_all": int(len(result)),
        "cohort_by_type": cohort.groupby("energy_type").size().to_dict(),
        "utility_by_type": utility.groupby("energy_type").size().to_dict(),
        "cohort_outcomes": cohort["outcome"].value_counts().to_dict(),
        "utility_outcomes": utility["outcome"].value_counts().to_dict(),
        "utility_with_mw": int(utility["capacity_mw"].notna().sum()),
        "utility_mw_total": round(float(utility["capacity_mw"].sum()), 1),
    }
    with (args.output_dir / "energy_cohort_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, default=str)

    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
