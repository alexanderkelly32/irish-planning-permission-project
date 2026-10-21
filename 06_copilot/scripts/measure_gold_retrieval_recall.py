#!/usr/bin/env python3
"""Measure how highly the retrieval ranks similarity-based gold precedents."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from find_similar_developments import build_query_frame, find_similar_to_query, fit_search_artifacts, transform_rows
from precedent_copilot_logic import normalize_cases, rerank_candidates
from retrieval_benchmark import pick_gold_similarity, retrieve_candidates

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "06_copilot" / "current"
DEFAULT_CSV = ROOT / "04_fi" / "current" / "greater_than_10_units_with_refusal_reasons_plus_ge10_fi_requests_enriched.csv"
DEFAULT_MANIFEST = ROOT / "02_development" / "current" / "retrieval_benchmark_grading_2026-09-04" / "query_manifest.csv"


def manifest_query_payload(row: pd.Series) -> dict[str, object]:
    return {
        "PlanningAuthority": row.get("query_authority"),
        "ApplicationType": None,
        "DevelopmentDescription": row.get("query_description"),
        "units_total_best": row.get("query_units"),
        "ITMEasting": None,
        "ITMNorthing": None,
        "received_year": 2026.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--top-k", type=int, default=200)
    args = parser.parse_args()

    cases = normalize_cases(pd.read_csv(args.csv, low_memory=False))
    artifacts = fit_search_artifacts(cases)
    case_matrix = transform_rows(cases, artifacts)
    manifest = pd.read_csv(args.manifest, low_memory=False)

    gold_mapping: dict[str, str] = {}
    ranks: dict[str, int] = {}
    for _, query_row in manifest.iterrows():
        query_id = query_row["query_id"]
        pseudo_query = pd.Series({
            "case_key": query_row.get("query_application_number"),
            "PlanningAuthority": query_row.get("query_authority"),
            "ApplicationType": None,
            "DevelopmentDescription": query_row.get("query_description"),
            "units_total_best": query_row.get("query_units"),
            "max_storeys_best": None,
            "ITMEasting": None,
            "ITMNorthing": None,
        })
        payload = manifest_query_payload(query_row)
        retrieved = retrieve_candidates(cases, pseudo_query, artifacts, case_matrix, top_k=10)
        gold = pick_gold_similarity(cases, pseudo_query, artifacts, excluded_keys=set(retrieved["case_key"]))
        if gold is None:
            continue
        gold_key = str(gold["case_key"])
        gold_mapping[query_id] = gold_key
        query_frame = build_query_frame(cases, **payload)
        candidates = find_similar_to_query(
            cases, case_matrix, transform_rows(query_frame, artifacts), top_k=max(args.top_k * 8, 400),
        )
        ranked = rerank_candidates(candidates, payload)
        case_keys = list(ranked["case_key"])
        if gold_key in case_keys:
            ranks[query_id] = case_keys.index(gold_key) + 1

    total = len(gold_mapping)
    rank_values = list(ranks.values())
    results = {
        "gold_count": total,
        "queries_without_similar_gold": int(len(manifest) - total),
        "found_within_candidates": int(len(rank_values)),
        "recall_at_10": round(sum(1 for rank in rank_values if rank <= 10) / total, 4) if total else None,
        "recall_at_50": round(sum(1 for rank in rank_values if rank <= 50) / total, 4) if total else None,
        "median_rank_of_found": float(pd.Series(rank_values).median()) if rank_values else None,
        "candidate_pool": args.top_k,
        "caveat": (
            "Gold precedents are same-authority cases that are text-similar to the query "
            "(minimum similarity threshold), selected independently of the retrieval ranking."
        ),
    }
    CURRENT.mkdir(parents=True, exist_ok=True)
    (CURRENT / "retrieval_benchmark_gold_mapping_similarity.json").write_text(
        json.dumps(gold_mapping, indent=2), encoding="utf-8"
    )
    (CURRENT / "retrieval_benchmark_gold_recall.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
