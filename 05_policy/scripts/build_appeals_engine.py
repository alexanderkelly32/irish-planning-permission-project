#!/usr/bin/env python3
"""Ultimate-permission engine: P(permission eventually | refused), using appeal outcomes."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "old_original_attempt" / "first_attempt_messy" / "irish_planning_dataset_clean_model.parquet"
OUTPUT_DIR = ROOT / "05_policy" / "current"

GRANT_MARKERS = ("grant", "conditional", "attach", "amend", "modified", "split", "to attach")
REFUSE_MARKERS = ("refuse", "refused", "dismiss")
EXCLUDE_MARKERS = ("withdraw", "invalid", "quashed", "leave to appeal")

FEATURES = ["received_year", "log_units", "authority_ordinal", "units_missing"]


def resolve_ultimate(value: object) -> str | None:
    text = str(value or "").lower()
    if any(marker in text for marker in EXCLUDE_MARKERS):
        return None
    if any(marker in text for marker in GRANT_MARKERS):
        return "GRANTED"
    if any(marker in text for marker in REFUSE_MARKERS):
        return "REFUSED"
    return None


def prepare() -> pd.DataFrame:
    frame = pd.read_parquet(RAW, columns=[
        "PlanningAuthority", "NumResidentialUnits", "ReceivedDate", "Decision", "AppealDecision",
    ])
    frame = frame[frame["Decision"].fillna("").astype(str).str.upper().str.contains("REFUS")].copy()
    frame["ultimate"] = frame["AppealDecision"].map(resolve_ultimate)
    frame = frame[frame["ultimate"].notna()].copy()
    frame["received_year"] = pd.to_datetime(frame["ReceivedDate"], utc=True, errors="coerce").dt.year
    frame = frame[frame["received_year"].notna()].copy()
    units = pd.to_numeric(frame["NumResidentialUnits"], errors="coerce")
    frame["log_units"] = np.log1p(units.clip(lower=0))
    frame["units_missing"] = units.isna().astype(int)
    frame["authority_ordinal"] = pd.factorize(frame["PlanningAuthority"].fillna(""))[0]
    frame["target_ultimate_granted"] = frame["ultimate"].eq("GRANTED").astype(int)
    return frame.dropna(subset=["log_units"])


def main() -> None:
    data = prepare()
    train = data[data["received_year"] < 2025]
    test = data[data["received_year"] >= 2025]
    model = Pipeline([
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(max_iter=2000, class_weight="balanced")),
    ])
    model.fit(train[FEATURES], train["target_ultimate_granted"])
    probabilities = model.predict_proba(test[FEATURES])[:, 1]
    y = test["target_ultimate_granted"]
    clipped = np.clip(probabilities, 1e-6, 1 - 1e-6)
    results = {
        "model_version": "ultimate_permission_candidate_2026-09-09",
        "definition": "P(permission eventually obtained | local authority refused), from appeal outcomes.",
        "train_n": int(len(train)),
        "test_n": int(len(test)),
        "test_years": [int(test["received_year"].min()), int(test["received_year"].max())],
        "test_grant_rate": round(float(y.mean()), 4),
        "roc_auc": round(float(roc_auc_score(y, clipped)), 4) if y.nunique() == 2 else None,
        "average_precision": round(float(average_precision_score(y, clipped)), 4) if y.nunique() == 2 else None,
        "brier": round(float(brier_score_loss(y, clipped)), 4),
        "log_loss": round(float(log_loss(y, clipped, labels=[0, 1])), 4),
        "caveats": [
            "Candidate only; refusals that never appealed are excluded by design.",
            "Split decisions (part grant/part refuse) count as granted for part of the scheme.",
            "Not yet a product claim; keep separate from the local-authority engines.",
        ],
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "raw_planning_appeals_engine_2026-09-09.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
