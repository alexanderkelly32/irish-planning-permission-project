"""Scalable, transparent candidate linkage for refused-to-later-granted applications."""
from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np
import pandas as pd

from revision_pairs import (
    base_application_reference,
    is_administrative_event_reference,
    normalize_address,
    normalize_outcome,
    token_similarity,
)

RESIDENTIAL_TERMS = re.compile(
    r"\b(?:apartment|apartments|dwelling|dwellings|house|houses|housing|residential|home|homes|retirement village|student accommodation|one-off|one off)\b",
    re.IGNORECASE,
)


def _slug(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _normalized_text(value: object) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())).strip()


def select_residential_scope(data: pd.DataFrame) -> pd.DataFrame:
    """Apply the same broad residential inclusion principle as the national model."""
    units = pd.to_numeric(data.get("NumResidentialUnits", pd.Series(index=data.index, dtype=float)), errors="coerce")
    descriptions = data.get("DevelopmentDescription", pd.Series(index=data.index, dtype=str)).fillna("").astype(str)
    one_off = data.get("OneOffHouse", pd.Series(index=data.index, dtype=str)).fillna("").astype(str).str.strip().str.lower()
    residential = units.gt(0) | descriptions.str.contains(RESIDENTIAL_TERMS, regex=True)
    residential |= one_off.isin({"y", "yes", "one", "single house"})
    return data.loc[residential].copy()


def _prepare(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.copy()
    defaults = {
        "ApplicationNumber": "", "DevelopmentAddress": "", "DevelopmentDescription": "",
        "DevelopmentPostcode": "", "ApplicantForename": "", "ApplicantSurname": "",
        "ITMEasting": np.nan, "ITMNorthing": np.nan, "SiteId": "",
        "NumResidentialUnits": np.nan, "LinkAppDetails": "",
    }
    for column, default in defaults.items():
        if column not in frame:
            frame[column] = default
    if "case_key" not in frame:
        frame["case_key"] = [
            f"{_slug(authority)}__{_slug(number)}"
            for authority, number in zip(frame["PlanningAuthority"], frame["ApplicationNumber"])
        ]
    frame["case_key"] = frame["case_key"].fillna("").astype(str).str.strip()
    frame["received_date_dt"] = pd.to_datetime(frame["ReceivedDate"], utc=True, errors="coerce")
    frame["outcome"] = frame["Decision"].map(normalize_outcome)
    frame["authority_key"] = frame["PlanningAuthority"].fillna("").astype(str).str.strip().str.lower()
    frame["address_key"] = frame["DevelopmentAddress"].map(normalize_address)
    frame["postcode_key"] = frame["DevelopmentPostcode"].map(_normalized_text)
    frame["applicant_key"] = (
        frame["ApplicantForename"].fillna("").astype(str) + " " + frame["ApplicantSurname"].fillna("").astype(str)
    ).map(_normalized_text)
    frame["site_key"] = frame["SiteId"].fillna("").astype(str).str.strip().str.lower()
    frame["application_reference_base"] = frame["ApplicationNumber"].map(base_application_reference)
    frame["is_administrative_event"] = frame["ApplicationNumber"].map(is_administrative_event_reference)
    frame["easting"] = pd.to_numeric(frame["ITMEasting"], errors="coerce")
    frame["northing"] = pd.to_numeric(frame["ITMNorthing"], errors="coerce")
    frame["units"] = pd.to_numeric(frame["NumResidentialUnits"], errors="coerce")
    usable = (
        frame["case_key"].ne("")
        & frame["authority_key"].ne("")
        & frame["received_date_dt"].notna()
        & frame["outcome"].isin(["REFUSED", "GRANTED"])
    )
    return frame.loc[usable].drop_duplicates("case_key").reset_index(drop=True)


def _merge_block(
    refusals: pd.DataFrame,
    grants: pd.DataFrame,
    keys: list[str],
    method: str,
    maximum_group_size: int,
) -> pd.DataFrame:
    combined = pd.concat([refusals[keys], grants[keys]], ignore_index=True)
    sizes = combined.groupby(keys, dropna=False).size().rename("block_size").reset_index()
    valid = sizes[(sizes["block_size"] >= 2) & (sizes["block_size"] <= maximum_group_size)][keys]
    if valid.empty:
        return pd.DataFrame(columns=["original_index", "revised_index", "blocking_method"])
    left = refusals.reset_index(names="original_index").merge(valid, on=keys, how="inner")
    right = grants.reset_index(names="revised_index").merge(valid, on=keys, how="inner")
    pairs = left.merge(right, on=keys, suffixes=("_original", "_revised"))
    return pairs[["original_index", "revised_index"]].assign(blocking_method=method)


def _spatial_block(
    refusals: pd.DataFrame,
    grants: pd.DataFrame,
    radius_m: float,
    maximum_cell_size: int,
) -> pd.DataFrame:
    if radius_m <= 0:
        return pd.DataFrame(columns=["original_index", "revised_index", "blocking_method"])
    valid_refusals = refusals[refusals["easting"].notna() & refusals["northing"].notna()].copy()
    valid_grants = grants[grants["easting"].notna() & grants["northing"].notna()].copy()
    for frame in (valid_refusals, valid_grants):
        frame["cell_x"] = np.floor(frame["easting"] / radius_m).astype("int64")
        frame["cell_y"] = np.floor(frame["northing"] / radius_m).astype("int64")
    cell_sizes = pd.concat([
        valid_refusals[["authority_key", "cell_x", "cell_y"]],
        valid_grants[["authority_key", "cell_x", "cell_y"]],
    ]).groupby(["authority_key", "cell_x", "cell_y"]).size()
    valid_cells = set(cell_sizes[cell_sizes <= maximum_cell_size].index)
    valid_refusals = valid_refusals[
        valid_refusals.apply(lambda row: (row["authority_key"], row["cell_x"], row["cell_y"]) in valid_cells, axis=1)
    ]
    expanded: list[pd.DataFrame] = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            shifted = valid_grants.copy()
            shifted["match_cell_x"] = shifted["cell_x"] + dx
            shifted["match_cell_y"] = shifted["cell_y"] + dy
            expanded.append(shifted)
    right = pd.concat(expanded, ignore_index=False).reset_index(names="revised_index")
    left = valid_refusals.reset_index(names="original_index")
    pairs = left.merge(
        right,
        left_on=["authority_key", "cell_x", "cell_y"],
        right_on=["authority_key", "match_cell_x", "match_cell_y"],
        suffixes=("_original", "_revised"),
    )
    distance = np.hypot(
        pairs["easting_original"] - pairs["easting_revised"],
        pairs["northing_original"] - pairs["northing_revised"],
    )
    pairs = pairs.loc[distance <= radius_m, ["original_index", "revised_index"]]
    return pairs.assign(blocking_method=f"spatial_{int(radius_m)}m")


def _score_pair(original: pd.Series, revised: pd.Series, methods: str, distance: float) -> tuple[float, str]:
    similarity = token_similarity(original["DevelopmentDescription"], revised["DevelopmentDescription"])
    score = 0.0
    if "site_id" in methods:
        score += 0.50
    if original["address_key"] and original["address_key"] == revised["address_key"]:
        score += 0.30
    if not math.isnan(distance):
        score += 0.25 if distance <= 25 else 0.15 if distance <= 100 else 0.0
    score += min(0.20, similarity * 0.20)
    if original["applicant_key"] and original["applicant_key"] == revised["applicant_key"]:
        score += 0.10
    if original["postcode_key"] and original["postcode_key"] == revised["postcode_key"]:
        score += 0.05
    # Exact text addresses are sometimes generic locality names with inconsistent
    # geocodes. Preserve these candidates for later inspection, but never let
    # them consume high/medium manual-review capacity without a SiteId match.
    if "site_id" not in methods and not math.isnan(distance) and distance > 500:
        score = min(score, 0.49)
    score = min(0.99, score)
    tier = "high" if score >= 0.75 else "medium" if score >= 0.50 else "low"
    return round(score, 3), tier


def build_full_revision_candidates(
    data: pd.DataFrame,
    maximum_gap_years: float = 5,
    spatial_radius_m: float = 50,
    maximum_group_size: int = 25,
    maximum_spatial_cell_size: int = 50,
    revised_outcome: str = "GRANTED",
) -> tuple[pd.DataFrame, dict[str, object]]:
    frame = _prepare(data)
    refusals = frame[frame["outcome"] == "REFUSED"]
    later = frame[frame["outcome"] == revised_outcome]
    blocks: list[pd.DataFrame] = []
    address_refusals = refusals[refusals["address_key"].str.len().ge(8)]
    address_later = later[later["address_key"].str.len().ge(8)]
    blocks.append(_merge_block(address_refusals, address_later, ["authority_key", "address_key"], "exact_address", maximum_group_size))
    site_refusals = refusals[refusals["site_key"].ne("")]
    site_later = later[later["site_key"].ne("")]
    blocks.append(_merge_block(site_refusals, site_later, ["authority_key", "site_key"], "site_id", maximum_group_size))
    blocks.append(_spatial_block(refusals, later, spatial_radius_m, maximum_spatial_cell_size))
    raw = pd.concat(blocks, ignore_index=True)
    if raw.empty:
        return pd.DataFrame(), {
            "input_row_count": int(len(data)), "usable_row_count": int(len(frame)),
            "refusal_row_count": int(len(refusals)), "grant_row_count": int(len(later)),
            "candidate_pair_count": 0, "blocking_method_pair_counts": {}, "linkage_tier_counts": {},
        }

    method_counts = Counter(raw["blocking_method"])
    grouped = raw.groupby(["original_index", "revised_index"])["blocking_method"].agg(lambda values: ";".join(sorted(set(values)))).reset_index()
    records: list[dict[str, object]] = []
    maximum_days = maximum_gap_years * 365.25
    for _, blocked in grouped.iterrows():
        original = frame.loc[int(blocked["original_index"])]
        revised = frame.loc[int(blocked["revised_index"])]
        gap_days = (revised["received_date_dt"] - original["received_date_dt"]).total_seconds() / 86400
        if gap_days <= 0 or gap_days > maximum_days:
            continue
        if original["application_reference_base"] and original["application_reference_base"] == revised["application_reference_base"]:
            continue
        if original["is_administrative_event"] or revised["is_administrative_event"]:
            continue
        distance = float(np.hypot(original["easting"] - revised["easting"], original["northing"] - revised["northing"]))
        score, tier = _score_pair(original, revised, blocked["blocking_method"], distance)
        records.append({
            "original_case_key": original["case_key"], "revised_case_key": revised["case_key"],
            "planning_authority": original["PlanningAuthority"],
            "original_application_number": original["ApplicationNumber"],
            "revised_application_number": revised["ApplicationNumber"],
            "original_received_date": original["received_date_dt"].date().isoformat(),
            "revised_received_date": revised["received_date_dt"].date().isoformat(),
            "gap_days": round(gap_days), "blocking_methods": blocked["blocking_method"],
            "coordinate_distance_m": round(distance, 2),
            "description_similarity": round(token_similarity(original["DevelopmentDescription"], revised["DevelopmentDescription"]), 4),
            "applicant_match": bool(original["applicant_key"] and original["applicant_key"] == revised["applicant_key"]),
            "postcode_match": bool(original["postcode_key"] and original["postcode_key"] == revised["postcode_key"]),
            "original_description": original["DevelopmentDescription"], "revised_description": revised["DevelopmentDescription"],
            "original_address": original["DevelopmentAddress"], "revised_address": revised["DevelopmentAddress"],
            "original_units": original["units"], "revised_units": revised["units"],
            "units_delta": revised["units"] - original["units"] if pd.notna(original["units"]) and pd.notna(revised["units"]) else np.nan,
            "original_source_url": original["LinkAppDetails"], "revised_source_url": revised["LinkAppDetails"],
            "linkage_score": score, "linkage_tier": tier, "manual_review_status": "pending",
            "revised_outcome": revised_outcome,
        })
    candidates = pd.DataFrame(records)
    if not candidates.empty:
        candidates = candidates.sort_values(["linkage_score", "gap_days"], ascending=[False, True]).reset_index(drop=True)
    diagnostics = {
        "input_row_count": int(len(data)), "usable_row_count": int(len(frame)),
        "refusal_row_count": int(len(refusals)), "grant_row_count": int(len(later)),
        "revised_outcome": revised_outcome,
        "candidate_pair_count": int(len(candidates)),
        "blocking_method_pair_counts": {key: int(value) for key, value in sorted(method_counts.items())},
        "linkage_tier_counts": {key: int(value) for key, value in candidates.get("linkage_tier", pd.Series(dtype=str)).value_counts().to_dict().items()},
    }
    return candidates, diagnostics


def build_stratified_review_sample(candidates: pd.DataFrame, per_tier: int = 100) -> pd.DataFrame:
    """Create a stable first audit batch across high, medium and low strength tiers."""
    if candidates.empty:
        return candidates.assign(manual_review_notes="", reviewer="", reviewed_at="")
    candidates = candidates[
        candidates.get("manual_review_status", pd.Series("pending", index=candidates.index)).eq("pending")
    ].copy()
    selected: list[pd.DataFrame] = []
    for tier in ("high", "medium", "low"):
        group = candidates[candidates["linkage_tier"] == tier].copy()
        if group.empty:
            continue
        group["_sample_order"] = pd.util.hash_pandas_object(
            group[["original_case_key", "revised_case_key"]].astype(str), index=False
        ).to_numpy()
        selected.append(group.nsmallest(per_tier, "_sample_order").drop(columns="_sample_order"))
    sample = pd.concat(selected, ignore_index=True) if selected else candidates.iloc[0:0].copy()
    sample["manual_review_notes"] = ""
    sample["reviewer"] = ""
    sample["reviewed_at"] = ""
    return sample


def _normalized_pair_key(original: object, revised: object) -> tuple[str, str]:
    normalize = lambda value: re.sub(r"[^a-z0-9]+", "", str(value or "").lower())
    return normalize(original), normalize(revised)


def audit_labels_from_review(review: pd.DataFrame) -> pd.DataFrame:
    """Convert completed review-sheet rows into the common audit-label contract."""
    required = {"original_case_key", "revised_case_key", "manual_review_status", "manual_review_notes"}
    missing = required.difference(review.columns)
    if missing:
        raise ValueError(f"review sheet is missing columns: {', '.join(sorted(missing))}")
    labels = review.loc[:, [
        "original_case_key", "revised_case_key", "manual_review_status", "manual_review_notes",
    ]].copy()
    labels["manual_review_status"] = labels["manual_review_status"].fillna("pending").astype(str).str.strip().str.lower()
    labels = labels[labels["manual_review_status"].isin({"accepted", "rejected"})]
    return labels.rename(columns={
        "manual_review_status": "audit_status",
        "manual_review_notes": "audit_notes",
    }).reset_index(drop=True)


def apply_known_audit_labels(candidates: pd.DataFrame, audit: pd.DataFrame) -> pd.DataFrame:
    """Carry existing manual decisions into a rebuilt candidate queue."""
    labelled = candidates.copy()
    if "manual_review_status" not in labelled:
        labelled["manual_review_status"] = "pending"
    labelled["manual_review_notes"] = labelled.get("manual_review_notes", "")
    allowed = {"accepted", "rejected", "pending"}
    decisions: dict[tuple[str, str], tuple[str, str]] = {}
    for _, row in audit.iterrows():
        status = str(row.get("audit_status") or "pending").strip().lower()
        if status not in allowed:
            raise ValueError(f"unsupported audit status: {status}")
        decisions[_normalized_pair_key(row["original_case_key"], row["revised_case_key"])] = (
            status, str(row.get("audit_notes") or "").strip()
        )
    for index, row in labelled.iterrows():
        decision = decisions.get(_normalized_pair_key(row["original_case_key"], row["revised_case_key"]))
        if decision:
            labelled.at[index, "manual_review_status"] = decision[0]
            labelled.at[index, "manual_review_notes"] = decision[1]
    return labelled


def evaluate_known_pair_recall(candidates: pd.DataFrame, known_pairs: pd.DataFrame) -> dict[str, object]:
    """Measure candidate recall against manually accepted pairs despite key punctuation differences."""
    candidate_keys = {
        _normalized_pair_key(row["original_case_key"], row["revised_case_key"])
        for _, row in candidates.iterrows()
    }
    missed: list[dict[str, str]] = []
    recalled = 0
    for _, row in known_pairs.iterrows():
        key = _normalized_pair_key(row["original_case_key"], row["revised_case_key"])
        if key in candidate_keys:
            recalled += 1
        else:
            missed.append({
                "original_case_key": str(row["original_case_key"]),
                "revised_case_key": str(row["revised_case_key"]),
            })
    total = int(len(known_pairs))
    return {
        "known_pair_count": total,
        "recalled_pair_count": int(recalled),
        "recall": round(recalled / total, 4) if total else None,
        "missed_pairs": missed,
    }
