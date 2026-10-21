import unittest

import numpy as np
import pandas as pd

from related_project_validation import build_related_project_group, group_kfold_summary, split_temporal_related_project_scores


class RelatedProjectValidationTests(unittest.TestCase):
    def test_groups_site_ids_only_within_the_same_authority(self):
        frame = pd.DataFrame(
            {
                "PlanningAuthority": ["Council A", "Council A", "Council B"],
                "SiteId": ["Site-7", "site-7", "Site-7"],
                "case_key": ["a__1", "a__2", "b__1"],
            }
        )

        groups = build_related_project_group(frame)

        self.assertEqual(groups.iloc[0], groups.iloc[1])
        self.assertNotEqual(groups.iloc[0], groups.iloc[2])

    def test_uses_case_key_as_a_safe_singleton_when_site_id_is_missing(self):
        frame = pd.DataFrame(
            {"PlanningAuthority": ["Council A"], "SiteId": [None], "case_key": ["a__1"]}
        )

        self.assertEqual(build_related_project_group(frame).iloc[0], "case:a__1")

    def test_marks_holdout_rows_as_seen_only_when_the_group_exists_in_training(self):
        train = pd.DataFrame(
            {
                "PlanningAuthority": ["Council A", "Council A"],
                "SiteId": ["shared", "train-only"],
                "case_key": ["a__1", "a__2"],
            }
        )
        holdout = pd.DataFrame(
            {
                "PlanningAuthority": ["Council A", "Council A"],
                "SiteId": ["shared", "unseen"],
                "case_key": ["a__3", "a__4"],
                "target_refused": [1, 0],
                "v3_ranking_score": [0.8, 0.1],
                "v3_platt_risk": [0.7, 0.2],
            }
        )

        result = split_temporal_related_project_scores(train, holdout)

        self.assertEqual(result["seen_before"].iloc[0], True)
        self.assertEqual(result["seen_before"].iloc[1], False)
        self.assertEqual(result["group_status_counts"], {"seen_before": 1, "unseen": 1})
        self.assertTrue(np.isfinite(result["scored"]["v3_ranking_score"]).all())

    def test_uses_explicit_accepted_revision_group_when_site_id_is_missing(self):
        train = pd.DataFrame({"PlanningAuthority": ["Council A"], "SiteId": [None], "case_key": ["a__1"]})
        holdout = pd.DataFrame({"PlanningAuthority": ["Council A"], "SiteId": [None], "case_key": ["a__2"]})

        result = split_temporal_related_project_scores(
            train,
            holdout,
            explicit_group_by_case={"a__1": "revision_pair:one", "a__2": "revision_pair:one"},
        )

        self.assertEqual(result["seen_before"].tolist(), [True])
        folds = group_kfold_summary(
            pd.concat([train, holdout], ignore_index=True),
            explicit_group_by_case={"a__1": "revision_pair:one", "a__2": "revision_pair:one"},
        )
        self.assertEqual(folds, [])


if __name__ == "__main__":
    unittest.main()
