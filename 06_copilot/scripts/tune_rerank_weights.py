#!/usr/bin/env python3
"""Tune the comparable-rerank weights against the human benchmark grades."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import linear_kernel

from find_similar_developments import fit_search_artifacts, transform_rows
from precedent_copilot_logic import normalize_cases, safe_float, token_overlap_ratio, token_set
from retrieval_benchmark import grade_to_score

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "06_copilot" / "current"
DEFAULT_CSV = ROOT / "04_fi" / "current" / "greater_than_10_units_with_refusal_reasons_plus_ge10_fi_requests_enriched.csv"
DEFAULT_GRADING = CURRENT / "retrieval_benchmark_grading_fixed.csv"
DEFAULT_MANIFEST = ROOT / "02_development" / "current" / "archive_2026-09-04" / "retrieval_benchmark_grading_2026-09-04" / "query_manifest.csv"

DEFAULT_WEIGHTS = {
    "text": 0.45,
    "authority": 0.15,
    "scale": 0.15,
    "geo": 0.10,
    "tag": 0.10,
    "token": 0.05,
}


def load_grading(grading_path: Path, manifest_path: Path, csv_path: Path):
    grading = pd.read_csv(grading_path, low_memory=False)
    manifest = pd.read_csv(manifest_path, low_memory=False) if manifest_path.exists() else pd.DataFrame()
    cases = normalize_cases(pd.read_csv(csv_path, low_memory=False))
    return grading, manifest, cases


def component_scores(query: dict, candidate_row: pd.Series, case_matrix, candidate_index: int, query_vector) -> dict[str, float]:
    candidate_description = str(candidate_row.get("DevelopmentDescription") or "")
    text_score = float(linear_kernel(query_vector, case_matrix[candidate_index]).ravel()[0])
    query_pa = str(query.get("PlanningAuthority") or "").lower()
    candidate_pa = str(candidate_row.get("PlanningAuthority") or "").lower()
    authority_score = float(query_pa and query_pa == candidate_pa)
    query_type = str(query.get("ApplicationType") or "").lower()
    candidate_type = str(candidate_row.get("ApplicationType") or "").lower()
    type_score = 1.0 if (query_type and query_type == candidate_type) else 0.0
    query_units = safe_float(query.get("units_total_best"))
    candidate_units = safe_float(candidate_row.get("units_total_num", candidate_row.get("units_total_best")))
    if query_units is not None and candidate_units is not None:
        denom = max(query_units, candidate_units)
        scale_score = float(np.clip(1.0 - abs(candidate_units - query_units) / max(denom, 1.0), 0.0, 1.0))
    else:
        scale_score = 0.0
    query_tag = str(query.get("case_top_primary_tag") or "").lower()
    candidate_tag = str(candidate_row.get("case_top_primary_tag") or "").lower()
    tag_score = 1.0 if (query_tag and query_tag == candidate_tag) else 0.0
    query_tokens = token_set(str(query.get("DevelopmentDescription") or ""))
    token_score = float(token_overlap_ratio(query_tokens, token_set(candidate_description)) if query_tokens else 0.0)
    query_easting = safe_float(query.get("ITMEasting"))
    query_northing = safe_float(query.get("ITMNorthing"))
    candidate_easting = safe_float(candidate_row.get("itm_easting_num", candidate_row.get("ITMEasting")))
    candidate_northing = safe_float(candidate_row.get("itm_northing_num", candidate_row.get("ITMNorthing")))
    if None not in {query_easting, query_northing, candidate_easting, candidate_northing}:
        distance_km = float(np.hypot(candidate_easting - query_easting, candidate_northing - query_northing) / 1000.0)
        geo_score = float(1.0 - np.clip(distance_km / 25.0, 0.0, 1.0))
    else:
        geo_score = 0.0
    return {
        "text": text_score, "authority": authority_score, "type": type_score,
        "scale": scale_score, "geo": geo_score, "tag": tag_score, "token": token_score,
    }


def _text_vector(artifacts, description: str):
    from scipy import sparse

    return sparse.csr_matrix(artifacts.vectorizer.transform([description]))


def hybrid_score(components: dict[str, float], weights: dict[str, float]) -> float:
    return sum(components.get(name, 0.0) * weight for name, weight in weights.items() if name != "type")


def ndcg_at_k(grades: list[float], k: int = 10) -> float:
    import math

    dcg = sum((2 ** grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(grades[:k], start=1))
    ideal = sorted(grades, reverse=True)
    idcg = sum((2 ** grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(ideal[:k], start=1))
    return dcg / idcg if idcg > 0 else 0.0


def evaluate_weights(grading_frame: pd.DataFrame, components_by_row: dict[int, dict[str, float]], weights: dict[str, float]) -> dict[str, float]:
    ndcgs = []
    precisions = []
    for query_id, group in grading_frame.groupby("query_id"):
        ranked = group[group["candidate_rank"] <= 10].copy()
        if ranked.empty:
            continue
        ranked["_score"] = [hybrid_score(components_by_row.get(int(index), {}), weights) for index in ranked.index]
        ranked = ranked.sort_values("_score", ascending=False)
        grades = [grade_to_score(value) or 0.0 for value in ranked["relevance"]]
        ndcgs.append(ndcg_at_k(grades))
        precisions.append(float(np.mean([grade >= 2 for grade in grades])))
    return {
        "ndcg_at_10": round(float(np.mean(ndcgs)), 4) if ndcgs else 0.0,
        "precision_at_10": round(float(np.mean(precisions)), 4) if precisions else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--grading", type=Path, default=DEFAULT_GRADING)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--trials", type=int, default=300)
    parser.add_argument("--seed", type=int, default=20260905)
    args = parser.parse_args()

    grading, manifest, cases = load_grading(args.grading, args.manifest, args.csv)
    artifacts = fit_search_artifacts(cases)
    case_matrix = transform_rows(cases, artifacts)
    case_by_key = {str(row["case_key"]): index for index, row in cases.iterrows()}
    manifest_by_id = {row["query_id"]: row for _, row in manifest.iterrows()} if not manifest.empty else {}

    components_by_row: dict[int, dict[str, float]] = {}
    queries_by_id: dict[str, dict] = {}
    from find_similar_developments import build_query_frame

    query_vectors: dict[str, object] = {}
    for index, row in grading.iterrows():
        query_id = row["query_id"]
        candidate_index = case_by_key.get(str(row["candidate_case_key"]))
        if candidate_index is None:
            continue
        query_row = manifest_by_id.get(query_id)
        if query_row is None:
            query = {
                "PlanningAuthority": None,
                "DevelopmentDescription": "",
                "ApplicationType": None,
                "units_total_best": None,
                "ITMEasting": None,
                "ITMNorthing": None,
                "case_top_primary_tag": None,
            }
        else:
            query = {
                "PlanningAuthority": query_row.get("query_authority"),
                "DevelopmentDescription": query_row.get("query_description"),
                "ApplicationType": None,
                "units_total_best": query_row.get("query_units"),
                "ITMEasting": None,
                "ITMNorthing": None,
                "case_top_primary_tag": None,
            }
        if query_id not in query_vectors:
            query_vectors[query_id] = transform_rows(build_query_frame(cases, **query), artifacts)
        queries_by_id[query_id] = query
        components_by_row[int(index)] = component_scores(
            query, cases.iloc[candidate_index], case_matrix, candidate_index, query_vectors[query_id]
        )

    query_ids = sorted(set(grading["query_id"]))
    rng = np.random.default_rng(args.seed)
    order = rng.permutation(len(query_ids))
    train_ids = {query_ids[index] for index in order[: int(len(order) * 0.7)]}
    test_ids = {query_ids[index] for index in order[int(len(order) * 0.7):]}
    train_frame = grading[grading["query_id"].isin(train_ids)]
    test_frame = grading[grading["query_id"].isin(test_ids)]

    baseline_train = evaluate_weights(train_frame, components_by_row, DEFAULT_WEIGHTS)
    baseline_test = evaluate_weights(test_frame, components_by_row, DEFAULT_WEIGHTS)

    best: dict[str, float] | None = None
    best_score = -1.0
    for _ in range(args.trials):
        weights = {
            "text": float(rng.uniform(0.2, 0.6)),
            "authority": float(rng.uniform(0.0, 0.3)),
            "scale": float(rng.uniform(0.0, 0.3)),
            "geo": float(rng.uniform(0.0, 0.2)),
            "tag": float(rng.uniform(0.0, 0.2)),
            "token": float(rng.uniform(0.0, 0.15)),
        }
        total = sum(weights.values())
        weights = {name: value / total for name, value in weights.items()}
        score = evaluate_weights(train_frame, components_by_row, weights)["ndcg_at_10"]
        if score > best_score:
            best_score = score
            best = weights

    results = {
        "baseline_weights": DEFAULT_WEIGHTS,
        "baseline": {"train": baseline_train, "test": baseline_test},
        "tuned_weights": {name: round(value, 4) for name, value in (best or DEFAULT_WEIGHTS).items()},
        "tuned": {
            "train": evaluate_weights(train_frame, components_by_row, best or DEFAULT_WEIGHTS),
            "test": evaluate_weights(test_frame, components_by_row, best or DEFAULT_WEIGHTS),
        },
        "tuning": {"trials": args.trials, "seed": args.seed, "train_queries": len(train_ids), "test_queries": len(test_ids)},
        "caveat": "Weight search uses the graded candidates only (top-10 + gold per query); the app keeps its current weights until this improvement is verified end to end.",
    }
    (CURRENT / "rerank_weight_tuning_2026-09-05.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
