import unittest

import pandas as pd

from find_similar_developments import fit_search_artifacts
from retrieval_benchmark import (
    grade_to_score,
    pick_gold_similarity,
    score_benchmark,
    select_queries,
)


def case_row(case_key, authority, description, units):
    return {
        "case_key": case_key,
        "PlanningAuthority": authority,
        "ApplicationNumber": case_key,
        "ApplicationType": "Permission",
        "DevelopmentDescription": description,
        "units_total_best": units,
    }


class RetrievalBenchmarkTests(unittest.TestCase):
    def build_cases(self):
        rows = []
        for index in range(40):
            rows.append(case_row(f"a{index}", "Council A", f"{10 + index} apartment homes with parking", 10 + index))
        for index in range(40):
            rows.append(case_row(f"b{index}", "Council B", f"one-off rural dwelling at plot {index}", 1))
        return pd.DataFrame(rows)

    def test_select_queries_is_deterministic_and_stratified(self):
        cases = self.build_cases()
        counts = {"10+ units": 8, "single dwelling": 6}
        first = select_queries(cases, counts, seed=5)
        second = select_queries(cases, counts, seed=5)
        self.assertEqual(first["case_key"].tolist(), second["case_key"].tolist())
        self.assertEqual(first["query_bucket"].value_counts().to_dict(), {"10+ units": 8, "single dwelling": 6})

    def test_pick_gold_requires_text_similarity_and_same_authority(self):
        cases = self.build_cases()
        artifacts = fit_search_artifacts(cases)
        query = cases.iloc[0]
        gold = pick_gold_similarity(cases, query, artifacts, excluded_keys=set(), seed=7)
        self.assertEqual(gold["PlanningAuthority"], "Council A")
        self.assertIn("apartment", str(gold["DevelopmentDescription"]).lower())

    def test_pick_gold_excludes_already_retrieved(self):
        cases = self.build_cases()
        artifacts = fit_search_artifacts(cases)
        query = cases.iloc[0]
        gold = pick_gold_similarity(cases, query, artifacts, excluded_keys={cases.iloc[1]["case_key"]}, seed=7)
        self.assertNotEqual(gold["case_key"], cases.iloc[1]["case_key"])

    def test_pick_gold_returns_none_when_no_similar_authority_case(self):
        rows = [
            case_row("solo_a", "Council Solo", "40 apartment homes with parking", 40),
            case_row("solo_b", "Other Council", "40 apartment homes with parking", 40),
        ]
        cases = pd.DataFrame(rows)
        artifacts = fit_search_artifacts(cases)
        gold = pick_gold_similarity(cases, cases.iloc[0], artifacts, excluded_keys=set(), seed=1)
        self.assertIsNone(gold)

    def test_grade_parsing(self):
        self.assertEqual(grade_to_score("3"), 3.0)
        self.assertEqual(grade_to_score("relevant"), 2.0)
        self.assertEqual(grade_to_score("irrelevant"), 0.0)
        self.assertIsNone(grade_to_score(""))

    def test_score_benchmark_precision_and_gold_recall(self):
        grading = pd.DataFrame([
            {"query_id": "Q001", "candidate_rank": 1, "candidate_case_key": "x", "relevance": "3"},
            {"query_id": "Q001", "candidate_rank": 2, "candidate_case_key": "y", "relevance": "2"},
            {"query_id": "Q001", "candidate_rank": 3, "candidate_case_key": "z", "relevance": "0"},
            {"query_id": "Q001", "candidate_rank": 4, "candidate_case_key": "w", "relevance": "1"},
            {"query_id": "Q001", "candidate_rank": 5, "candidate_case_key": "v", "relevance": "1"},
            {"query_id": "Q001", "candidate_rank": 11, "candidate_case_key": "gold1", "relevance": "3"},
        ])
        results = score_benchmark(grading, {"Q001": "gold1"})
        self.assertAlmostEqual(results["precision_at_5"], 2 / 5)
        self.assertEqual(results["gold_recall"], 1.0)
        self.assertEqual(results["gold_total"], 1)

    def test_score_benchmark_no_grades(self):
        self.assertEqual(score_benchmark(pd.DataFrame(), {}), {"status": "no_grades"})


if __name__ == "__main__":
    unittest.main()
