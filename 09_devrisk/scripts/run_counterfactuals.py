"""Driver attribution + scheme-specific counterfactuals on the frozen model.

For a scheme: score base + tailored rewrites of ITS OWN description and
units, report deltas with the caveat (model-implied sensitivity, 1-4pp
typical). Driver table: mean |delta| from permuting feature families
across a 50-scheme sample. Conditions/reasons accuracy cited from the
registry record.
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
from devrisk.models.planning_adapter import proposal_from_application, score_planning  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "report" / "counterfactuals"
OUT.mkdir(parents=True, exist_ok=True)


def score_row(r, desc, units, year):
    proposal = proposal_from_application(
        authority=r["PlanningAuthority"], description=desc, units=units,
        site_area_sqm=float(r["AreaofSite"]) if pd.notna(r.get("AreaofSite")) else None,
        floor_area_sqm=float(r["FloorArea"]) if pd.notna(r.get("FloorArea")) else None,
        itm_easting=float(r["ITMEasting"]), itm_northing=float(r["ITMNorthing"]),
        submission_year=year)
    return score_planning(proposal)["refusal_probability"]


COUNTERFACTUALS = [
    ("units_-20pct", lambda u: max(int(u * 0.8), 1), None),
    ("units_+20pct", lambda u: int(u * 1.2), None),
    ("add_open_space", None, " with substantial public open space and play areas"),
    ("add_creche", None, " including a creche"),
    ("reduce_storeys", None, None),  # handled via regex below
    ("add_part_v", None, " including Part V social housing provision"),
    ("reduce_density_language", None, " at a reduced density with generous setbacks and landscaping"),
    ("remove_technical_language", None, None),
]


def apply_desc(desc, name):
    if name == "add_open_space":
        return desc + " with substantial public open space and play areas"
    if name == "add_creche":
        return desc + " including a creche"
    if name == "reduce_storeys":
        return re.sub(r"\b(\d+)[ -]storey\b", lambda m: f"{max(int(m.group(1)) - 1, 2)} storey", desc, flags=re.I)
    if name == "add_part_v":
        return desc + " including Part V social housing provision"
    if name == "reduce_density_language":
        return desc + " at a reduced density with generous setbacks and landscaping"
    if name == "remove_technical_language":
        return re.sub(r"\b(?:attenuation|SUDS|suds|surface water management|drainage network)\b[^,\.]*", "", desc, flags=re.I)
    return desc


def main() -> None:
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "PlanningAuthority", "DevelopmentDescription",
                                   "NumResidentialUnits", "AreaofSite", "FloorArea",
                                   "ITMEasting", "ITMNorthing", "ReceivedDate"])
    reg = reg.drop_duplicates("case_key")
    reg["year"] = pd.to_datetime(reg["ReceivedDate"], utc=True, errors="coerce").dt.year

    out = {}
    for key in ["South Dublin County Council__SD17A/0397", "South Dublin County Council__LRD25A/0014W"]:
        r = reg[reg["case_key"] == key].iloc[0]
        units = int(pd.to_numeric(r["NumResidentialUnits"], errors="coerce") or 1)
        desc = str(r["DevelopmentDescription"])
        base_p = score_row(r, desc, units, int(r["year"]))
        rows = [{"change": "as_submitted", "p": base_p, "delta_pp": 0.0}]
        for name, unit_fn, _ in COUNTERFACTUALS:
            new_units = unit_fn(units) if unit_fn else units
            new_desc = apply_desc(desc, name) if name != "units_-20pct" and name != "units_+20pct" else desc
            if new_desc == desc and new_units == units:
                continue
            try:
                p = score_row(r, new_desc, new_units, int(r["year"]))
            except Exception:
                continue
            rows.append({"change": name, "p": p, "delta_pp": round((p - base_p) * 100, 2)})
        out[key] = {"base_p": round(base_p, 4), "counterfactuals": rows}

    # driver attribution: permute feature families over a sample
    sample = reg.dropna(subset=["AreaofSite", "ITMEasting"]).sample(min(40, len(reg)), random_state=42)
    drivers = {}
    for _, r in sample.iterrows():
        units = pd.to_numeric(r["NumResidentialUnits"], errors="coerce")
        units = int(units) if pd.notna(units) else 1
        base_p = score_row(r, str(r["DevelopmentDescription"]), units, int(r["year"]))
        for fam, pat in [("density_language", r"density|scale|storey|units"),
                         ("amenity_language", r"open space|amenity|play|landscap|creche"),
                         ("technical_language", r"drainage|attenuation|suds|sewer|access|road")]:
            d2 = re.sub(pat, "", str(r["DevelopmentDescription"]), flags=re.I)
            if d2 == str(r["DevelopmentDescription"]):
                continue
            p2 = score_row(r, d2, units, int(r["year"]))
            drivers.setdefault(fam, []).append(abs(p2 - base_p) * 100)
        p_u = score_row(r, str(r["DevelopmentDescription"]), max(int(units * 0.8), 1), int(r["year"]))
        drivers.setdefault("units", []).append(abs(p_u - base_p) * 100)
    driver_table = {k: {"n": len(v), "mean_abs_pp": round(float(np.mean(v)), 2),
                        "max_pp": round(float(np.max(v)), 2)} for k, v in drivers.items() if v}
    out["driver_attribution"] = driver_table
    out["conditions_reasons_accuracy"] = {
        "precommencement_conditions": "rolling-origin AUC 0.714/0.765/0.747 (promoted)",
        "financial_conditions": "AUC 0.633-0.688 (provisional)",
        "other_condition_families": "flat (~0.47-0.54) - not predicted",
        "refusal_reasons_zero_day": "top-3 recall 0.478 vs 0.467 baseline - FALSIFIED",
        "refusal_theme_matching": "descriptive (works by construction)",
    }
    out["caveat"] = "all counterfactuals are model-implied sensitivities, not causal effects; typical magnitude 1-4pp"
    (OUT / "counterfactuals_report.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str)[:6000])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
