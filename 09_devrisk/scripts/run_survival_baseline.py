"""Runner: baseline survival readout on pilot activation labels.

Kaplan-Meier overall and by size band / COVID exposure. This is a research
baseline (brief section 15.3): no calibrated product probability is implied.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.models.survival import kaplan_meier, km_probability_by, median_survival_time  # noqa: E402

if __name__ == "__main__":
    labels = pd.read_csv(settings.SILVER_DIR / "activation_labels_pilot.csv")
    labels = labels[labels["eligible"]].copy()
    durations = labels["duration_days"].fillna(
        (pd.to_datetime(labels["last_observation_date"], utc=True) - pd.to_datetime(labels["start_date"], utc=True)).dt.days
    ).clip(lower=0)
    events = labels["event_observed"].fillna(0).astype(int)

    report = {"n_eligible": int(len(labels)), "n_events": int(events.sum())}
    overall = kaplan_meier(durations.to_numpy(), events.to_numpy())
    report["overall"] = {
        "median_days": median_survival_time(overall),
        "p_event_by_12m": round(km_probability_by(overall, 365), 3),
        "p_event_by_24m": round(km_probability_by(overall, 730), 3),
        "p_event_by_36m": round(km_probability_by(overall, 1096), 3),
    }
    strata = {}
    pilot = pd.read_parquet(settings.SILVER_DIR / "pilot_candidates_100.parquet")
    band_map = pilot.set_index("case_key")["size_band"].to_dict()
    covid_map = pilot.set_index("case_key")["covid_materially_exposed"].to_dict()
    labels["size_band"] = labels["scheme_id"].map(band_map)
    labels["covid"] = labels["scheme_id"].map(covid_map)
    for name, group in [("size_band", labels["size_band"]), ("covid", labels["covid"])]:
        strata[name] = {}
        for value, part in labels.groupby(name, dropna=False):
            key = str(value)
            sub = part[part["eligible"]]
            sub_durations = sub["duration_days"].fillna(
                (pd.to_datetime(sub["last_observation_date"], utc=True) - pd.to_datetime(sub["start_date"], utc=True)).dt.days
            ).clip(lower=0)
            sub_events = sub["event_observed"].fillna(0).astype(int)
            table = kaplan_meier(sub_durations.to_numpy(), sub_events.to_numpy())
            strata[name][key] = {
                "n": int(len(sub)),
                "events": int(sub_events.sum()),
                "median_days": median_survival_time(table),
                "p_event_by_24m": round(km_probability_by(table, 730), 3),
            }
    report["strata"] = strata
    out = settings.SILVER_DIR / "survival_baseline_pilot.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
