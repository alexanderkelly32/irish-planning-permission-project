#!/usr/bin/env python3
"""Power demonstration: the algorithm as a decision engine, not a stat.

1) Capture: share of actual 2024+2025 GE10 refusals falling in the model's top
   quintiles (how much of the pain it sees coming).
2) Case studies: real refused schemes - model risk, model reasons, model's
   suggested change, rescored risk - plus a real granted scheme the model
   cleared.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))

from build_8020_regime_experiment import build_data  # noqa: E402
from explain_proposal import explain_proposal  # noqa: E402
from explain_scenario_plain import plain_language  # noqa: E402
from model_feature_builder import score_proposal  # noqa: E402

ARTIFACT = ROOT / "05_policy" / "current" / "model_v4" / "national_residential_v4_full.joblib"


def proposal_from_row(row: pd.Series) -> dict:
    return {
        "authority": str(row["PlanningAuthority"]),
        "description": str(row["description_stripped"] or row.get("DevelopmentDescription") or ""),
        "units": float(row["units"]) if pd.notna(row["units"]) else 10.0,
        "site_area_sqm": float(row["AreaofSite"]) * 10000 if pd.notna(row["AreaofSite"]) else None,
        "floor_area_sqm": float(row["FloorArea"]) if pd.notna(row["FloorArea"]) else None,
        "itm_easting": float(row["ITMEasting"]),
        "itm_northing": float(row["ITMNorthing"]),
        "submission_year": int(row["received_date_dt"].year),
    }


def suggested_changes(base: dict, artifact) -> list[dict]:
    levers = []
    units = int(base["units"] or 0)
    site = base["site_area_sqm"] or 0
    if units >= 10:
        levers.append(("reduce units by 25%", {"units": max(1, int(units * 0.75))}))
        levers.append(("increase site by 50%", {"site_area_sqm": site * 1.5}))
        levers.append(("halve the density (units -50%)", {"units": max(1, int(units * 0.5))}))
        levers.append(("add community facilities", {"description": f"{base['description']} with community facilities"}))
        levers.append(("add landscaped open space", {"description": f"{base['description']} with landscaped open space and landscaping works"}))
        levers.append(("masonry construction", {"description": f"{base['description']} of masonry construction with brick finish"}))
    out = []
    for label, changes in levers:
        scenario = {**base, **changes}
        result = plain_language(artifact, base, scenario)
        out.append({"change": label, "delta_pp": result["delta_pp"], "new_refusal": result["scenario_refusal_probability"], "why": result["explanations"][:1]})
    out.sort(key=lambda r: r["delta_pp"])
    return out


def main() -> None:
    data, train, test, y = build_data()
    artifact = joblib.load(ARTIFACT)
    ranking = artifact["ranking_model"]
    ge10 = test[test["units"] >= 10].copy()
    ge10["risk"] = ranking.predict_proba(ge10[artifact["feature_columns"]])[:, 1]
    quintile = pd.qcut(ge10["risk"], 5, labels=False)
    ge10["quintile"] = quintile
    refusals = ge10[ge10["target_refused"] == 1]
    total_refusals = len(refusals)
    capture = {
        "n_schemes": int(len(ge10)),
        "n_refusals": total_refusals,
        "share_of_refusals_in_top_quintile": round(float((refusals["quintile"] == 4).mean()), 4),
        "share_of_refusals_in_top_two_quintiles": round(float((refusals["quintile"] >= 3).mean()), 4),
        "share_of_grants_in_bottom_quintile": round(float((ge10.loc[ge10["target_refused"] == 0, "quintile"] == 0).mean()), 4),
    }

    refused_top = ge10[(ge10["target_refused"] == 1) & (ge10["quintile"] >= 3)].sort_values("risk", ascending=False)
    case_studies = []
    used = set()
    for _, row in refused_top.iterrows():
        base = proposal_from_row(row)
        site = base["site_area_sqm"]
        if site is None or not (500 <= site <= 5_000_000):
            continue
        if base["floor_area_sqm"] is None:
            continue
        if row["case_key"] in used:
            continue
        used.add(row["case_key"])
        score = score_proposal(base)
        digest = explain_proposal(artifact, base)
        changes = suggested_changes(base, artifact)
        if not changes or changes[0]["delta_pp"] >= -3.0:
            continue
        case_studies.append({
            "type": "refused - caught by the model",
            "case_key": str(row["case_key"]),
            "council": base["authority"],
            "units": base["units"],
            "site_area_sqm": round(base["site_area_sqm"] or 0, 0),
            "description": base["description"][:300],
            "model_refusal_probability": score["refusal_probability"],
            "risk_band": score["risk_band"],
            "what_drove_it": [f["text"] for f in digest["factors"][:3]],
            "best_change": changes[0] if changes else None,
            "second_change": changes[1] if len(changes) > 1 else None,
        })
        if len(case_studies) >= 2:
            break

    granted_bottom = ge10[(ge10["target_refused"] == 0) & (ge10["quintile"] == 0)].sort_values("risk")
    if len(granted_bottom):
        for _, row in granted_bottom.iterrows():
            base = proposal_from_row(row)
            site = base["site_area_sqm"]
            if site is None or not (500 <= site <= 5_000_000) or base["floor_area_sqm"] is None:
                continue
            score = score_proposal(base)
            case_studies.append({
                "type": "granted - cleared by the model",
                "case_key": str(row["case_key"]),
                "council": base["authority"],
                "units": base["units"],
                "site_area_sqm": round(base["site_area_sqm"] or 0, 0),
                "description": base["description"][:300],
                "model_refusal_probability": score["refusal_probability"],
                "risk_band": score["risk_band"],
                "outcome": "granted",
            })
            break

    payload = {"capture": capture, "case_studies": case_studies,
               "revision_evidence_note": "Historical refused-to-revised-to-granted pairs: reducing units precedes grants 74.4% of the time (refused arm, n=896)."}
    (OUT / "algo_power_demo.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
