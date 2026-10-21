"""Seed the shadow log as of 2026-10-01 with state-machine v1 predictions.

For every clean-labelled scheme with a known current state, freeze the
next-transition empirical distribution (median + 50/80% intervals + 3/6/12m
probabilities) as a prospective prediction. Outcomes fill in as events are
observed later. Write-once by construction.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402
from devrisk.shadow import log_prediction, score_shadow  # noqa: E402

SILVER = settings.SILVER_DIR
SNAP = "2026-10-01T00:00:00+00:00"


def main() -> None:
    cur = pd.read_csv(SILVER / "state_machine" / "current_state.csv", dtype=str)
    transitions = json.loads((SILVER / "state_machine" / "transitions.json").read_text(encoding="utf-8"))
    clean = pd.read_csv(SILVER / "dq" / "labels_clean.csv", dtype=str)
    clean_keys = set(clean["case_key"])
    seeded = 0
    for _, row in cur.iterrows():
        key = row["case_key"]
        if key not in clean_keys:
            continue
        state = row["current_state"]
        nxt = row["next_possible_states"].split("|")
        for target in nxt:
            t = transitions.get(f"{state}->{target}")
            if not t or not t.get("n"):
                continue
            pred = {"median_days": t["median_days"],
                    "pct50_lower": t.get("pct50_lower"), "pct50_upper": t.get("pct50_upper"),
                    "pct80_lower": t.get("pct80_lower"), "pct80_upper": t.get("pct80_upper"),
                    "within_3m": t.get("within_3m"), "within_6m": t.get("within_6m"),
                    "within_12m": t.get("within_12m"),
                    "basis": "empirical transition table; not day-level precision"}
            snap = {"current_state": state, "days_in_state": row["days_in_state"],
                    "source": row["source"], "confidence": row["confidence"]}
            try:
                log_prediction(case_key=key, model_version="state_machine_v1",
                               state_at_prediction=state, target_transition=f"{state}->{target}",
                               prediction=pred, features_snapshot=snap,
                               source="state_machine_seed", timestamp=SNAP)
                seeded += 1
            except ValueError:
                continue
    print(json.dumps({"seeded_predictions": seeded, "scoring": score_shadow()}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
