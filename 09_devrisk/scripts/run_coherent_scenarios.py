"""Coherent design-scenario engine + first registered counterfactual batch.

Follows the brief's Phase 4/5 discipline:
- design bundles with explicit dependency rules (units -> density, parking,
  open space, floor area, description text), immutable fields preserved
- frozen model + empirical-neighbour engine + support score
- paraphrase stability (3 rewrites; wording variance vs design effect)
- append-only registry; no production claims without gates
"""
from __future__ import annotations

import csv
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
REGISTRY = Path("experiments/counterfactual_experiment_registry.csv")

ASSUMPTIONS = {
    "parking_house": 1.2, "parking_apartment": 0.8, "open_space_share": 0.15,
    "unit_size_house": 110.0, "unit_size_apartment": 75.0,
    "parking": "assumed from unit mix (client-supplied standards preferred)",
    "open_space": "assumed 15% of site (client-supplied preferred)",
    "floor_area": "estimated from unit sizes",
}


def parse_design(desc: str, units: int, site_area: float) -> dict:
    d = (desc or "").lower()
    apt = "apartment" in d or "duplex" in d
    houses = "house" in d or "dwelling" in d or "terrace" in d or "semi" in d
    mix = "mixed" if apt and houses else ("apartment" if apt else "house")
    m = re.search(r"(\d+)[ -]storey", d)
    storeys = int(m.group(1)) if m else (4 if apt else 2)
    return {"units": units, "site_area": site_area, "mix": mix,
            "storeys": storeys, "creche": "creche" in d or "creche" in d,
            "open_space_mention": "open space" in d or "amenity" in d,
            "part_v": "part v" in d or "social housing" in d,
            "demolition": "demolition" in d}


def bundle(design: dict, *, units=None, storeys=None, mix=None, creche=None,
           part_v=None, demolition=None, open_space_mention=None) -> dict:
    u = units if units is not None else design["units"]
    s = storeys if storeys is not None else design["storeys"]
    m = mix if mix is not None else design["mix"]
    c = creche if creche is not None else design["creche"]
    pv = part_v if part_v is not None else design["part_v"]
    dm = demolition if demolition is not None else design["demolition"]
    os = open_space_mention if open_space_mention is not None else design["open_space_mention"]
    house_share = {"house": 1.0, "apartment": 0.0, "mixed": 0.7}[m]
    parking = int(round(u * (house_share * ASSUMPTIONS["parking_house"] +
                             (1 - house_share) * ASSUMPTIONS["parking_apartment"])))
    open_m2 = round(design["site_area"] * ASSUMPTIONS["open_space_share"], 0)
    floor_m2 = round(u * (house_share * ASSUMPTIONS["unit_size_house"] +
                          (1 - house_share) * ASSUMPTIONS["unit_size_apartment"]), 0)
    density = round(u / (design["site_area"] / 10000.0), 1)
    units_desc = ("dwellings" if m == "house" else ("apartments" if m == "apartment" else
                                                    f"residential units ({int(house_share * 100)}% houses, "
                                                    f"{int((1 - house_share) * 100)}% apartments)"))
    desc = (f"Residential development of {u} {units_desc} in blocks of up to {s} storeys, "
            f"with {parking} car parking spaces and {open_m2:.0f} sqm of public open space")
    if c:
        desc += ", including a creche"
    if pv:
        desc += ", including Part V social housing provision"
    if dm:
        desc += ", including demolition of existing structures on site"
    return {"units": u, "storeys": s, "mix": m, "creche": c, "part_v": pv,
            "demolition": dm, "open_space": os, "parking": parking,
            "open_space_m2": open_m2, "floor_area_m2": floor_m2, "density_uph": density,
            "description": desc}


def score(r, b, year: int) -> float:
    desc = b if isinstance(b, str) else b["description"]
    units = None if isinstance(b, str) else b["units"]
    p = proposal_from_application(authority=r["PlanningAuthority"], description=desc,
                                  units=units,
                                  site_area_sqm=float(r["AreaofSite"]) if pd.notna(r.get("AreaofSite")) else None,
                                  floor_area_sqm=None if isinstance(b, str) else b["floor_area_m2"],
                                  itm_easting=float(r["ITMEasting"]), itm_northing=float(r["ITMNorthing"]),
                                  submission_year=year)
    return score_planning(p)["refusal_probability"]


def paraphrase(desc: str, variant: int) -> str:
    if variant == 1:
        return desc.replace(" in blocks of up to ", " arranged in blocks not exceeding ").replace(
            " with ", ", with ", 1)
    if variant == 2:
        return "The proposed development comprises " + desc.replace("Residential development of ", "", 1).replace(
            ", with", " and provides", 1)
    return desc + "."


def main() -> None:
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "PlanningAuthority", "DevelopmentDescription",
                                   "NumResidentialUnits", "AreaofSite", "FloorArea",
                                   "ITMEasting", "ITMNorthing", "ReceivedDate"])
    reg = reg.drop_duplicates("case_key")
    reg["year"] = pd.to_datetime(reg["ReceivedDate"], utc=True, errors="coerce").dt.year

    rows = []
    for key in ["South Dublin County Council__LRD25A/0014W", "South Dublin County Council__SD17A/0397"]:
        r = reg[reg["case_key"] == key].iloc[0]
        units = int(pd.to_numeric(r["NumResidentialUnits"], errors="coerce") or 1)
        design = parse_design(str(r["DevelopmentDescription"]), units, float(r["AreaofSite"]))
        base = bundle(design)
        base_p = score(r, base, int(r["year"]))
        scenarios = {
            "current": base,
            "units_minus_20pct": bundle(design, units=max(int(units * 0.8), 1)),
            "units_plus_20pct": bundle(design, units=int(units * 1.2)),
            "apartments_4storey": bundle(design, mix="apartment", storeys=4),
            "houses_2storey": bundle(design, mix="house", storeys=2),
            "add_creche": bundle(design, creche=True),
            "reduce_storeys": bundle(design, storeys=max(design["storeys"] - 1, 2)),
            "add_part_v": bundle(design, part_v=True),
            "no_open_space_language": bundle(design, open_space_mention=False),
        }
        out = {"case_key": key, "base_p": round(base_p, 4), "scenarios": {}}
        for name, b in scenarios.items():
            p = score(r, b, int(r["year"]))
            ps = [score(r, paraphrase(b["description"], v), int(r["year"])) for v in (1, 2, 3)]
            para_sd = float(np.std(ps)) if len(ps) else 0.0
            effect = (p - base_p) * 100
            verdict = "SUPPORTED" if False else ("MODEL_ONLY" if abs(effect) >= 1.0 else "MODEL_ONLY")
            if abs(effect) < 1.0:
                verdict = "MODEL_ONLY"
            if para_sd * 100 > max(abs(effect), 1.0):
                verdict = "FRAGILE"
            out["scenarios"][name] = {
                "refusal_p": round(p, 4), "delta_pp": round(effect, 2),
                "paraphrase_sd_pp": round(para_sd * 100, 2),
                "units": b["units"], "density_uph": b["density_uph"], "mix": b["mix"],
                "storeys": b["storeys"], "parking": b["parking"],
                "open_space_m2": b["open_space_m2"], "floor_area_m2": b["floor_area_m2"],
                "verdict": verdict,
                "support": "neighbour engine pending",
            }
        rows.append(out)
    (SILVER / "report" / "counterfactuals" / "coherent_scenarios.json").write_text(
        json.dumps(rows, indent=2), encoding="utf-8")
    with open(REGISTRY, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for entry in rows:
            for name, s in entry["scenarios"].items():
                w.writerow([f"CF-{entry['case_key'][:12]}-{name}",
                            f"coherent bundle {name} changes refusal",
                            "submission day", entry["case_key"], name,
                            "units/density/mix/storeys/description coherent",
                            "frozen refusal model", "none", "pending",
                            "none (prospective)", f"delta {s['delta_pp']}pp",
                            f"paraphrase sd {s['paraphrase_sd_pp']}pp", "paraphrase",
                            s["verdict"], "audit phase 1 - no production claims"])
    print(json.dumps(rows, indent=2, default=str)[:5000])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
