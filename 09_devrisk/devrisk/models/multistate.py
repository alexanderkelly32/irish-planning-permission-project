"""Multi-state development timeline model (core module).

States: application -> decision -> final_permission (appeal/JR cleared) ->
pre_construction -> phase_commenced -> first_ccc -> units_completed ->
delivered (sale/rental/social).

Each transition is fit separately from the event ledger on train-era data:
  - occur(3/6/12/24m): stratified hazard-based probability
  - conditional duration distribution if it occurs (strata quantiles)
  - stall probability (no transition by censor / not_commenced / expiry)
Monte Carlo simulation chains transitions into a full timeline distribution.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

HORIZONS = [91, 183, 365, 730]
STATES = ["application", "decision", "final_permission", "pre_construction",
          "phase_commenced", "first_ccc", "units_completed", "delivered"]


def route_of(row: pd.Series) -> str:
    description = str(row.get("description") or "").lower()
    ahb = str(row.get("approved_housing_body") or "").strip().lower() in {"yes", "y", "true"}
    if ahb or "social housing" in description or "part v" in description or "turnkey" in description:
        return "social"
    if "build to rent" in description or "build-to-rent" in description or "private rental" in description or "prs" in description:
        return "rental"
    if "forward fund" in description or "forward-fund" in description:
        return "forward_funded"
    if "part v" in description and "social" in description:
        return "social"
    return "private_sale"


def fit_transition(frame: pd.DataFrame, duration_col: str, event_col: str, strata_cols: list[str]) -> dict:
    """Fit one transition: occurrence strata + conditional duration quantiles."""
    observed = frame[frame[event_col].astype(bool)].dropna(subset=[duration_col]).copy()
    observed = observed[observed[duration_col].between(0, 4000)]
    at_risk = frame.copy()
    at_risk["_event"] = at_risk[event_col].astype(bool) & at_risk[duration_col].notna()
    at_risk["_dur"] = pd.to_numeric(at_risk[duration_col], errors="coerce").where(at_risk["_event"], at_risk["censor_days"]).clip(lower=0)

    occ = {"overall": {str(h): round(float((at_risk["_dur"] <= h).mean()), 4) for h in HORIZONS}}
    for col in strata_cols:
        for value, part in at_risk.groupby(col, dropna=False):
            if len(part) < 15:
                continue
            occ[f"{col}={value}"] = {str(h): round(float((part["_dur"] <= h).mean()), 4) for h in HORIZONS}

    durations = {"overall": {
        "q10": round(float(observed[duration_col].quantile(0.1)), 0),
        "q50": round(float(observed[duration_col].quantile(0.5)), 0),
        "q90": round(float(observed[duration_col].quantile(0.9)), 0),
        "n": int(len(observed)),
    }}
    for col in strata_cols:
        for value, part in observed.groupby(col, dropna=False):
            if len(part) < 10:
                continue
            durations[f"{col}={value}"] = {
                "q10": round(float(part[duration_col].quantile(0.1)), 0),
                "q50": round(float(part[duration_col].quantile(0.5)), 0),
                "q90": round(float(part[duration_col].quantile(0.9)), 0),
                "n": int(len(part)),
            }
    return {"occurrence": occ, "duration_quantiles": durations}


def sample_duration(transition: dict, row: pd.Series, strata_cols: list[str], rng: np.random.Generator) -> float | None:
    """Sample a conditional duration for the transition given the scheme row."""
    quantiles = transition["duration_quantiles"]
    key = None
    for col in strata_cols:
        candidate = f"{col}={row.get(col)}"
        if candidate in quantiles:
            key = candidate
            break
    entry = quantiles.get(key, quantiles["overall"])
    q10, q50, q90 = entry["q10"], entry["q50"], entry["q90"]
    if entry["n"] < 5:
        return None
    # Piecewise-linear quantile interpolation for a continuous draw.
    u = rng.random()
    if u <= 0.1:
        return float(rng.uniform(0, q10))
    if u >= 0.9:
        return float(rng.uniform(q90, q90 * 1.5))
    return float(np.interp(u, [0.1, 0.5, 0.9], [q10, q50, q90]))


def simulate_timeline(row: pd.Series, transitions: dict, rng: np.random.Generator) -> dict[str, float]:
    """One Monte Carlo path through the state chain. Milestone days measured
    from submission (received date); each transition adds its own leg."""
    days = {"decision": None, "final_permission": None, "commencement": None,
            "first_ccc": None, "units_completed": None, "first_sale": None}
    d = 0.0
    decision = sample_duration(transitions["decision"], row, ["era", "authority"], rng)
    if decision is None:
        return days
    d += max(decision, 1.0)
    days["decision"] = d
    # final permission: appealed schemes only (sample the appeal-resolution
    # extra); non-appealed schemes add nothing.
    if bool(row.get("appeal_submitted")):
        appeal_extra = sample_duration(transitions["final_permission"], row, ["era"], rng)
        if appeal_extra is not None:
            d += appeal_extra
    days["final_permission"] = d
    # commencement: grant -> commencement (grant ~ decision date).
    if not transitions["commencement"].get("ever_rate", 0) > rng.random():
        return days
    start = sample_duration(transitions["commencement"], row, ["era", "band", "type"], rng)
    if start is None:
        return days
    d += start
    days["commencement"] = d
    # first CCC: commencement -> first CCC.
    build = sample_duration(transitions["first_ccc"], row, ["era", "band"], rng)
    if build is None:
        return days
    d += build
    days["first_ccc"] = d
    # units completed: first CCC -> final CCC.
    finish = sample_duration(transitions["units_completed"], row, ["era"], rng)
    if finish is not None:
        d += finish
    days["units_completed"] = d
    # first sale: final CCC -> first sale, route-specific.
    route = row.get("route", "private_sale")
    sale = sample_duration(transitions["first_sale"].get(route, transitions["first_sale"]["private_sale"]),
                           row, ["era"], rng)
    if sale is not None:
        days["first_sale"] = d + sale
    return days


def evaluate_paths(paths: list[dict[str, float]], frame: pd.DataFrame) -> dict:
    """Compare simulated milestone days against observed event days."""
    out = {}
    milestone_cols = {
        "decision": "decision_days", "commencement": "activation_days",
        "first_ccc": "first_ccc_days", "units_completed": "final_ccc_days",
        "first_sale": "first_sale_days",
    }
    for milestone, col in milestone_cols.items():
        observed = pd.to_numeric(frame[col], errors="coerce")
        evaluable = observed.notna() & observed.between(0, 4000)
        if evaluable.sum() < 10:
            continue
        preds = np.full((len(frame), len(paths[0])), np.nan)
        for i in range(len(frame)):
            for j, p in enumerate(paths[i]):
                value = p.get(milestone)
                if value is not None:
                    preds[i, j] = value
        med = np.nanmedian(preds, axis=1)[evaluable]
        lo = np.nanpercentile(preds, 10, axis=1)[evaluable]
        hi = np.nanpercentile(preds, 90, axis=1)[evaluable]
        y = observed[evaluable].to_numpy()
        mae = float(np.nanmean(np.abs(y - med)))
        coverage_80 = float(np.nanmean((y >= lo) & (y <= hi)))
        out[milestone] = {"n": int(evaluable.sum()), "mae_days": round(mae, 0), "coverage_80": round(coverage_80, 3)}
    return out
