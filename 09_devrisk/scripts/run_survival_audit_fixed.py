"""Runner: survival pipeline re-audit with the fixed evaluation.

Fixed grid incidence, IPCW dynamic AUC, integrated Brier. Intercept-only
hazard must now land at ~0.5 AUC. Then a one-feature hazard (units) is
compared against KM as the honest baseline.
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
from devrisk.models.survival import (  # noqa: E402
    dynamic_auc,
    integrated_brier,
    kaplan_meier,
    predict_cumulative_incidence,
)

CENSOR = pd.Timestamp("2026-09-27", tz="UTC")
HORIZONS = [365, 730, 1096]
INTERVAL = 30.0
MAX_TIME = 2000.0
GRID = np.arange(0.0, MAX_TIME, INTERVAL)


def build_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    frame = labels.merge(register[["case_key", "PlanningAuthority", "GrantDate", "DevelopmentDescription",
                                   "NumResidentialUnits", "AreaofSite"]], on="case_key", how="inner")
    frame["grant_dt"] = pd.to_datetime(frame["GrantDate"], utc=True, errors="coerce")
    frame["activation"] = pd.to_numeric(frame["activation_days"], errors="coerce").clip(lower=0)
    frame = frame.dropna(subset=["grant_dt"])
    frame = frame[frame["grant_dt"] < CENSOR - pd.Timedelta(days=180)]
    frame["y_obs"] = np.where(frame["activation"].notna(), frame["activation"],
                              (CENSOR - frame["grant_dt"]).dt.days)
    frame["censored"] = frame["activation"].isna()
    frame["log_units"] = np.log1p(pd.to_numeric(frame["NumResidentialUnits"], errors="coerce").fillna(0))
    return (frame[frame["grant_dt"] < pd.Timestamp("2020-01-01", tz="UTC")],
            frame[frame["grant_dt"] >= pd.Timestamp("2020-01-01", tz="UTC")])


def person_periods(part: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, scheme in part.iterrows():
        duration = min(float(scheme["y_obs"]), MAX_TIME)
        for start in GRID:
            if start >= duration:
                break
            end = min(start + INTERVAL, duration)
            y = int((~scheme["censored"]) and scheme["y_obs"] <= start + INTERVAL)
            rows.append({"scheme_id": scheme["case_key"], "interval_start": start, "y": y,
                         "log_units": scheme["log_units"], "t_years": start / 365.0})
            if y:
                break
    return pd.DataFrame(rows)


def fixed_grid_incidence(model, frame: pd.DataFrame, features: list[str], horizons: list[int]) -> dict[float, np.ndarray]:
    """Per-scheme P(T<=h) on the FIXED grid - the corrected evaluation."""
    schemes = frame[["case_key"]].drop_duplicates()
    grid_frame = pd.DataFrame({
        "case_key": np.repeat(schemes["case_key"].to_numpy(), len(GRID)),
        "interval_start": np.tile(GRID, len(schemes)),
    })
    grid_frame = grid_frame.merge(frame[["case_key"] + [f for f in features if f != "t_years"]].drop_duplicates(), on="case_key", how="left")
    grid_frame["t_years"] = grid_frame["interval_start"] / 365.0
    grid_frame["hazard"] = model.predict_proba(grid_frame[features].to_numpy())[:, 1]
    out: dict[float, np.ndarray] = {}
    for horizon in horizons:
        intervals = int(np.ceil(horizon / INTERVAL))
        wide = grid_frame.pivot_table(index="case_key", columns="interval_start", values="hazard", aggfunc="first")
        wide = wide[sorted(wide.columns)[:intervals]]
        values = wide.to_numpy()
        incidence = 1.0 - np.prod(1.0 - values, axis=1)
        out[horizon] = np.clip(incidence, 0.0, 1.0)
    return out


if __name__ == "__main__":
    train, test = build_data()
    report = {"n": {"train": int(len(train)), "test": int(len(test))}}

    for name, features in (("intercept_only", ["t_years"]), ("units", ["t_years", "log_units"])):
        pp_train = person_periods(train)
        model = LogisticRegression(C=1e9, max_iter=2000, solver="liblinear")
        model.fit(pp_train[features], pp_train["y"])
        scores = fixed_grid_incidence(model, test, features, HORIZONS)
        report[name] = {}
        for horizon in HORIZONS:
            report[name][str(horizon)] = round(
                dynamic_auc(test["y_obs"].to_numpy(), test["censored"].to_numpy(dtype=bool), scores[horizon], horizon), 3)
        report[name]["integrated_brier"] = round(
            integrated_brier(test["y_obs"].to_numpy(), test["censored"].to_numpy(dtype=bool), scores), 4)

    km = kaplan_meier(train["y_obs"].to_numpy(), (~train["censored"]).astype(int).to_numpy())
    km_probs = {str(h): round(float(1.0 - km[km["t"] <= h]["survival"].iloc[-1]), 4) if len(km[km["t"] <= h]) else 0.0 for h in HORIZONS}
    report["km_train_event_probs"] = km_probs

    out = settings.SILVER_DIR / "survival_audit_fixed.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
