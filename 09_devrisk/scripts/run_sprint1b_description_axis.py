"""Sprint 1b: description-axis optionality surface (units axis proved flat).

The frozen model barely moves with unit-count changes (comparables bucket
smoothing) - so the real optionality lever must be description content.
Perturb description-derived characteristics and measure the response.
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
OUT = SILVER / "sprint1"

VARIANTS = {
    "as_submitted": lambda d: d,
    "remove_demolition": lambda d: re.sub(r"\bdemolition of [^,\.]*|and demolition[^,\.]*|, demolition[^,\.]*", "", d or "", flags=re.I),
    "add_amenity_space": lambda d: (d or "") + " with generous public open space and amenity areas",
    "add_green_infrastructure": lambda d: (d or "") + " incorporating green roofs, SUDS and extensive landscaping",
    "remove_storeys": lambda d: re.sub(r"\b(\d+)[ -]storey\b", "2 storey", d or "", flags=re.I),
    "add_change_of_use": lambda d: (d or "") + " involving the change of use of existing structures",
    "add_social_housing": lambda d: (d or "") + " including Part V social housing provision",
    "add_reduced_density": lambda d: (d or "") + " at a reduced density with generous setbacks",
}


def main() -> None:
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                               columns=["case_key", "PlanningAuthority", "DevelopmentDescription",
                                        "NumResidentialUnits", "AreaofSite", "FloorArea",
                                        "ITMEasting", "ITMNorthing", "ReceivedDate", "Decision",
                                        "FIRequestDate"])
    register = register.drop_duplicates("case_key")
    register["units"] = pd.to_numeric(register["NumResidentialUnits"], errors="coerce")
    register["site_area"] = pd.to_numeric(register["AreaofSite"], errors="coerce")
    register["floor_area"] = pd.to_numeric(register["FloorArea"], errors="coerce")
    register["recv_year"] = pd.to_datetime(register["ReceivedDate"], utc=True,
                                           errors="coerce").dt.tz_localize(None).dt.year
    base = register.dropna(subset=["units", "site_area", "ITMEasting", "ITMNorthing"])
    base = base[(base["units"] >= 5) & (base["recv_year"] >= 2018)]
    sample = base.sample(min(100, len(base)), random_state=42)

    rows = []
    for _, r in sample.iterrows():
        for name, fn in VARIANTS.items():
            desc = fn(r["DevelopmentDescription"])
            if not desc or desc == r["DevelopmentDescription"] and name != "as_submitted":
                continue
            proposal = proposal_from_application(
                authority=r["PlanningAuthority"], description=desc,
                units=int(r["units"]), site_area_sqm=float(r["site_area"]),
                floor_area_sqm=float(r["floor_area"]) if pd.notna(r["floor_area"]) else None,
                itm_easting=float(r["ITMEasting"]), itm_northing=float(r["ITMNorthing"]),
                submission_year=int(r["recv_year"]))
            try:
                out = score_planning(proposal)
            except Exception:
                continue
            rows.append({"case_key": r["case_key"], "variant": name,
                         "refusal_probability": out["refusal_probability"],
                         "risk_band": out["risk_band"]})
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT / "description_surface.csv", index=False)
    base_p = frame[frame["variant"] == "as_submitted"].set_index("case_key")["refusal_probability"]
    report = {"n_schemes": int(frame["case_key"].nunique())}
    for name in VARIANTS:
        if name == "as_submitted":
            continue
        sub = frame[frame["variant"] == name].set_index("case_key")["refusal_probability"]
        both = pd.concat([base_p, sub.rename("variant_p")], axis=1).dropna()
        if len(both):
            delta = (both["variant_p"] - both["refusal_probability"]) * 100
            report[name] = {"n": int(len(both)),
                            "median_delta_pp": round(float(delta.median()), 2),
                            "p10_pp": round(float(delta.quantile(0.1)), 2),
                            "p90_pp": round(float(delta.quantile(0.9)), 2),
                            "pct_improved": round(float((delta < 0).mean() * 100), 1),
                            "mean_abs_pp": round(float(delta.abs().mean()), 2)}
    (OUT / "description_surface_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
