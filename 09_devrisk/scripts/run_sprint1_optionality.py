"""Sprint 1: Planning Optionality Surface, Efficient Frontier, Fragility
Index, Planning Greeks.

All four built on the FROZEN v4-full refusal model as a local response
surface. Perturbations: units multipliers (fixed site area -> density),
apartment/house mix toggle, scale band (via units). Per-scheme gradient,
curvature, robust/cliff regions, fragility class; aggregates for the
frontier and greeks; historical validation vs Decision/FI where held.

MODEL-IMPLIED SCENARIO SENSITIVITIES ONLY - not causal.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devrisk import settings  # noqa: E402
from devrisk.models.planning_adapter import proposal_from_application, score_planning  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "sprint1"
OUT.mkdir(parents=True, exist_ok=True)

UNIT_MULTS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]


def toggle_mix(desc: str) -> str | None:
    low = (desc or "").lower()
    if "apartment" in low or "duplex" in low:
        return (desc.replace("apartments", "dwellings").replace("apartment", "dwelling")
                .replace("duplex units", "dwellings").replace("duplex", "dwelling"))
    return f"{desc} (developed as apartments)"


def main() -> None:
    rng = np.random.default_rng(7)
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                               columns=["case_key", "PlanningAuthority", "DevelopmentDescription",
                                        "NumResidentialUnits", "AreaofSite", "FloorArea",
                                        "ITMEasting", "ITMNorthing", "ReceivedDate",
                                        "Decision", "FIRequestDate"])
    register = register.drop_duplicates("case_key")
    register["units"] = pd.to_numeric(register["NumResidentialUnits"], errors="coerce")
    register["site_area"] = pd.to_numeric(register["AreaofSite"], errors="coerce")
    register["floor_area"] = pd.to_numeric(register["FloorArea"], errors="coerce")
    register["recv_year"] = pd.to_datetime(register["ReceivedDate"], utc=True,
                                           errors="coerce").dt.tz_localize(None).dt.year
    base = register.dropna(subset=["units", "site_area", "ITMEasting", "ITMNorthing"])
    base = base[(base["units"] >= 5) & (base["site_area"] >= 200) & (base["recv_year"] >= 2018)]
    sample = base.sample(min(100, len(base)), random_state=42)

    rows = []
    for _, r in sample.iterrows():
        for mult in UNIT_MULTS:
            units = max(int(round(r["units"] * mult)), 1)
            for mix_name, desc in [("as_submitted", r["DevelopmentDescription"]),
                                   ("mix_toggled", toggle_mix(r["DevelopmentDescription"]))]:
                if desc is None:
                    continue
                proposal = proposal_from_application(
                    authority=r["PlanningAuthority"], description=desc, units=units,
                    site_area_sqm=float(r["site_area"]),
                    floor_area_sqm=float(r["floor_area"]) if pd.notna(r["floor_area"]) else None,
                    itm_easting=float(r["ITMEasting"]), itm_northing=float(r["ITMNorthing"]),
                    submission_year=int(r["recv_year"]))
                try:
                    out = score_planning(proposal)
                except Exception:
                    continue
                rows.append({"case_key": r["case_key"], "units_mult": mult,
                             "units": units, "mix": mix_name,
                             "refusal_probability": out["refusal_probability"],
                             "risk_band": out["risk_band"],
                             "decision": r["Decision"], "fi": pd.notna(r["FIRequestDate"])})
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT / "optionality_surface.csv", index=False)

    per_scheme = []
    for key, g in frame[frame["mix"] == "as_submitted"].groupby("case_key"):
        g = g.sort_values("units")
        p = g["refusal_probability"].to_numpy()
        u = g["units"].to_numpy()
        du = np.diff(u)
        grad = np.diff(p) / np.where(du == 0, 1, du) * 10.0
        curv = np.diff(grad) if len(grad) > 1 else np.array([0.0])
        bands = g["risk_band"].to_numpy()
        band_idx = {"low": 0, "medium": 1, "high": 2}
        band_levels = np.array([band_idx.get(b, 0) for b in bands])
        crossings = int((np.diff(band_levels) > 0).sum())
        robust_span = u[band_levels == 0].max() - u[band_levels == 0].min() if (band_levels == 0).any() else 0
        max_grad = float(np.max(np.abs(grad))) if len(grad) else 0.0
        max_curv = float(np.max(np.abs(curv))) if len(curv) else 0.0
        spread = float(np.ptp(p))
        if max_grad >= 2.5 or crossings >= 2:
            frag = "fragile"
        elif max_grad >= 1.0 or crossings == 1:
            frag = "moderately_sensitive"
        else:
            frag = "robust"
        per_scheme.append({"case_key": key, "max_gradient_per_10units": round(max_grad, 3),
                           "max_curvature": round(max_curv, 3), "band_crossings": crossings,
                           "robust_span_units": int(robust_span), "p_range": round(spread, 3),
                           "fragility": frag,
                           "decision": g["decision"].iloc[0], "fi": g["fi"].iloc[0],
                           "base_units": int(u[len(u) // 2])})
    ps = pd.DataFrame(per_scheme)
    ps.to_csv(OUT / "fragility.csv", index=False)

    frontier = {}
    for mult in UNIT_MULTS:
        sub = frame[(frame["mix"] == "as_submitted") & (frame["units_mult"] == mult)]
        frontier[f"units_mult_{mult}"] = {
            "n": int(len(sub)), "median_p": round(float(sub["refusal_probability"].median()), 4),
            "p25": round(float(sub["refusal_probability"].quantile(0.25)), 4),
            "p75": round(float(sub["refusal_probability"].quantile(0.75)), 4),
            "pct_high_band": round(float((sub["risk_band"] == "high").mean() * 100), 1),
        }
    med_units = sample["units"].median()
    marginal = {}
    p_med = {m: frame[(frame["units_mult"] == m) & (frame["mix"] == "as_submitted")]
             ["refusal_probability"].median() for m in UNIT_MULTS}
    for label, m_lo, m_hi in [("+5 units", 1.0, 1.25), ("+10 units", 1.0, 1.5), ("+20 units", 1.0, 2.0)]:
        marginal[label] = round(float(p_med[m_hi] - p_med[m_lo]), 4)

    greeks = {"median_units": float(med_units), "delta_p_by_units_mult": {m: round(v, 4) for m, v in p_med.items()},
              "marginal_risk": marginal}
    grads = ps["max_gradient_per_10units"]
    greeks["gradient_distribution"] = {"p10": round(float(grads.quantile(0.1)), 3),
                                       "p50": round(float(grads.median()), 3),
                                       "p90": round(float(grads.quantile(0.9)), 3)}

    outcome = {}
    for frag in ["robust", "moderately_sensitive", "fragile"]:
        sub = ps[ps["fragility"] == frag]
        if len(sub):
            refused = sub["decision"].fillna("").str.lower().str.contains("refus")
            outcome[frag] = {"n": int(len(sub)),
                             "refused_rate": round(float(refused.mean() * 100), 1),
                             "fi_rate": round(float(sub["fi"].mean() * 100), 1)}
    report = {"n_schemes": int(len(ps)), "frontier": frontier, "greeks": greeks,
              "fragility_outcomes": outcome,
              "caveat": "model-implied scenario sensitivities; NOT causal"}
    (OUT / "sprint1_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
