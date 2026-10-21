#!/usr/bin/env python3
"""Plain-language scenario explanations (no LLM, no jargon).

Combines the v4-full linear decomposition with historical rate tables to
produce short, layperson-friendly sentences explaining why a scenario changed
the refusal probability.
"""
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from explain_scenario_delta import explain_delta  # noqa: E402
from model_feature_builder import build_feature_row  # noqa: E402

MODEL_PATH = ROOT / "05_policy" / "current" / "model_v4" / "national_residential_v4_full.joblib"

UNITS_BUCKETS = [(0, 1, "single home"), (2, 9, "2-9 homes"), (10, 19, "10-19 homes"), (20, 39, "20-39 homes"), (40, 79, "40-79 homes"), (80, 9999, "80+ homes")]


@lru_cache(maxsize=1)
def rate_tables() -> dict:
    cached = ROOT / "05_policy" / "current" / "rate_tables.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))

    from build_prospective_calibration_backtest import prepare  # noqa: E402

    df = prepare()
    df = df[df["target_refused"].notna()]
    units = pd.to_numeric(df["NumResidentialUnits"], errors="coerce")
    bucket_rates = df.groupby("application_bucket")["target_refused"].agg(["mean", "size"])
    council_bucket = df.groupby(["PlanningAuthority", "application_bucket"])["target_refused"].agg(["mean", "size"])
    units_bucket = {}
    for lo, hi, label in UNITS_BUCKETS:
        sel = df[(units >= lo) & (units <= hi)]
        if len(sel) >= 30:
            units_bucket[label] = {"rate": float(sel["target_refused"].mean()), "n": int(len(sel))}
    site_ha = pd.to_numeric(df["AreaofSite"], errors="coerce")
    density = np.divide(units, site_ha, out=np.full(len(df), np.nan), where=site_ha > 0)
    bands = {
        "low (below 35 homes/ha)": ((density < 35), None),
        "medium (35-50 homes/ha)": ((density >= 35) & (density <= 50), None),
        "high (above 50 homes/ha)": ((density > 50), None),
    }
    density_rates = {}
    for label, (mask, _) in bands.items():
        sel = df[mask]
        if len(sel) >= 30:
            density_rates[label] = {"rate": float(sel["target_refused"].mean()), "n": int(len(sel))}
    return {
        "bucket_rates": {k: {"rate": round(float(v["mean"]), 3), "n": int(v["size"])} for k, v in bucket_rates.iterrows()},
        "council_bucket_rates": {f"{a}__{b}": {"rate": round(float(v["mean"]), 3), "n": int(v["size"])} for (a, b), v in council_bucket.iterrows()},
        "units_bucket_rates": units_bucket,
        "density_band_rates": density_rates,
    }


def _units_label(units) -> str:
    for lo, hi, label in UNITS_BUCKETS:
        if units is not None and not pd.isna(units) and lo <= units <= hi:
            return label
    return ""


def plain_language(artifact, baseline: dict, mutated: dict) -> dict:
    decomposition = explain_delta(artifact, baseline, mutated)
    tables = rate_tables()
    groups = decomposition["group_contributions_logit"]
    delta_pp = decomposition["delta_probability_pp"]
    total = decomposition["total_logit_change"]
    share = lambda contribution: abs(contribution) / (abs(total) or 1.0)

    bullets = []
    b0 = build_feature_row(baseline).iloc[0]
    b1 = build_feature_row(mutated).iloc[0]
    auth = baseline["authority"]

    bucket0, bucket1 = str(b0["application_bucket"]), str(b1["application_bucket"])
    bucket_changed = bucket0 != bucket1
    if bucket_changed:
        r0 = tables["bucket_rates"].get(bucket0, {})
        r1 = tables["bucket_rates"].get(bucket1, {})
        c0 = tables["council_bucket_rates"].get(f"{auth}__{bucket0}")
        c1 = tables["council_bucket_rates"].get(f"{auth}__{bucket1}")
        if c0 is not None and c1 is not None and c0["n"] >= 30 and c1["n"] >= 30:
            context = f"in {auth}"
            p0, p1 = c0["rate"], c1["rate"]
        else:
            context = "across Ireland"
            p0, p1 = r0.get("rate"), r1.get("rate")
        if p0 is not None and p1 is not None:
            direction = "raises" if p1 >= p0 else "lowers"
            if abs(p1 - p0) < 0.01:
                rate_text = ""
            else:
                rate_text = (
                    f" {context}, {bucket1} applications are refused "
                    f"{p1 * 100:.0f}% of the time compared with {p0 * 100:.0f}% for {bucket0}."
                )
            bullets.append({
                "driver": "scheme size category",
                "direction": direction,
                "text": (
                    f"Changing the scheme moved it from the \u2018{bucket0}\u2019 category to "
                    f"\u2018{bucket1}\u2019.{rate_text}"
                ),
                "importance": round(share(groups.get("application type bucket", 0.0)), 3),
            })

    if not bucket_changed:
        u0, u1 = baseline.get("units"), mutated.get("units")
        if u0 != u1 and (u0 is not None) and (u1 is not None):
            l0, l1 = _units_label(float(u0)), _units_label(float(u1))
            r0 = tables["units_bucket_rates"].get(l0)
            r1 = tables["units_bucket_rates"].get(l1)
            if r0 and r1 and l0 != l1:
                direction = "raises" if r1["rate"] >= r0["rate"] else "lowers"
                bullets.append({
                    "driver": "development size",
                    "direction": direction,
                    "text": (
                        f"Smaller developments are refused more often than larger ones: {l1} schemes are "
                        f"refused {r1['rate'] * 100:.0f}% of the time, while {l0} schemes are refused "
                        f"{r0['rate'] * 100:.0f}%."
                    ),
                    "importance": round(share(groups.get("numeric: units count", 0.0) + groups.get("numeric: floor area", 0.0)), 3),
                })

    comp_keys = [k for k in groups if k.startswith("numeric: comparable")]
    comp_contribution = sum(groups[k] for k in comp_keys)
    if abs(comp_contribution) > 0.005:
        top5_0, top5_1 = float(b0["comp_top5_refusal_rate"]), float(b1["comp_top5_refusal_rate"])
        direction = "raises" if comp_contribution > 0 else "lowers"
        bullets.append({
            "driver": "similar past applications",
            "direction": direction,
            "text": (
                f"The most similar past applications to the revised scheme were refused "
                f"{top5_1 * 100:.0f}% of the time, compared with {top5_0 * 100:.0f}% for the original "
                f"scheme."
            ),
            "importance": round(share(comp_contribution), 3),
        })

    d0 = baseline.get("units") / (baseline.get("site_area_sqm") or np.nan) * 10000 if baseline.get("site_area_sqm") else None
    d1 = mutated.get("units") / (mutated.get("site_area_sqm") or np.nan) * 10000 if mutated.get("site_area_sqm") else None
    density_contribution = groups.get("numeric: density band 35-50/ha", 0.0) + groups.get("numeric: density band >50/ha", 0.0) + groups.get("numeric: density band <35/ha", 0.0) + groups.get("numeric: density (units/ha)", 0.0) + groups.get("numeric: floor area ratio", 0.0)
    if d0 is not None and d1 is not None and abs(d0 - d1) > 1 and abs(density_contribution) > 0.005:
        if d1 < 35:
            band = "low (below 35 homes/ha)"
        elif d1 <= 50:
            band = "medium (35-50 homes/ha)"
        else:
            band = "high (above 50 homes/ha)"
        rate = tables["density_band_rates"].get(band)
        direction = "raises" if density_contribution > 0 else "lowers"
        if rate is not None and ((rate["rate"] >= 0.13 and direction == "raises") or (rate["rate"] < 0.13 and direction == "lowers")):
            rate_text = f" Schemes at {band} density are refused {rate['rate'] * 100:.0f}% of the time."
        else:
            rate_text = ""
        bullets.append({
            "driver": "site density",
            "direction": direction,
            "text": (
                f"The revised scheme is {d1:.0f} homes per hectare (was {d0:.0f}), moving it into the "
                f"{band} density band.{rate_text}"
            ),
            "importance": round(share(density_contribution), 3),
        })

    flood_now = bool(b1.get("flood_any")) and bool(float(b1["flood_any"])) if pd.notna(b1.get("flood_any")) else False
    flood_before = bool(b0.get("flood_any")) and bool(float(b0["flood_any"])) if pd.notna(b0.get("flood_any")) else False
    if flood_now and not flood_before:
        bullets.append({
            "driver": "flood risk",
            "direction": "raises",
            "text": "The revised location falls within a mapped flood zone; flooding and drainage are among the most common refusal grounds nationally.",
            "importance": 0.1,
        })

    bullets = sorted(bullets, key=lambda b: -b["importance"])[:4]
    for b in bullets:
        b.pop("importance", None)
    from model_feature_builder import score_proposal  # noqa: E402

    p0_cal = score_proposal(baseline)["refusal_probability"]
    p1_cal = score_proposal(mutated)["refusal_probability"]
    delta_cal = (p1_cal - p0_cal) * 100
    verdict = "raise" if delta_cal >= 0 else "lower"
    return {
        "baseline_refusal_probability": round(p0_cal, 4),
        "scenario_refusal_probability": round(p1_cal, 4),
        "delta_pp": round(delta_cal, 2),
        "verdict": f"Overall, these changes {verdict} the refusal probability from {p0_cal * 100:.0f}% to {p1_cal * 100:.0f}%.",
        "explanations": bullets,
        "note": "Explanations are model-attributed sensitivity statements, not guaranteed outcomes.",
    }


def main() -> None:
    artifact = joblib.load(MODEL_PATH)
    baseline = {
        "authority": "Dun Laoghaire Rathdown County Council",
        "description": "construction of 12 no. apartments in a 4 storey block with car parking and associated site works",
        "units": 12,
        "site_area_sqm": 4000,
        "floor_area_sqm": 2400,
        "itm_easting": 722000,
        "itm_northing": 726500,
        "submission_year": 2026,
    }
    scenarios = {
        "fewer_units_8": {**baseline, "units": 8, "floor_area_sqm": 1600},
        "more_units_16": {**baseline, "units": 16, "floor_area_sqm": 3200},
        "smaller_site": {**baseline, "site_area_sqm": 2500},
        "one_off_house": {**baseline, "units": 1, "floor_area_sqm": 250, "description": "construction of a single dwelling house with garage"},
    }
    out = {}
    for name, mutated in scenarios.items():
        result = plain_language(artifact, baseline, mutated)
        out[name] = result
        print(f"===== {name} =====")
        print(result["verdict"])
        for bullet in result["explanations"]:
            print(f"  [{bullet['direction'].upper()}] {bullet['text']}")
        print()
    (OUT / "scenario_plain_explanations_v4.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("saved -> scenario_plain_explanations_v4.json")


if __name__ == "__main__":
    main()
