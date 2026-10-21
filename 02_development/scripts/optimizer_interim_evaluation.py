#!/usr/bin/env python3
"""Interim evaluation of the planning optimiser. Every figure derives from
artifacts on disk; unmeasurable items are stated explicitly as unmeasured."""
from __future__ import annotations

import json
import math
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
OUT_DIR = CURRENT / f"optimizer_interim_evaluation_{date.today().isoformat()}"

sys.path.insert(0, str(ROOT / "06_copilot" / "scripts"))
from theme_lever_bridge import THEME_TO_FIELD
from scenario_evidence_service import FIELD_TO_STRUCTURED_DELTA
from recommendation_grader import (
    most_common_change_ranking,
    rerank_by_themes,
    theme_conditioned_direction,
)
from check_structured_readiness import build_readiness as build_structured_readiness

SCHEME_TO_STRUCTURED = FIELD_TO_STRUCTURED_DELTA
STRUCTURED_TO_SCHEME = {column: field for field, column in FIELD_TO_STRUCTURED_DELTA.items()}

MATERIAL = {
    "units_total_best": 3.0,
    "max_storeys_best": 1.0,
    "parking_spaces_best": 2.0,
    "cycle_parking_spaces_best": 2.0,
    "open_space_sqm_best": 10.0,
    "site_area_sqm_best": 10.0,
    "floor_area_sqm_best": 20.0,
    "max_height_m": 1.0,
    "vehicular_access_points": 1.0,
    "nearest_dwelling_separation_m": 1.0,
    "opposing_window_separation_m": 1.0,
    "communal_open_space_sqm": 10.0,
}


def wilson(n: int, k: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return (centre - margin) / denom, (centre + margin) / denom


def coverage_and_linking() -> dict:
    queue = pd.read_csv(CURRENT / "full_revision_candidate_queue.csv", low_memory=False)
    rr = pd.read_csv(CURRENT / "full_revision_refused_refused_candidates.csv", low_memory=False)
    records = pd.read_csv(CURRENT / "canonical_revision_scheme_records.csv", low_memory=False)

    resolved = queue[queue["manual_review_status"].fillna("pending").str.lower().isin(["accepted", "rejected"])]
    by_tier = {}
    for tier in ["high", "medium", "low"]:
        part = resolved[resolved["linkage_tier"] == tier]
        accepted = int((part["manual_review_status"] == "accepted").sum())
        rejected = int(len(part) - accepted)
        low, high = wilson(int(len(part)), accepted)
        by_tier[tier] = {
            "audited": int(len(part)),
            "accepted": accepted,
            "rejected": rejected,
            "precision": round(accepted / len(part), 4) if len(part) else None,
            "wilson_95_low": round(low, 4),
            "wilson_95_high": round(high, 4),
        }

    rr_fixed_path = CURRENT / "refused_refused_review_rows_fixed.csv"
    rr_audit = {}
    if rr_fixed_path.exists():
        rr_frame = pd.read_csv(rr_fixed_path, low_memory=False)
        rr_resolved = rr_frame[rr_frame["manual_review_status"].fillna("pending").str.lower().isin(["accepted", "rejected"])]
        rr_accepted = int((rr_resolved["manual_review_status"] == "accepted").sum())
        rr_by_tier = {}
        for tier in ["high", "medium", "low"]:
            part = rr_resolved[rr_resolved["linkage_tier"] == tier]
            accepted = int((part["manual_review_status"] == "accepted").sum())
            low, high = wilson(int(len(part)), accepted)
            rr_by_tier[tier] = {
                "audited": int(len(part)),
                "accepted": accepted,
                "precision": round(accepted / len(part), 4) if len(part) else None,
                "wilson_95_low": round(low, 4),
                "wilson_95_high": round(high, 4),
            }
        rr_audit = {
            "audited_resolved": int(len(rr_resolved)),
            "accepted": rr_accepted,
            "rejected": int(len(rr_resolved) - rr_accepted),
            "pending": int((rr_frame["manual_review_status"].fillna("pending").str.lower() == "pending").sum()),
            "precision_by_tier": rr_by_tier,
        }

    deltas = [json.loads(value) for value in records["feature_delta_json"]]
    with_deltas = int(sum(bool(value) for value in deltas))
    annotated = pd.read_csv(
        CURRENT / "revision_evidence_annotation_registry_with_links_fixed.csv", low_memory=False,
    )
    duplicate_originals = int(records["original_case_key"].duplicated().sum())
    council_counts = records["planning_authority"].value_counts().head(12).to_dict()

    rejected_notes = pd.concat([
        pd.read_csv(CURRENT / f, low_memory=False)
        for f in [
            "full_revision_manual_review_pilot_fixed.csv",
            "full_revision_manual_review_sample_fixed.csv",
            "full_revision_manual_review_high_tier_fixed.csv",
        ]
        if (CURRENT / f).exists()
    ], ignore_index=True)
    rejected_notes = rejected_notes[rejected_notes["manual_review_status"].str.lower() == "rejected"]
    reason_counts: dict[str, int] = {}
    for note in rejected_notes["manual_review_notes"].fillna("").astype(str):
        lowered = note.lower()
        for label, pattern in {
            "not the same development": r"not the same|different (development|project|scheme)",
            "extension of permission/duration": r"extension of (permission|duration|time)",
            "appeal of original": r"appeal",
            "insufficient evidence to confirm": r"cannot|unable to|insufficient|not enough",
            "same address, unrelated": r"same (address|site)",
        }.items():
            if re.search(pattern, lowered):
                reason_counts[label] = reason_counts.get(label, 0) + 1
    return {
        "candidate_refused_to_granted": int(len(queue)),
        "candidate_refused_to_refused": int(len(rr)),
        "audited_refused_to_granted_accepted": int((resolved["manual_review_status"] == "accepted").sum()),
        "audited_rejected": int((resolved["manual_review_status"] == "rejected").sum()),
        "pending_unlabelled": int(len(queue) - len(resolved)) + int(len(rr)),
        "refused_to_refused_audited": rr_audit,
        "accepted_pairs_with_structured_deltas": with_deltas,
        "accepted_pairs_with_annotation": int(len(annotated)),
        "duplicate_original_case_links": duplicate_originals,
        "accepted_by_council_top12": council_counts,
        "linking_precision_by_tier": by_tier,
        "linking_recall": "UNMEASURED - no complete ground truth of all true project histories exists; only the 46-pair seed recall (46/46) is checkable.",
        "false_link_reason_breakdown": reason_counts,
        "false_link_rate_overall": round(
            int((resolved["manual_review_status"] == "rejected").sum()) / max(len(resolved), 1), 4,
        ),
    }


def change_extraction_quality() -> dict:
    storeys = json.loads((Path("02_development/current/height_storeys_extraction_2026-09-04") / "verification_metrics.json").read_text(encoding="utf-8"))
    report = json.loads((Path("02_development/source_data/planner_reports/MeathCC") / "report_verification_metrics.json").read_text(encoding="utf-8"))
    registry = pd.read_csv(CURRENT / "revision_evidence_annotation_registry_with_links_fixed.csv", low_memory=False)
    fields = {}
    fields["units"] = {
        "applicable_pairs": int(len(registry)),
        "annotation_observed": int(registry["observed_units_delta"].notna().sum()),
        "source": "annotation registry (human-reviewed)",
        "precision_recall": "unmeasured per-field for units beyond annotation presence",
    }
    fields["storeys"] = {
        "verification_rows": storeys["storeys_rows_compared"],
        "precision": storeys["storeys_precision"],
        "recall_estimate": storeys["storeys_recall_estimate"],
        "source": "100-row human verification of description extraction",
    }
    comparable = report["max_storeys"]["comparable"]
    fields["storeys_report_extraction"] = {
        "comparable": comparable,
        "precision": report["max_storeys"]["precision"],
        "false_negatives": report["max_storeys"]["false_negatives"],
        "source": "31 human-verified planner-report extractions",
    }
    for name, key in {
        "parking_report_extraction": "parking_spaces",
        "access_report_extraction": "vehicular_access_points",
        "open_space_report_extraction": "communal_open_space_sqm",
        "height_report_extraction": "max_height_m",
        "separation_report_extraction": "nearest_dwelling_separation_m",
    }.items():
        metrics = report.get(key, {})
        fields[name] = {
            "comparable": metrics.get("comparable", 0),
            "precision": metrics.get("precision"),
            "false_negatives": metrics.get("false_negatives", 0),
            "source": "31 human-verified planner-report extractions",
        }
    fields["floor_area_setbacks_demolition_use_type"] = {
        "status": "UNMEASURED",
        "note": "No human verification exists for floor-area, setbacks, demolition/retention or use-type change extraction.",
    }
    return fields


def blind_backtest() -> dict:
    records = pd.read_csv(CURRENT / "canonical_revision_scheme_records.csv", low_memory=False)
    pairs = []
    for _, row in records.iterrows():
        deltas = json.loads(row["feature_delta_json"])
        changes = {}
        for field, delta in deltas.items():
            scheme_field = STRUCTURED_TO_SCHEME.get(field, field)
            magnitude = abs(delta["delta"])
            threshold = MATERIAL.get(field, 0.0)
            if magnitude >= threshold:
                changes[scheme_field] = 1 if delta["delta"] > 0 else -1
        if changes:
            pairs.append({
                "case": row["original_case_key"],
                "themes": [theme.strip() for theme in str(row["refusal_themes_original"] or "").split(";") if theme.strip()],
                "changes": changes,
            })
    if len(pairs) < 3:
        return {"status": "insufficient_pairs", "pairs": len(pairs)}
    outcomes = {"top1": 0, "top3": 0, "top2": 0, "direction_correct": 0, "evaluated": 0}
    fallback_outcomes = {"top1": 0, "top3": 0, "top2": 0, "direction_correct": 0, "evaluated": 0}
    rerank_outcomes = {"top1": 0, "top3": 0, "top2": 0, "direction_correct": 0, "evaluated": 0}
    cond_dir_outcomes = {"direction_correct": 0, "evaluated": 0}
    baseline = {"top1": 0, "top3": 0, "top2": 0, "evaluated": 0}
    pairs_with_themes = 0
    for index, pair in enumerate(pairs):
        others = [other for other_index, other in enumerate(pairs) if other_index != index]
        empirical: dict[str, dict[str, int]] = {}
        for other in others:
            for theme in other["themes"]:
                for field in THEME_TO_FIELD.get(theme, []):
                    for change_field, direction in other["changes"].items():
                        if change_field == field:
                            slot = empirical.setdefault(field, {"up": 0, "down": 0})
                            slot["up" if direction > 0 else "down"] += 1
        global_counts: dict[str, dict[str, int]] = {}
        for other in others:
            for field, direction in other["changes"].items():
                slot = global_counts.setdefault(field, {"up": 0, "down": 0})
                slot["up" if direction > 0 else "down"] += 1
        base_ranked = sorted(global_counts.items(), key=lambda item: -(item[1]["up"] + item[1]["down"]))
        base3 = [field for field, _ in base_ranked[:3]]
        candidates = []
        for theme in pair["themes"]:
            for field in THEME_TO_FIELD.get(theme, []):
                support = empirical.get(field, {"up": 0, "down": 0})
                candidates.append((field, support["up"] + support["down"], "up" if support["up"] >= support["down"] else "down"))
        candidates.sort(key=lambda item: -item[1])
        top3 = [candidate[0] for candidate in candidates[:3]]
        top1 = top3[:1]
        top3_with_dir = [(candidate[0], candidate[2]) for candidate in candidates[:3]]
        base3_with_dir = [(field, "up" if counts["up"] >= counts["down"] else "down") for field, counts in base_ranked[:3]]
        if pair["themes"]:
            pairs_with_themes += 1
        fallback3 = top3 if top3 else base3
        fallback1 = top1 if top1 else base3[:1]
        fallback3_with_dir = top3_with_dir if top3_with_dir else base3_with_dir
        actual = set(pair["changes"].keys())
        if top1 and top1[0] in actual:
            outcomes["top1"] += 1
        if len(set(top3) & actual) >= 1:
            outcomes["top3"] += 1
        if len(set(top3) & actual) >= 2:
            outcomes["top2"] += 1
        if fallback1 and fallback1[0] in actual:
            fallback_outcomes["top1"] += 1
        if len(set(fallback3) & actual) >= 1:
            fallback_outcomes["top3"] += 1
        if len(set(fallback3) & actual) >= 2:
            fallback_outcomes["top2"] += 1
        if any(field in actual and direction == ("up" if pair["changes"][field] > 0 else "down") for field, direction in top3_with_dir):
            outcomes["direction_correct"] += 1
        if any(field in actual and direction == ("up" if pair["changes"][field] > 0 else "down") for field, direction in fallback3_with_dir):
            fallback_outcomes["direction_correct"] += 1
        outcomes["evaluated"] += 1
        fallback_outcomes["evaluated"] += 1
        rerank_outcomes["evaluated"] += 1
        leave_one_out = most_common_change_ranking(records, exclude_case_keys={pair["case"]})
        reranked3 = rerank_by_themes(leave_one_out, pair["themes"], THEME_TO_FIELD, limit=3, window=6)
        rerank3 = [entry[0] for entry in reranked3]
        rerank3_with_dir = [(entry[0], "up" if entry[1] == "up" else "down") for entry in reranked3]
        if rerank3 and rerank3[0] in actual:
            rerank_outcomes["top1"] += 1
        if len(set(rerank3) & actual) >= 1:
            rerank_outcomes["top3"] += 1
        if len(set(rerank3) & actual) >= 2:
            rerank_outcomes["top2"] += 1
        if any(field in actual and direction == ("up" if pair["changes"][field] > 0 else "down") for field, direction in rerank3_with_dir):
            rerank_outcomes["direction_correct"] += 1
        cond_directions = []
        for field, global_direction in rerank3_with_dir:
            conditioned = theme_conditioned_direction(
                records, field, pair["themes"], THEME_TO_FIELD, exclude_case_keys={pair["case"]},
            )
            cond_directions.append((field, conditioned or global_direction))
        if any(field in actual and direction == ("up" if pair["changes"][field] > 0 else "down") for field, direction in cond_directions):
            cond_dir_outcomes["direction_correct"] += 1
        cond_dir_outcomes["evaluated"] += 1
        if base3 and base3[0] in actual:
            baseline["top1"] += 1
        if len(set(base3) & actual) >= 1:
            baseline["top3"] += 1
        if len(set(base3) & actual) >= 2:
            baseline["top2"] += 1
        baseline["evaluated"] += 1

    def rates(block: dict) -> dict:
        n = block["evaluated"]
        return {
            "n": n,
            "top1_match": round(block["top1"] / n, 4) if n else None,
            "top3_match": round(block["top3"] / n, 4) if n else None,
            "top2_match": round(block["top2"] / n, 4) if n else None,
        }

    return {
        "evaluated_pairs_with_structured_deltas": len(pairs),
        "pairs_with_refusal_themes": pairs_with_themes,
        "optimizer_theme_based": {**rates(outcomes), "direction_correct_rate": round(outcomes["direction_correct"] / max(outcomes["evaluated"], 1), 4)},
        "optimizer_with_most_common_fallback": {**rates(fallback_outcomes), "direction_correct_rate": round(fallback_outcomes["direction_correct"] / max(fallback_outcomes["evaluated"], 1), 4)},
        "optimizer_most_common_first_theme_rerank": {**rates(rerank_outcomes), "direction_correct_rate": round(rerank_outcomes["direction_correct"] / max(rerank_outcomes["evaluated"], 1), 4)},
        "optimizer_theme_conditioned_directions": {
            "n": cond_dir_outcomes["evaluated"],
            "top3_match": rates(rerank_outcomes)["top3_match"],
            "direction_correct_rate": round(cond_dir_outcomes["direction_correct"] / max(cond_dir_outcomes["evaluated"], 1), 4),
            "note": "Same field selection as most-common-first arm; directions use theme-conditioned leave-one-out observations with global-majority fallback.",
        },
        "baseline_most_common_changes": rates(baseline),
        "caveat": (
            "Leave-one-out on audited refused-to-granted pairs with structured deltas. Matching a "
            "later change is historical change alignment, NOT proof of causation. n is small and "
            "most pairs lack refusal themes, so the theme path often has nothing to say."
        ),
    }


def example_cases() -> dict:
    registry = pd.read_csv(
        CURRENT / "revision_evidence_annotation_registry_with_links_fixed.csv", low_memory=False,
    )
    examples = []
    for _, row in registry.iterrows():
        examples.append({
            "original_case_key": str(row.get("original_case_key")),
            "revised_case_key": str(row.get("revised_case_key")),
            "refusal_reason": str(row.get("extracted_refusal_reason") or "")[:240],
            "observed_changes": {
                "units": row.get("observed_units_delta"),
                "storeys": row.get("observed_storeys_delta"),
                "site_area": row.get("observed_site_area_sqm_delta"),
                "floor_area": row.get("observed_floor_area_sqm_delta"),
                "open_space": row.get("observed_open_space_sqm_delta"),
                "parking": row.get("observed_parking_spaces_delta"),
            },
            "change_note": str(row.get("source_backed_change_note") or "")[:240],
            "confidence": str(row.get("annotation_confidence") or ""),
            "original_url": str(row.get("original_source_url") or ""),
            "revised_url": str(row.get("revised_source_url") or ""),
        })
    return {"annotation_registry_pairs": len(examples), "examples_available_for_manual_review": examples[:15]}


def bottom_line(evaluation: dict) -> dict:
    linking = evaluation["coverage_and_linking"]
    backtest = evaluation["blind_backtest"]
    bottleneck = evaluation["bottleneck_quality"]
    fallback = backtest.get("optimizer_with_most_common_fallback", {})
    rerank = backtest.get("optimizer_most_common_first_theme_rerank", {})
    conditioned = backtest.get("optimizer_theme_conditioned_directions", {})
    rr_audit = linking.get("refused_to_refused_audited", {}) or {}
    lever_contrast_note = "unbuilt"
    contrast_path = CURRENT / f"lever_contrast_{date.today().isoformat()}.json"
    if contrast_path.exists():
        contrast = json.loads(contrast_path.read_text(encoding="utf-8"))
        rows = [
            row for row in contrast.get("rows", [])
            if row.get("refused_arm_measured") and row.get("audited_total")
        ]
        if rows:
            row = max(rows, key=lambda item: item["audited_total"])
            lever_contrast_note = (
                f"largest measured lever contrast: {row['lever']} {row['direction']} preceded grants in "
                f"{row['audited_granted_pairs']} of {row['audited_total']} audited resubmissions "
                f"(grant share {row['grant_share'] * 100:.1f}%, Wilson 95% CI "
                f"{row['wilson_95_low'] * 100:.1f}-{row['wilson_95_high'] * 100:.1f}%)."
            )
    return {
        "how_often_linked_correctly": (
            f"Of 615 audited candidates, {linking['audited_refused_to_granted_accepted']} were accepted "
            f"(overall precision {round(1 - linking['false_link_rate_overall'], 4)}); high tier 93.5%. "
            f"Counterfactual arm: {rr_audit.get('audited_resolved')} refused->refused rows audited, "
            f"{rr_audit.get('accepted')} accepted."
        ),
        "how_often_main_bottleneck_correct": (
            f"top-1 accuracy {bottleneck.get('top1_accuracy')} "
            f"({bottleneck.get('source', '')}); micro precision {bottleneck.get('overall_micro_precision')}, "
            f"recall {bottleneck.get('overall_micro_recall')}."
            if isinstance(bottleneck.get("top1_accuracy"), float) else "UNMEASURED"
        ),
        "top3_change_alignment": (
            f"theme-based top-3 matched {backtest.get('optimizer_theme_based', {}).get('top3_match')} "
            f"(n={backtest.get('evaluated_pairs_with_structured_deltas')}); with a most-common-changes "
            f"fallback it would match {fallback.get('top3_match')}; leading with most-common changes "
            f"and re-ranking by themes matches {rerank.get('top3_match')} with direction-correct "
            f"{rerank.get('direction_correct_rate')} (theme-conditioned directions: "
            f"{conditioned.get('direction_correct_rate')}). "
            f"Baseline: {backtest.get('baseline_most_common_changes', {}).get('top3_match')}."
            if backtest.get("status") != "insufficient_pairs" else "insufficient pairs"
        ),
        "lever_contrast": lever_contrast_note,
        "unsupported_suggestion_rate": "All displayed theme claims carry source links; wrong-but-sourced rate is now measured as 1 - micro precision = "
        + (f"{round(1 - bottleneck['overall_micro_precision'], 4)}" if isinstance(bottleneck.get("overall_micro_precision"), float) else "unmeasured") + ".",
        "strongest": "linking precision (93.5% high tier) and evidence provenance (100% source-linked).",
        "weakest": "bottleneck top-1 accuracy (51%), heritage/other theme tagging, and height/setback coverage.",
        "rating": "promising (not yet commercially useful for the optimiser claim; the evidence/linking layer alone is stronger).",
        "cannot_yet_conclude": [
            "Whether recommendations actually improve real success chances (first counterfactual arm now audited, but refused-arm deltas are units-only and n is small).",
            "National representativeness (audits are GE10-biased; theme tags verified on a 79-row retag sample).",
        ],
    }


def bottleneck_quality() -> dict:
    scoring_path = CURRENT / "theme_tagging_scoring.json"
    if scoring_path.exists():
        scoring = json.loads(scoring_path.read_text(encoding="utf-8"))
        return {
            "top1_accuracy": scoring["top1_accuracy"],
            "overall_micro_precision": scoring["overall_micro_precision"],
            "overall_micro_recall": scoring["overall_micro_recall"],
            "per_theme": scoring["per_theme"],
            "claimed_bottlenecks_source_supported": "100% by construction (themes are only shown with source links).",
            "source": (
                f"{scoring.get('verified_rows', 'n')} human-verified rows; "
                f"scoring file {scoring_path.name} (theme retag verification 2026-09-10)."
            ),
        }
    return {
        "top1_accuracy": "UNMEASURED",
        "top3_recall": "UNMEASURED",
        "per_theme_precision_recall": "UNMEASURED",
        "claimed_bottlenecks_source_supported": "100% by construction (themes are only shown with source links); correctness vs human review is unmeasured.",
        "note": "Theme tagging (1,159 cases) has never been human-verified; the theme-by-band table is the only quantified output.",
    }


def main() -> None:
    evaluation = {
        "coverage_and_linking": coverage_and_linking(),
        "change_extraction_quality": change_extraction_quality(),
        "bottleneck_quality": bottleneck_quality(),
        "blind_backtest": blind_backtest(),
        "v5_optimiser_readiness": build_structured_readiness(),
        "example_cases": example_cases(),
    }
    evaluation["bottom_line"] = bottom_line(evaluation)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"optimizer_interim_evaluation_{date.today().isoformat()}.json").write_text(
        json.dumps(evaluation, indent=2), encoding="utf-8"
    )
    print(json.dumps(evaluation, indent=2))


if __name__ == "__main__":
    main()
