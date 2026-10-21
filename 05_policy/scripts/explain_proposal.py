#!/usr/bin/env python3
"""Single-proposal bottleneck explainer for v4-full (no LLM).

Decomposes one proposal's risk score into its largest contributing features
(contribution = transformed feature value x coefficient), then translates the
top drivers into plain-language bullets: what pushes the risk up and what
pulls it down.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy import sparse

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from explain_scenario_plain import rate_tables  # noqa: E402
from model_feature_builder import build_feature_row, score_proposal  # noqa: E402

MODEL_PATH = ROOT / "05_policy" / "current" / "model_v4" / "national_residential_v4_full.joblib"


def _row_values(frame: pd.DataFrame, name: str, default=np.nan):
    if name in frame.columns:
        value = frame.iloc[0][name]
        return float(value) if pd.notna(value) else default
    return default


def explain_proposal(artifact, proposal: dict) -> dict:
    score = score_proposal(proposal)
    frame = build_feature_row(proposal)
    pre = artifact["ranking_model"].named_steps["preprocessor"]
    model = artifact["ranking_model"].named_steps["model"]
    x = pre.transform(frame)
    names = pre.get_feature_names_out()
    coefs = model.coef_[0]
    values = x.toarray()[0] if sparse.issparse(x) else x[0]
    contributions = values * coefs

    tables = rate_tables()
    national_rate = tables["bucket_rates"]["single dwelling"]["rate"] * 0 + np.nan
    bucket_row = frame.iloc[0]["application_bucket"]
    bucket_rate = tables["bucket_rates"].get(str(bucket_row), {}).get("rate")
    council_bucket = tables["council_bucket_rates"].get(f"{proposal['authority']}__{bucket_row}")
    if council_bucket is not None and council_bucket["n"] >= 30:
        bucket_rate = council_bucket["rate"]
        bucket_context = f"in {proposal['authority']}"
    else:
        bucket_context = "across Ireland"

    factors: list[dict] = []
    text_raise: list[str] = []
    text_lower: list[str] = []
    top5_rate = _row_values(frame, "comp_top5_refusal_rate")
    top20_rate = _row_values(frame, "comp_top20_refusal_rate")
    council_rate = _row_values(frame, "authority_prior_12m_refusal_rate")
    nearby_rate = _row_values(frame, "nearby_1km_prior_24m_refusal_rate")
    flood_hit = _row_values(frame, "flood_any", 0.0)
    density = _row_values(frame, "density_units_per_ha")
    site_per_unit = _row_values(frame, "site_sqm_per_unit")
    band_low = _row_values(frame, "density_band_low", 0.0)
    band_mid = _row_values(frame, "density_band_mid", 0.0)
    band_high = _row_values(frame, "density_band_high", 0.0)

    name_to_contrib = dict(zip(names, contributions))

    bucket_contrib = sum(v for k, v in name_to_contrib.items() if "application_bucket" in k)
    comp_contrib = sum(v for k, v in name_to_contrib.items() if k.startswith("num__comp_"))
    density_contrib = sum(v for k, v in name_to_contrib.items() if any(t in k for t in ("density_", "floor_area_ratio")))
    flood_contrib = sum(v for k, v in name_to_contrib.items() if "flood" in k or "fluvial" in k or "coastal" in k)
    council_contrib = sum(v for k, v in name_to_contrib.items() if "authority_prior" in k)
    nearby_contrib = sum(v for k, v in name_to_contrib.items() if "nearby_" in k)
    site_contrib = sum(v for k, v in name_to_contrib.items() if "site_sqm_per_unit" in k or "log_site_area_sqm" in k or "log_floor_area_sqm" in k)
    plan_contrib = sum(v for k, v in name_to_contrib.items() if "plan_theme" in k or "log_plan" in k or "policy_plan" in k)

    if bucket_rate is not None:
        factors.append({"driver": "application type",
                        "text": f"This is a \u2018{bucket_row}\u2019 application; {bucket_context} these are refused {bucket_rate * 100:.0f}% of the time.",
                        "importance": abs(bucket_contrib)})
    if np.isfinite(comp_contrib) and abs(comp_contrib) > 0.02 and np.isfinite(top5_rate):
        factors.append({"driver": "similar past applications",
                        "text": f"The most similar past applications to this scheme were refused {top5_rate * 100:.0f}% of the time.",
                        "importance": abs(comp_contrib)})
    if np.isfinite(density_contrib) and abs(density_contrib) > 0.02 and np.isfinite(density):
        if band_low:
            band = "low (below 35 homes/ha)"
        elif band_mid:
            band = "medium (35-50 homes/ha)"
        else:
            band = "high (above 50 homes/ha)"
        band_rate = rate_tables().get("density_band_rates", {}).get(band, {}).get("rate")
        rate_text = f" Historically, schemes in this band refuse at {band_rate * 100:.0f}%." if band_rate else ""
        factors.append({"driver": "site density",
                        "text": f"The scheme is at {density:.0f} homes per hectare \u2013 the {band} band.{rate_text}",
                        "importance": abs(density_contrib)})
    if flood_hit and abs(flood_contrib) > 0.005:
        factors.append({"driver": "flood risk",
                        "text": "The site falls within a mapped flood zone; flooding and drainage are among the most common refusal grounds nationally.",
                        "importance": abs(flood_contrib)})
    if np.isfinite(council_rate) and abs(council_contrib) > 0.02:
        factors.append({"driver": "council track record",
                        "text": f"Applications in {proposal['authority']} have recently been refused {council_rate * 100:.0f}% of the time.",
                        "importance": abs(council_contrib)})
    if np.isfinite(nearby_rate) and abs(nearby_contrib) > 0.02 and np.isfinite(nearby_rate) and nearby_rate > 0:
        factors.append({"driver": "local track record",
                        "text": f"Recent applications within 1km of the site were refused {nearby_rate * 100:.0f}% of the time.",
                        "importance": abs(nearby_contrib)})
    if np.isfinite(site_per_unit) and abs(site_contrib) > 0.02 and site_per_unit < 800:
        factors.append({"driver": "site space per home",
                        "text": f"The scheme provides {site_per_unit:.0f} m\u00b2 of site per home.",
                        "importance": abs(site_contrib)})
    if abs(plan_contrib) > 0.02:
        factors.append({"driver": "local plan",
                        "text": "The development plan in force here carries a large set of design and zoning objectives.",
                        "importance": abs(plan_contrib)})

    factors = {f["driver"]: f for f in factors}
    plan_code_count = int(np.expm1(_row_values(frame, "log_plan_unique_codes", 0.0)))
    if "local plan" in factors and plan_code_count > 0:
        factors["local plan"]["text"] = f"The development plan in force here carries around {plan_code_count} objectives."
    ordered = sorted(factors.values(), key=lambda f: -f["importance"])[:6]
    for factor in ordered:
        factor.pop("importance", None)

    confidence_notes: list[str] = []
    comp_sim = _row_values(frame, "comp_top20_mean_similarity", np.nan)
    comp_count = _row_values(frame, "comp_top20_count", 0.0)
    if (not np.isfinite(comp_sim)) or comp_sim < 0.2 or comp_count < 20:
        confidence_notes.append(
            "Few close precedents: this scheme type is rare in the historical record, so the score is less certain than usual."
        )
    council = str(proposal.get("authority") or "")
    council_flags = {
        "Fingal County Council": "Fingal has refused 4 of its last 6 schemes of this size (historical rate 21%) - recent outcomes are worse than the model's inputs suggest; treat this score as a lower bound.",
        "Limerick County Council": "Limerick's recent large-scheme refusals (20%) are running above its historical rate (8.5%) - the score may understate risk.",
        "Cork County Council": "Cork County decisions are flagged as a data-quality issue in the register - treat Cork scores as provisional.",
    }
    if council in council_flags:
        confidence_notes.append(council_flags[council])
    description = str(proposal.get("description") or "").lower()
    import re as _re  # noqa: E402

    if _re.search(
        r"(senior\s*living|retirement\s*village|nursing\s*home|care\s*home|assisted\s*living|sheltered|community\s*dwelling|residential\s*care|independent\s*living|retirement\s*home|continuing\s*care)",
        description,
    ):
        confidence_notes.append(
            "Specialised scheme (senior living / care / community): these historically refuse at roughly 27-35%, higher than the general score suggests - treat the number as a lower bound."
        )

    return {
        "refusal_probability": score["refusal_probability"],
        "grant_probability": score["grant_probability"],
        "risk_band": score["risk_band"],
        "factors": ordered,
        "confidence_notes": confidence_notes,
        "summary": (
            f"Together these factors give an estimated {score['refusal_probability'] * 100:.0f}% chance of refusal."
        ),
        "note": "Model-attributed drivers; the percentages are historical rates, not guarantees.",
    }


def main() -> None:
    artifact = joblib.load(MODEL_PATH)
    demos = {
        "apartment_block_dlr": {
            "authority": "Dun Laoghaire Rathdown County Council",
            "description": "construction of 12 no. apartments in a 4 storey block with car parking and associated site works",
            "units": 12,
            "site_area_sqm": 4000,
            "floor_area_sqm": 2400,
            "itm_easting": 722000,
            "itm_northing": 726500,
            "submission_year": 2026,
        },
        "one_off_house": {
            "authority": "Dun Laoghaire Rathdown County Council",
            "description": "construction of a single dwelling house with garage",
            "units": 1,
            "site_area_sqm": 4000,
            "floor_area_sqm": 250,
            "itm_easting": 722000,
            "itm_northing": 726500,
            "submission_year": 2026,
        },
    }
    out = {}
    for name, proposal in demos.items():
        result = explain_proposal(artifact, proposal)
        out[name] = result
        print(f"===== {name} =====  {result['summary']}")
        for factor in result["factors"]:
            print(f"  - {factor['text']}")
        print()
    (OUT / "proposal_bottleneck_explanations_v4.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("saved -> proposal_bottleneck_explanations_v4.json")


if __name__ == "__main__":
    main()
