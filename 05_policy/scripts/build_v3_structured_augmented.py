#!/usr/bin/env python3
"""v3b candidate: v3 architecture with structured value tokens injected into
the description text.

Why plain v3 cannot feel alterations: it only ever saw free-text descriptions,
where storeys/units/height phrasing is rare and noisy, so it learned no weight
on those signals. v3b appends tokenised structured values (from planner reports
and the GE10 extraction) to every description where they exist, retrains the
same pipeline, and re-ranks the 2025 holdout against the frozen baseline.

If v3b (a) holds ranking performance and (b) responds sensibly to structured
token mutations, it is the candidate for "alter X -> modelled % change" on a
v3-family instrument.

Output: raw_planning_v3b_structured_augmented.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "05_policy" / "current"

sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from build_comparable_feature_experiment import COMPARABLE_FEATURES_PATH, V3_FEATURES  # noqa: E402
from build_national_residential_model_v2 import TRAIN_CUTOFF, load_data_with_history  # noqa: E402
from build_spatial_history_feature_experiment import build_scaled_pipeline  # noqa: E402
from structured_optimiser_v5 import dedupe_reports, load_planner_reports  # noqa: E402

sys.path.insert(0, str(ROOT / "06_copilot" / "scripts"))
from precedent_copilot_logic import clean_text  # noqa: E402


def token_storeys(value: float) -> str:
    return f"sst_{int(round(value))}"


def token_units(value: float) -> str:
    bucket = int(round(float(value) / 5.0)) * 5
    return f"sun_{bucket}"


def token_parking(value: float) -> str:
    bucket = int(round(float(value) / 5.0)) * 5
    return f"spk_{bucket}"


def token_height(value: float) -> str:
    return f"sht_{round(float(value) * 2) / 2:g}"


def token_access(value: float) -> str:
    return f"sac_{int(round(value))}"


def token_separation(value: float) -> str:
    return f"ssep_{int(round(value))}"


def augment_description(description: str, tokens: list[str]) -> str:
    extra = " ".join(tokens)
    if not extra:
        return description
    return f"{description} [structured {extra}]"


def build_join_values(data: pd.DataFrame) -> pd.DataFrame:
    reports = dedupe_reports(load_planner_reports())
    keys = data[["case_key", "PlanningAuthority", "ApplicationNumber"]].copy()
    keys["app_number"] = keys["ApplicationNumber"].fillna("").astype(str).str.strip()
    keys["_authority"] = keys["PlanningAuthority"]
    joined = keys.merge(reports, on=["_authority", "app_number"], how="left")
    joined = joined.drop(columns=["_authority", "app_number"])
    values = joined.set_index(data.index)
    for column in ["report_storeys", "report_parking_spaces", "report_max_height_m",
                   "report_vehicular_access_points", "report_nearest_dwelling_separation_m"]:
        if column not in values.columns:
            values[column] = np.nan
    return values


def structured_tokens(row: pd.Series, units: float | None) -> list[str]:
    tokens = []
    if pd.notna(row.get("report_storeys")):
        tokens.append(token_storeys(float(row["report_storeys"])))
    if units is not None:
        tokens.append(token_units(units))
    if pd.notna(row.get("report_parking_spaces")):
        tokens.append(token_parking(float(row["report_parking_spaces"])))
    if pd.notna(row.get("report_max_height_m")):
        tokens.append(token_height(float(row["report_max_height_m"])))
    if pd.notna(row.get("report_vehicular_access_points")):
        tokens.append(token_access(float(row["report_vehicular_access_points"])))
    if pd.notna(row.get("report_nearest_dwelling_separation_m")):
        tokens.append(token_separation(float(row["report_nearest_dwelling_separation_m"])))
    return tokens


def mutate_tokens(description: str, field: str, delta: float) -> str | None:
    prefixes = {
        "storeys": "sst_", "units": "sun_", "parking": "spk_",
        "height": "sht_", "access": "sac_",
    }
    prefix = prefixes[field]
    parts = description.split(" ")
    changed = False
    out = []
    for part in parts:
        if part.startswith(prefix):
            try:
                value = float(part[len(prefix):])
            except ValueError:
                out.append(part)
                continue
            if field in {"storeys", "access"}:
                new_value = int(round(value + delta))
            elif field == "units":
                new_value = int(round((value + delta) / 5.0)) * 5
            elif field == "parking":
                new_value = int(round((value + delta) / 5.0)) * 5
            else:
                new_value = round(value + delta, 1)
            out.append(f"{prefix}{new_value:g}")
            changed = True
        else:
            out.append(part)
    return " ".join(out) if changed else None


def main() -> None:
    data = load_data_with_history().reset_index(drop=True)
    comparable = pd.read_parquet(COMPARABLE_FEATURES_PATH)
    data = data.merge(comparable, on="case_key", how="left")
    joined_values = build_join_values(data)

    data["description_stripped"] = data["description_stripped"].fillna("").astype(str).map(clean_text)
    for index, row in data.iterrows():
        units = pd.to_numeric(row.get("units_total_best"), errors="coerce")
        units_value = float(units) if pd.notna(units) else None
        tokens = structured_tokens(joined_values.loc[index], units_value)
        if tokens:
            data.at[index, "description_stripped"] = augment_description(data.at[index, "description_stripped"], tokens)

    train = data[data["received_date_dt"] < TRAIN_CUTOFF].copy()
    test = data[data["received_date_dt"] >= TRAIN_CUTOFF].copy()
    features = V3_FEATURES

    model = build_scaled_pipeline(V3_FEATURES[3:])
    model.fit(train[features], train["target_refused"])
    p = model.predict_proba(test[features])[:, 1]

    results = {
        "candidate": "v3b_structured_augmented_2026-09-14",
        "definition": "v3 architecture retrained with tokenised structured values (storeys/units/parking/height/access/separation) appended to descriptions where known; mutation sensitivity via token rewriting.",
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "test_refusal_rate": round(float(test["target_refused"].mean()), 4),
        "rows_with_any_token_train": int(train["description_stripped"].str.contains("[structured", regex=False).sum()),
        "rows_with_any_token_test": int(test["description_stripped"].str.contains("[structured", regex=False).sum()),
        "holdout_ranking": {
            "roc_auc": round(float(roc_auc_score(test["target_refused"], p)), 4),
            "average_precision": round(float(average_precision_score(test["target_refused"], p)), 4),
            "frozen_v3_roc_auc": 0.7989,
            "frozen_v3_ap": 0.4202,
        },
    }

    mutation_test = test[test["description_stripped"].str.contains("[structured", regex=False)].sample(
        n=min(60, int(test["description_stripped"].str.contains("[structured", regex=False).sum())), random_state=42
    )
    sweeps = {}
    for field, delta in [("storeys", 1), ("storeys", -1), ("units", 10), ("units", -10), ("parking", 5), ("parking", -5), ("height", 1.0), ("height", -1.0), ("access", 1), ("access", -1)]:
        moved = 0
        correct = 0
        deltas = []
        for _, row in mutation_test.iterrows():
            mutated = mutate_tokens(str(row["description_stripped"]), field, delta)
            if mutated is None:
                continue
            before = float(model.predict_proba(pd.DataFrame([{f: row[f] for f in features}]).assign(description_stripped=str(row["description_stripped"])))[:, 1][0])
            after = float(model.predict_proba(pd.DataFrame([{f: row[f] for f in features}]).assign(description_stripped=mutated))[:, 1][0])
            d = (after - before) * 100.0
            deltas.append(d)
            moved += 1
            if (delta > 0 and d > 0) or (delta < 0 and d < 0):
                correct += 1
        sweeps[f"{field}{delta:+g}"] = {
            "n": moved,
            "direction_agreement": round(correct / moved, 4) if moved else None,
            "median_delta_pp": round(float(np.median(deltas)), 3) if deltas else None,
        }
    results["token_mutation_sweeps"] = sweeps
    results["caveat"] = (
        "Augmented tokens are only present where extracted (planner reports + GE10 units); "
        "the frozen v3 discipline is untouched - this is a research candidate. Structured "
        "tokens learn from the same noisy cohorts, so improvement is not guaranteed."
    )
    (OUTPUT_DIR / "raw_planning_v3b_structured_augmented.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
