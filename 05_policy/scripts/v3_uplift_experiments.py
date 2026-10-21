#!/usr/bin/env python3
"""v3-native uplift experiments (no new models - the frozen model is the instrument).

1. text-mutation sweeps: rewrite storeys/units/parking/height phrases in real
   descriptions and rescore with frozen v3; measures whether v3-native
   sensitivity analysis is usable for the scenario engine.
2. coefficient diagnosis: token-level risk contributions from the trained
   logistic coefficients, validated against known refused/granted labels.
3. weakness clusters: where frozen v3 under-performs on the 2025 holdout,
   by application bucket and authority.

Outputs (05_policy/current/):
  raw_planning_v3_text_mutation_sweeps.json
  raw_planning_v3_coefficient_diagnosis.json
  raw_planning_v3_weakness_clusters.json
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "05_policy" / "current"
BUNDLE_PATH = OUTPUT_DIR / "model_v3" / "national_residential_v3_comparables.joblib"
PREDICTIONS = OUTPUT_DIR / "raw_planning_v3_2025_predictions.csv"

sys.path.insert(0, str(ROOT / "06_copilot" / "scripts"))
from precedent_copilot_logic import clean_text, score_submission_risk  # noqa: E402

STORIES_PATTERN = re.compile(r"(\d+)\s*(?:[-–]|to\s*\d+\s*[-–]\s*)?(?:storeys?|storey)", re.IGNORECASE)
STOREY_WORD_PATTERN = re.compile(r"\b(\d+)\s*[-–]\s*storeys?\b", re.IGNORECASE)
UNITS_PATTERN = re.compile(r"\b(\d+)\s*(?:no\.?\s+)?(?:residential\s+)?(?:units|dwellings|houses|apartments)\b", re.IGNORECASE)
PARKING_PATTERN = re.compile(r"\b(\d+)\s*(?:no\.?\s+)?(?:car\s+)?parking\s+spaces?\b", re.IGNORECASE)
HEIGHT_PATTERN = re.compile(r"\b(\d+(?:\.\d+)?)\s*m(?:etres?)?\s*(?:high|in height|above ground)\b", re.IGNORECASE)


def _replace_first(pattern: re.Pattern, text: str, replacement: str) -> str | None:
    match = pattern.search(text)
    if not match:
        return None
    return text[:match.start()] + replacement + text[match.end():]


def mutate_storeys(description: str, delta: int) -> str | None:
    for pattern in (STOREY_WORD_PATTERN, STORIES_PATTERN):
        match = pattern.search(description)
        if match:
            current = int(match.group(1))
            new_value = max(1, min(12, current + delta))
            if new_value == current:
                return None
            return description[:match.start()] + str(new_value) + description[match.end():]
    return None


def mutate_units(description: str, factor: float) -> str | None:
    match = UNITS_PATTERN.search(description)
    if not match:
        return None
    current = int(match.group(1))
    new_value = max(1, int(round(current * factor)))
    if new_value == current:
        return None
    return description[:match.start()] + str(new_value) + description[match.end():]


def mutate_parking(description: str, delta: int) -> str | None:
    match = PARKING_PATTERN.search(description)
    if not match:
        return None
    current = int(match.group(1))
    new_value = max(0, current + delta)
    if new_value == current:
        return None
    return description[:match.start()] + str(new_value) + description[match.end():]


def mutate_height(description: str, factor: float) -> str | None:
    match = HEIGHT_PATTERN.search(description)
    if not match:
        return None
    current = float(match.group(1))
    new_value = round(current * factor, 1)
    if new_value == current:
        return None
    return description[:match.start()] + f"{new_value:g}m" + description[match.end():]


def _score(model, planning_authority: str, description: str, received_year: int) -> float | None:
    query = {
        "PlanningAuthority": planning_authority,
        "ApplicationType": "",
        "DevelopmentDescription": description,
        "units_total_best": None,
        "received_year": received_year,
    }
    try:
        result = score_submission_risk(query, model)
    except Exception:
        return None
    if result.get("status") != "scored":
        return None
    return float(result["refusal_score"])


def experiment_text_mutations(model, n: int = 100, seed: int = 20260913) -> dict:
    reference = model.get("comparable_reference", pd.DataFrame())
    if reference.empty:
        return {"status": "no_reference"}
    descriptions = reference["description_stripped"].fillna("").astype(str).map(clean_text)

    pools = {
        "storeys": reference[descriptions.map(lambda text: bool(STOREY_WORD_PATTERN.search(text) or STORIES_PATTERN.search(text)))],
        "units": reference[descriptions.map(lambda text: bool(UNITS_PATTERN.search(text)))],
        "parking": reference[descriptions.map(lambda text: bool(PARKING_PATTERN.search(text)))],
        "height": reference[descriptions.map(lambda text: bool(HEIGHT_PATTERN.search(text)))],
    }
    mutations = [
        ("storeys_up", "storeys", lambda d: mutate_storeys(d, +1)),
        ("storeys_down", "storeys", lambda d: mutate_storeys(d, -1)),
        ("units_up10", "units", lambda d: mutate_units(d, 1.10)),
        ("units_down10", "units", lambda d: mutate_units(d, 0.90)),
        ("parking_up5", "parking", lambda d: mutate_parking(d, +5)),
        ("parking_down5", "parking", lambda d: mutate_parking(d, -5)),
        ("height_up50", "height", lambda d: mutate_height(d, 1.5)),
        ("height_down33", "height", lambda d: mutate_height(d, 0.66)),
    ]
    stats = {}
    deltas = {}
    examples = []
    for name, pool_key, builder in mutations:
        pool = pools[pool_key].sample(n=min(25, len(pools[pool_key])), random_state=seed + hash(name) % 1000)
        stats[name] = {"evaluated": 0, "direction_agreement": 0, "moved_at_least_1pp": 0, "pool": int(len(pools[pool_key]))}
        deltas[name] = []
        for _, row in pool.iterrows():
            description = clean_text(row.get("description_stripped"))
            if not description:
                continue
            year = int(pd.to_datetime(row.get("received_date_dt"), errors="coerce").year) if pd.notna(row.get("received_date_dt")) else 2023
            authority = clean_text(row.get("PlanningAuthority"))
            baseline = _score(model, authority, description, year)
            if baseline is None:
                continue
            mutated = builder(description)
            if mutated is None or mutated == description:
                continue
            score = _score(model, authority, mutated, year)
            if score is None:
                continue
            delta_pp = (score - baseline) * 100.0
            stats[name]["evaluated"] += 1
            deltas[name].append(delta_pp)
            up_variants = {"storeys_up", "units_up10", "parking_up5", "height_up50"}
            if (name in up_variants and delta_pp > 0) or (name not in up_variants and delta_pp < 0):
                stats[name]["direction_agreement"] += 1
            if abs(delta_pp) >= 1.0:
                stats[name]["moved_at_least_1pp"] += 1
            if len(examples) < 8 and name in {"storeys_up", "units_down10"}:
                examples.append({
                    "mutation": name,
                    "authority": authority,
                    "description": description[:200],
                    "baseline_risk": round(baseline, 4),
                    "mutated_risk": round(score, 4),
                    "delta_pp": round(delta_pp, 2),
                })

    for name in stats:
        values = deltas[name]
        stats[name]["n"] = len(values)
        stats[name]["median_delta_pp"] = round(float(np.median(values)), 3) if values else None
        stats[name]["direction_agreement_rate"] = round(stats[name]["direction_agreement"] / stats[name]["evaluated"], 4) if stats[name]["evaluated"] else None
        stats[name]["moved_at_least_1pp_rate"] = round(stats[name]["moved_at_least_1pp"] / stats[name]["evaluated"], 4) if stats[name]["evaluated"] else None
        stats[name].pop("direction_agreement", None)
        stats[name].pop("moved_at_least_1pp", None)

    ladder_rows = 0
    ladder_monotone = 0
    ladder_pool = pools["storeys"].sample(n=min(20, len(pools["storeys"])), random_state=seed)
    for _, row in ladder_pool.iterrows():
        description = clean_text(row.get("description_stripped"))
        if not description:
            continue
        authority = clean_text(row.get("PlanningAuthority"))
        year = int(pd.to_datetime(row.get("received_date_dt"), errors="coerce").year) if pd.notna(row.get("received_date_dt")) else 2023
        baseline = _score(model, authority, description, year)
        if baseline is None:
            continue
        scores = [baseline]
        text = description
        for _ in range(8):
            rewritten = mutate_storeys(text, +1)
            if rewritten is None or rewritten == text:
                break
            text = rewritten
            value = _score(model, authority, text, year)
            if value is None:
                break
            scores.append(value)
        if len(scores) >= 3:
            ladder_rows += 1
            if all(later >= earlier for earlier, later in zip(scores, scores[1:])):
                ladder_monotone += 1
    ladder = {"rows_evaluated": ladder_rows, "monotone_increasing": ladder_monotone,
              "monotone_rate": round(ladder_monotone / ladder_rows, 4) if ladder_rows else None}

    return {
        "pattern_pools": {key: int(len(pool)) for key, pool in pools.items()},
        "mutation_stats": stats,
        "storeys_ladder": ladder,
        "examples": examples,
        "caveat": "Text rewrites are synthetic edits to real descriptions sampled from those containing the target phrase; direction agreement and monotonicity are signs of usable v3-native sensitivity, not causal effects. Bucket/dev-type inference reads the mutated text.",
    }


def experiment_coefficient_diagnosis(model, n: int = 100, seed: int = 20260913) -> dict:
    pipeline = model.get("ranking_model")
    reference = model.get("comparable_reference", pd.DataFrame())
    if pipeline is None or reference.empty:
        return {"status": "no_pipeline_or_reference"}
    preprocessor = pipeline.named_steps["preprocessor"]
    vectorizer = preprocessor.named_transformers_["txt"]
    coefficients = pipeline.named_steps["model"].coef_[0]
    feature_names = np.asarray(vectorizer.get_feature_names_out())
    text_weights = coefficients[-len(feature_names):]

    refused = reference[reference["target_refused"] == 1].sample(n=min(n // 2, int((reference["target_refused"] == 1).sum())), random_state=seed)
    granted = reference[reference["target_refused"] == 0].sample(n=min(n // 2, int((reference["target_refused"] == 0).sum())), random_state=seed)
    cases = pd.concat([refused, granted], ignore_index=True)

    rows = []
    for _, row in cases.iterrows():
        description = clean_text(row.get("description_stripped"))
        if not description:
            continue
        tfidf = vectorizer.transform([description])
        contributions = tfidf.toarray()[0] * text_weights
        order = np.argsort(-contributions)
        top = []
        for index in order[:6]:
            weight = float(contributions[index])
            if weight <= 0:
                break
            token = str(feature_names[index])
            span = re.search(re.escape(token), description, re.IGNORECASE)
            top.append({
                "token": token,
                "contribution": round(weight, 5),
                "span": description[max(0, span.start() - 30):span.end() + 30] if span else "",
            })
        rows.append({
            "case_key": str(row.get("case_key")),
            "target_refused": int(row["target_refused"]),
            "top_risk_tokens": top,
            "total_risk_contribution": round(float(contributions.sum()), 5),
        })
    if not rows:
        return {"status": "no_scorable_rows"}
    frame = pd.DataFrame(rows)
    refused_load = frame[frame["target_refused"] == 1]["total_risk_contribution"].mean()
    granted_load = frame[frame["target_refused"] == 0]["total_risk_contribution"].mean()
    separation = refused_load - granted_load

    return {
        "cases": int(len(frame)),
        "mean_text_risk_contribution_refused": round(float(refused_load), 5),
        "mean_text_risk_contribution_granted": round(float(granted_load), 5),
        "separation": round(float(separation), 5),
        "verdict": "text coefficients separate refused from granted" if separation > 0 else "text coefficients do NOT separate the labels - investigate",
        "top_global_risk_tokens": [
            {"token": str(feature_names[i]), "weight": round(float(text_weights[i]), 5)}
            for i in np.argsort(-text_weights)[:25]
        ],
        "examples": rows[:12],
        "caveat": "Contributions are logistic coefficients weighted by the case's own TF-IDF values; directionally useful for diagnosis, not causal attribution.",
    }


def experiment_weakness_clusters() -> dict:
    frame = pd.read_csv(PREDICTIONS, low_memory=False)
    clusters = []
    for column in ["application_bucket", "PlanningAuthority"]:
        for value, group in frame.groupby(column):
            y = group["target_refused"]
            if y.nunique() < 2:
                continue
            p = group["v3_ranking_score"].to_numpy()
            calibrated = group["v3_platt_risk"].to_numpy()
            clusters.append({
                "dimension": column,
                "cluster": str(value),
                "n": int(len(group)),
                "refusal_rate": round(float(y.mean()), 4),
                "roc_auc": round(float(roc_auc_score(y, p)), 4),
                "average_precision": round(float(average_precision_score(y, p)), 4),
                "ranking_brier": round(float(brier_score_loss(y, p)), 4),
                "calibrated_brier": round(float(brier_score_loss(y, calibrated)), 4),
                "calibration_error_pp": round(float(np.abs(calibrated.mean() - y.mean()) * 100), 2),
            })
    clusters = sorted(clusters, key=lambda row: (row["roc_auc"] is None, row["roc_auc"]))
    weak = [row for row in clusters if row["roc_auc"] is not None and row["roc_auc"] < 0.72]
    return {
        "holdout_rows": int(len(frame)),
        "clusters_evaluated": len(clusters),
        "weakest_clusters_auc_below_0.72": weak,
        "weakest_overall": clusters[:12],
        "caveat": "Small clusters and all-one-class groups excluded; per-cluster metrics on the 2025 holdout are directional where n is small.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiments", type=str, default="1,2,3", help="comma-separated: 1=text mutations, 2=coefficients, 3=weakness clusters")
    parser.add_argument("--rows", type=int, default=100)
    args = parser.parse_args()

    model = joblib.load(BUNDLE_PATH)
    if isinstance(model, dict) and "ranking_model" not in model:
        model = {"ranking_model": None, **model}

    selected = {int(part) for part in args.experiments.split(",") if part.strip()}
    outputs = {}
    if 1 in selected:
        outputs["text_mutation_sweeps"] = experiment_text_mutations(model, n=args.rows)
    if 2 in selected:
        outputs["coefficient_diagnosis"] = experiment_coefficient_diagnosis(model, n=args.rows)
    if 3 in selected:
        outputs["weakness_clusters"] = experiment_weakness_clusters()

    names = {
        "text_mutation_sweeps": "raw_planning_v3_text_mutation_sweeps.json",
        "coefficient_diagnosis": "raw_planning_v3_coefficient_diagnosis.json",
        "weakness_clusters": "raw_planning_v3_weakness_clusters.json",
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for key, payload in outputs.items():
        (OUTPUT_DIR / names[key]).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(outputs, indent=2))


if __name__ == "__main__":
    main()
