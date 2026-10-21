"""Build the comparable-retrieval benchmark grading pack (Task 6)."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import pandas as pd

from precedent_copilot_logic import infer_residential_application_bucket, normalize_cases, rerank_candidates
from find_similar_developments import build_query_frame, find_similar_to_query, fit_search_artifacts, transform_rows

RESIDENTIAL_QUERY_BUCKETS = ("10+ units", "2-9 units", "single dwelling", "extension / alteration", "retention", "change of use", "other residential")


def _hash(value: object, salt: str) -> str:
    return hashlib.sha256(f"{salt}|{value}".encode("utf-8")).hexdigest()


def select_queries(cases: pd.DataFrame, per_bucket: dict[str, int], seed: int = 20260904) -> pd.DataFrame:
    """Deterministic stratified query selection across application buckets."""
    frame = cases.copy()
    frame["query_bucket"] = frame.apply(
        lambda row: infer_residential_application_bucket({
            "ApplicationType": row.get("ApplicationType"),
            "DevelopmentDescription": row.get("DevelopmentDescription"),
            "units_total_best": row.get("units_total_best"),
        }),
        axis=1,
    )
    selected = []
    for bucket, count in per_bucket.items():
        group = frame[frame["query_bucket"] == bucket].copy()
        if group.empty:
            continue
        group["_order"] = [_hash(case_key, str(seed)) for case_key in group["case_key"]]
        selected.append(group.sort_values("_order").head(count).drop(columns="_order"))
    if not selected:
        raise ValueError("no query candidates found for the requested buckets")
    return pd.concat(selected, ignore_index=True)


def build_query_payload(row: pd.Series) -> dict[str, object]:
    return {
        "PlanningAuthority": row.get("PlanningAuthority"),
        "ApplicationType": row.get("ApplicationType"),
        "DevelopmentDescription": row.get("DevelopmentDescription"),
        "units_total_best": row.get("units_total_best"),
        "max_storeys_best": row.get("max_storeys_best"),
        "ITMEasting": row.get("ITMEasting"),
        "ITMNorthing": row.get("ITMNorthing"),
        "received_year": 2026.0,
    }


def retrieve_candidates(cases: pd.DataFrame, query_row: pd.Series, artifacts, case_matrix, top_k: int = 10) -> pd.DataFrame:
    normalized = normalize_cases(cases)
    query_frame = build_query_frame(normalized, **build_query_payload(query_row))
    candidates = find_similar_to_query(
        normalized, case_matrix, transform_rows(query_frame, artifacts), top_k=max(top_k * 8, 120),
    )
    ranked = rerank_candidates(candidates, build_query_payload(query_row))
    ranked = ranked[ranked["case_key"] != query_row["case_key"]]
    return ranked.head(top_k)


def pick_gold_similarity(
    cases: pd.DataFrame,
    query_row: pd.Series,
    artifacts,
    excluded_keys: set[str],
    minimum_similarity: float = 0.12,
    seed: int = 20260904,
) -> pd.Series | None:
    """A genuinely similar same-authority precedent, selected by text similarity.

    Same bucket alone was too weak (extracted unit errors, unrelated schemes), so the
    gold must additionally be text-similar to the query description.
    """
    from sklearn.metrics.pairwise import linear_kernel

    frame = cases[cases["case_key"] != query_row["case_key"]].copy()
    frame = frame[~frame["case_key"].isin(excluded_keys)]
    frame = frame[frame["PlanningAuthority"].astype(str) == str(query_row.get("PlanningAuthority"))].copy()
    if frame.empty:
        return None
    query_text = str(query_row.get("DevelopmentDescription") or "")
    query_vector = artifacts.vectorizer.transform([query_text])
    candidate_vectors = artifacts.vectorizer.transform(frame["DevelopmentDescription"].fillna("").astype(str))
    similarity = linear_kernel(query_vector, candidate_vectors).ravel()
    frame["_similarity"] = similarity
    frame = frame[frame["_similarity"] >= minimum_similarity].sort_values("_similarity", ascending=False)
    if frame.empty:
        return None
    top = frame.head(5)
    top = top.copy()
    top["_order"] = [_hash(case_key, f"gold-sim-{seed}") for case_key in top["case_key"]]
    return top.sort_values("_order").iloc[0]


def build_grading_rows(cases: pd.DataFrame, queries: pd.DataFrame, artifacts, case_matrix, seed: int = 20260904) -> tuple[pd.DataFrame, dict[str, str]]:
    rows: list[dict[str, Any]] = []
    gold_mapping: dict[str, str] = {}
    for query_index, (_, query_row) in enumerate(queries.iterrows()):
        query_id = f"Q{query_index + 1:03d}"
        retrieved = retrieve_candidates(cases, query_row, artifacts, case_matrix, top_k=10)
        excluded = set(retrieved["case_key"])
        gold = pick_gold_similarity(cases, query_row, artifacts, excluded, seed=seed)
        if gold is not None:
            gold_mapping[query_id] = str(gold["case_key"])
        candidate_rows = []
        for rank, (_, candidate) in enumerate(retrieved.iterrows(), start=1):
            candidate_rows.append({
                "query_id": query_id,
                "candidate_rank": rank,
                "candidate_case_key": str(candidate.get("case_key")),
                "candidate_authority": str(candidate.get("PlanningAuthority") or ""),
                "candidate_application_number": str(candidate.get("ApplicationNumber") or ""),
                "candidate_description": str(candidate.get("DevelopmentDescription") or ""),
                "candidate_units": candidate.get("units_total_best"),
                "retrieval_score": round(float(candidate.get("hybrid_score", 0.0)), 4),
                "relevance": "",
                "grade_notes": "",
                "graded_by": "",
                "graded_at": "",
            })
        if gold is not None:
            candidate_rows.append({
                "query_id": query_id,
                "candidate_rank": 11,
                "candidate_case_key": str(gold["case_key"]),
                "candidate_authority": str(gold.get("PlanningAuthority") or ""),
                "candidate_application_number": str(gold.get("ApplicationNumber") or ""),
                "candidate_description": str(gold.get("DevelopmentDescription") or ""),
                "candidate_units": gold.get("units_total_best"),
                "retrieval_score": None,
                "relevance": "",
                "grade_notes": "",
                "graded_by": "",
                "graded_at": "",
            })
        rows.extend(candidate_rows)
    return pd.DataFrame(rows), gold_mapping


def query_manifest(queries: pd.DataFrame, gold_mapping: dict[str, str]) -> pd.DataFrame:
    rows = []
    for index, (_, row) in enumerate(queries.iterrows()):
        query_id = f"Q{index + 1:03d}"
        rows.append({
            "query_id": query_id,
            "query_authority": str(row.get("PlanningAuthority") or ""),
            "query_application_number": str(row.get("ApplicationNumber") or ""),
            "query_description": str(row.get("DevelopmentDescription") or ""),
            "query_units": row.get("units_total_best"),
        })
    return pd.DataFrame(rows)


def grade_to_score(value: object) -> float | None:
    text = str(value or "").strip().lower()
    mapping = {"0": 0.0, "irrelevant": 0.0, "1": 1.0, "weak": 1.0, "2": 2.0, "relevant": 2.0, "3": 3.0, "highly relevant": 3.0}
    return mapping.get(text)


def score_benchmark(grading: pd.DataFrame, gold_mapping: dict[str, str]) -> dict[str, Any]:
    """Precision@5/10, NDCG@10 and gold recall from completed grades."""
    if grading.empty:
        return {"status": "no_grades"}
    frame = grading.copy()
    frame["score"] = frame["relevance"].map(grade_to_score)
    results: dict[str, Any] = {}
    precision_at_5 = []
    precision_at_10 = []
    ndcg_at_10 = []
    gold_found = 0
    gold_total = 0
    for query_id, group in frame.groupby("query_id"):
        retrieved = group[group["candidate_rank"] <= 10].sort_values("candidate_rank")
        scores = retrieved["score"]
        graded = scores.dropna()
        relevant_k = graded >= 2
        if len(graded) >= 5:
            precision_at_5.append(float(relevant_k.head(5).mean()))
        precision_at_10.append(float(relevant_k.mean()) if len(graded) else 0.0)
        dcg = sum((2 ** float(score) - 1) / __import__("math").log2(rank + 1) for rank, score in enumerate(graded.head(10), start=1))
        ideal = sorted([float(score) for score in graded.head(10)], reverse=True)
        idcg = sum((2 ** score - 1) / __import__("math").log2(rank + 1) for rank, score in enumerate(ideal, start=1))
        ndcg_at_10.append(dcg / idcg if idcg > 0 else 0.0)
        if query_id in gold_mapping:
            gold_total += 1
            gold_row = group[group["candidate_case_key"] == gold_mapping[query_id]]
            if not gold_row.empty and grade_to_score(gold_row.iloc[0]["relevance"]) is not None and grade_to_score(gold_row.iloc[0]["relevance"]) >= 2:
                gold_found += 1
    import statistics

    results = {
        "queries_graded": int(frame["query_id"].nunique()),
        "grades_available": int(frame["score"].notna().sum()),
        "precision_at_5": round(statistics.mean(precision_at_5), 4) if precision_at_5 else None,
        "precision_at_10": round(statistics.mean(precision_at_10), 4) if precision_at_10 else None,
        "ndcg_at_10": round(statistics.mean(ndcg_at_10), 4) if ndcg_at_10 else None,
        "gold_recall": round(gold_found / gold_total, 4) if gold_total else None,
        "gold_total": gold_total,
        "caveat": "Grades measure the current retrieval ranking on a labelled sample; they are not production guarantees.",
    }
    return results
