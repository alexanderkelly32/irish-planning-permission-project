#!/usr/bin/env python3
"""New-build money facts: refusal rates, delay costs and model lift for 10+ unit schemes."""
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

ARTIFACT = ROOT / "05_policy" / "current" / "model_v4" / "national_residential_v4_full.joblib"


def main() -> None:
    from build_prospective_calibration_backtest import prepare  # noqa: E402

    df = prepare()
    df = df[df["target_refused"].notna()].copy()
    units = pd.to_numeric(df["NumResidentialUnits"], errors="coerce")
    ge10 = df[units >= 10].copy()
    ge10["units"] = units[units >= 10]
    site_ha = pd.to_numeric(ge10["AreaofSite"], errors="coerce")
    ge10["density"] = np.divide(ge10["units"], site_ha, out=np.full(len(ge10), np.nan), where=site_ha > 0)

    facts: dict[str, object] = {"national_ge10_refusal_rate": round(float(ge10["target_refused"].mean()), 4), "ge10_n": int(len(ge10))}

    by_units = {}
    for label, lo, hi in (("10-19", 10, 19), ("20-39", 20, 39), ("40-79", 40, 79), ("80+", 80, 99999)):
        sel = ge10[(ge10["units"] >= lo) & (ge10["units"] <= hi)]
        if len(sel) >= 50:
            by_units[label] = {"refusal_rate": round(float(sel["target_refused"].mean()), 4), "n": int(len(sel))}
    facts["refusal_by_units_band"] = by_units

    by_density = {}
    for label, mask in (("low <35/ha", ge10["density"] < 35), ("mid 35-50/ha", (ge10["density"] >= 35) & (ge10["density"] <= 50)), ("high >50/ha", ge10["density"] > 50)):
        sel = ge10[mask]
        if len(sel) >= 30:
            by_density[label] = {"refusal_rate": round(float(sel["target_refused"].mean()), 4), "n": int(len(sel))}
    facts["refusal_by_density_band"] = by_density

    ge10_dates = ge10.copy()
    ge10_dates["decided"] = pd.to_datetime(ge10_dates["DecisionDate"], utc=True, errors="coerce")
    ge10_dates["received"] = pd.to_datetime(ge10_dates["ReceivedDate"], utc=True, errors="coerce")
    ge10_dates["months"] = (ge10_dates["decided"] - ge10_dates["received"]).dt.days / 30.44
    delay = {}
    for label, mask in (("refused", ge10_dates["target_refused"] == 1), ("granted", ge10_dates["target_refused"] == 0)):
        months = ge10_dates.loc[mask, "months"].dropna()
        months = months[(months > 0) & (months < 200)]
        if len(months) >= 30:
            delay[label] = {"median_months": round(float(months.median()), 1), "n": int(len(months))}
    facts["decision_delay_months"] = delay

    words = ge10["DevelopmentDescription"].fillna("").astype(str).str.split().str.len()
    facts["description_words"] = {
        "refused_median": round(float(words[ge10["target_refused"] == 1].median()), 1),
        "granted_median": round(float(words[ge10["target_refused"] == 0].median()), 1),
    }

    desc = ge10["DevelopmentDescription"].fillna("").astype(str).str.lower()
    timber = ge10[desc.str.contains(r"timber", regex=True)]
    masonry = ge10[desc.str.contains(r"\b(?:masonry|brick|render)\b", regex=True)]
    if len(timber) >= 30 and len(masonry) >= 30:
        facts["timber_vs_masonry_ge10"] = {
            "timber": {"refusal_rate": round(float(timber["target_refused"].mean()), 4), "n": int(len(timber))},
            "masonry": {"refusal_rate": round(float(masonry["target_refused"].mean()), 4), "n": int(len(masonry))},
        }

    print("model lift on 2024+2025 GE10...", flush=True)
    data, train, test, y = build_data()
    artifact = joblib.load(ARTIFACT)
    ranking = artifact["ranking_model"]
    ge10_test = test[test["units"] >= 10].copy()
    p = ranking.predict_proba(ge10_test[artifact["feature_columns"]])[:, 1]
    ge10_test["risk"] = p
    quintile = pd.qcut(ge10_test["risk"], 5, labels=False)
    lift = {}
    for q in range(5):
        mask = quintile == q
        lift[f"q{q + 1}"] = {
            "refusal_rate": round(float(ge10_test.loc[mask, "target_refused"].mean()), 4),
            "n": int(mask.sum()),
        }
    facts["model_lift_ge10_2024_25"] = {
        "n": int(len(ge10_test)),
        "base_rate": round(float(ge10_test["target_refused"].mean()), 4),
        "by_risk_quintile": lift,
    }

    (OUT / "newbuild_money_facts.json").write_text(json.dumps(facts, indent=2), encoding="utf-8")
    print(json.dumps(facts, indent=2))


if __name__ == "__main__":
    main()
