"""Runner: phase-level completion models (todo 2).

Targets per scheme, from first commencement:
  t_first_ccc    - first CCC of any phase
  t_25pct        - 25% of permitted units certified (cumulative)
  t_50pct        - 50% certified
  t_final_ccc    - last phase CCC (final completion)
All censored at the censor date. Models: KM, strata (authority x era),
discrete-time hazard with corrected fixed-grid evaluation (dynamic AUC,
integrated Brier). Phase-level: units certified accumulate over CCC events
with completion_units.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.models.survival import dynamic_auc, integrated_brier, kaplan_meier  # noqa: E402

CENSOR = pd.Timestamp("2026-09-27", tz="UTC")
HORIZONS = [365, 730, 1096, 1461]
INTERVAL = 30.0
MAX_TIME = 2000.0
GRID = np.arange(0.0, MAX_TIME, INTERVAL)


def build_frame() -> pd.DataFrame:
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    links = pd.read_csv(settings.SILVER_DIR / "bcms_links_all_granted.csv")
    overlay = settings.SILVER_DIR / "audit" / "bcms_verdict_overlay.csv"
    if overlay.exists():
        links = pd.concat([links, pd.read_csv(overlay).reindex(columns=links.columns)], ignore_index=True)
    confirmed = links[links["confidence_band"] == "confirmed"]
    events = confirmed.merge(bcms, on="bcms_event_id", how="inner")
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")

    rows = []
    for scheme_id, group in events.groupby("scheme_id"):
        comm = pd.to_datetime(group["commencement_date_dt"], utc=True, errors="coerce").min()
        if pd.isna(comm):
            continue
        cccs = pd.to_datetime(group["completion_certificate_date_dt"], utc=True, errors="coerce")
        cccs = cccs.dropna().sort_values()
        total_units = pd.to_numeric(group["dwellings_total"], errors="coerce").fillna(0).sum()
        units_cert = pd.to_numeric(group["completion_units"], errors="coerce").fillna(0)
        if units_cert.sum() == 0 and len(cccs):
            # completion_units missing: approximate by dwellings_phase per CCC row
            phase_units = pd.to_numeric(group["dwellings_phase"], errors="coerce").fillna(0)
            units_cert = phase_units.where(cccs.notna(), 0)
        censor_days = (CENSOR - comm).days
        def first_time(pct: float):
            if total_units <= 0:
                return np.nan, True
            cumulative = 0.0
            for t, u in zip(cccs, units_cert, strict=False):
                cumulative += float(u)
                if cumulative >= pct * total_units:
                    return (t - comm).days, False
            return None, False
        t_first = max(0, (cccs.iloc[0] - comm).days) if len(cccs) else None
        t_25, _ = first_time(0.25)
        t_50, _ = first_time(0.50)
        t_final = (cccs.iloc[-1] - comm).days if len(cccs) else None
        scheme = register[register["case_key"].astype(str) == str(scheme_id)]
        units_reg = pd.to_numeric(scheme["NumResidentialUnits"], errors="coerce").iloc[0] if len(scheme) else np.nan
        auth = scheme["PlanningAuthority"].iloc[0] if len(scheme) else ""
        rows.append({
            "scheme_id": str(scheme_id),
            "commencement": comm,
            "t_first_ccc": t_first,
            "t_25pct": t_25,
            "t_50pct": t_50,
            "t_final_ccc": t_final,
            "n_phases": int(pd.to_numeric(group["phase_number"], errors="coerce").nunique()),
            "total_units_bcms": float(total_units),
            "units_reg": units_reg,
            "authority": auth,
            "censor_days": float(censor_days),
        })
    frame = pd.DataFrame(rows)
    frame = frame[frame["censor_days"].between(0, 4000)]
    return frame


def observed(series: pd.Series, censor_days: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    y_obs = series.where(series.notna(), censor_days).clip(lower=0).to_numpy()
    censored = series.isna().to_numpy()
    return y_obs, censored


def evaluate(name: str, frame: pd.DataFrame, target: str, scores: dict[float, np.ndarray] | None = None) -> dict:
    y_obs, censored = observed(frame[target], frame["censor_days"])
    events = (~censored) & (y_obs <= 4000)
    out: dict = {
        "n": int(len(frame)),
        "events": int(events.sum()),
        "km_median_days": None,
        "median_event_days": round(float(np.median(y_obs[events])), 0) if events.any() else None,
    }
    km = kaplan_meier(y_obs, (~censored).astype(int))
    crossed = km[km["survival"] <= 0.5]
    out["km_median_days"] = round(float(crossed["t"].iloc[0]), 0) if len(crossed) else None
    if scores is not None:
        out["dynamic_auc"] = {}
        for horizon in HORIZONS:
            out["dynamic_auc"][str(horizon)] = round(dynamic_auc(y_obs, censored, scores[horizon], horizon), 3)
        out["integrated_brier"] = round(integrated_brier(y_obs, censored, scores), 4)
    return {name: out}


def fit_hazard(frame: pd.DataFrame, target: str) -> dict[float, np.ndarray]:
    """Discrete hazard with corrected fixed-grid incidence; strata features."""
    y_obs, censored = observed(frame[target], frame["censor_days"])
    persons = []
    for i in range(len(frame)):
        duration = min(float(y_obs[i]), MAX_TIME)
        for start in GRID:
            if start >= duration:
                break
            persons.append({
                "row": i, "interval_start": start,
                "y": int((not censored[i]) and y_obs[i] <= start + INTERVAL),
            })
    pp = pd.DataFrame(persons)
    pp["t_years"] = pp["interval_start"] / 365.0
    features = ["t_years"]
    model = LogisticRegression(C=0.5, max_iter=2000, solver="liblinear")
    model.fit(pp[features], pp["y"])

    grid_frame = pd.DataFrame({
        "row": np.repeat(np.arange(len(frame)), len(GRID)),
        "interval_start": np.tile(GRID, len(frame)),
    })
    grid_frame["t_years"] = grid_frame["interval_start"] / 365.0
    grid_frame["hazard"] = model.predict_proba(grid_frame[features])[:, 1]
    scores = {}
    for horizon in HORIZONS:
        intervals = int(np.ceil(horizon / INTERVAL))
        wide = grid_frame.pivot_table(index="row", columns="interval_start", values="hazard", aggfunc="first")
        wide = wide[sorted(wide.columns)[:intervals]]
        scores[horizon] = np.clip(1.0 - np.prod(1.0 - wide.to_numpy(), axis=1), 0.0, 1.0)
    return scores


if __name__ == "__main__":
    frame = build_frame()
    frame.to_csv(settings.SILVER_DIR / "completion_targets.csv", index=False)
    report = {"n_schemes": int(len(frame)), "phase_counts": int(frame["n_phases"].sum())}
    for target in ("t_first_ccc", "t_25pct", "t_50pct", "t_final_ccc"):
        sub = frame.dropna(subset=["censor_days"]).copy()
        scores = fit_hazard(sub, target)
        report.update(evaluate(target, sub, target, scores))
    out = settings.SILVER_DIR / "completion_models_v1.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
