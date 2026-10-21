"""Task 2 extraction: max height and storeys from GE10 development descriptions."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable

import pandas as pd

STOREY_PATTERN = re.compile(r"\bstoreys?\b", re.IGNORECASE)
HEIGHT_PATTERN = re.compile(
    r"\bheight\b|(?:\d+(?:\.\d+)?)\s*(?:m|metres|meters)\s*(?:high|in height)|\b(?:eaves|ridge|parapet)\b",
    re.IGNORECASE,
)

EXTRACTION_FIELDS = ["max_height_m", "height_context", "max_storeys", "upper_floor_setback_m"]
PLAUSIBLE_BOUNDS = {
    "max_height_m": (2.0, 150.0),
    "max_storeys": (1.0, 40.0),
    "upper_floor_setback_m": (0.0, 30.0),
}

SYSTEM_PROMPT = """You are extracting structured building dimensions from Irish planning application development descriptions.

Rules:
- Use only the DevelopmentDescription text provided. Silence is not evidence.
- Extract only values that are explicitly supported by the text. If not supported, return null.
- max_height_m: the maximum building height in metres explicitly stated (e.g. "18m high", "height of 16.2m"). Convert metres only; do not convert storeys into metres.
- height_context: one of "overall", "eaves", "ridge", "parapet", "other" describing what the stated height refers to, or null when no height is extracted.
- max_storeys: the maximum number of storeys explicitly stated (e.g. "6 storey", "three storey"). Return the number, not a range.
- upper_floor_setback_m: a setback in metres explicitly stated for an upper floor or top storey only; do not use ground-floor setbacks.
- If a value is ambiguous between interpretations, return null for that field and say so in the note.
- Return exactly one compact JSON object and nothing else:
  {
    "status": "ok|unclear",
    "max_height_m": 18.0,
    "height_context": "overall",
    "max_storeys": 6,
    "upper_floor_setback_m": null,
    "confidence": "high|medium|low",
    "note": "short factual note"
  }
- Keep notes short and factual."""


def select_rows(frame: pd.DataFrame) -> pd.DataFrame:
    text = frame["DevelopmentDescription"].fillna("").astype(str)
    mask = text.str.contains(STOREY_PATTERN) | text.str.contains(HEIGHT_PATTERN)
    selected = frame.loc[mask].copy()
    selected["_selected_by_storey"] = text.loc[mask].str.contains(STOREY_PATTERN)
    selected["_selected_by_height"] = text.loc[mask].str.contains(HEIGHT_PATTERN)
    return selected


def build_user_prompt(row_number: int, row: Dict[str, Any]) -> str:
    payload = {
        "row_number": row_number,
        "PlanningAuthority": str(row.get("PlanningAuthority") or ""),
        "ApplicationNumber": str(row.get("ApplicationNumber") or ""),
        "case_key": str(row.get("case_key") or ""),
        "DevelopmentDescription": str(row.get("DevelopmentDescription") or ""),
    }
    return json.dumps(payload, ensure_ascii=True)


def make_request(custom_id: str, user_prompt: str, model: str) -> Dict[str, object]:
    return {
        "custom_id": custom_id,
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": model,
            "reasoning_effort": "minimal",
            "verbosity": "low",
            "max_completion_tokens": 320,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        },
    }


def build_batch_requests(selected: pd.DataFrame, model: str = "gpt-5") -> list[Dict[str, object]]:
    requests: list[Dict[str, object]] = []
    for row_number, row in selected.iterrows():
        custom_id = f"structured-extract-row-{row_number}"
        requests.append(make_request(custom_id, build_user_prompt(row_number, row.to_dict()), model))
    return requests


def row_number_from_custom_id(custom_id: str) -> int | None:
    marker = "structured-extract-row-"
    if custom_id.startswith(marker):
        try:
            return int(custom_id[len(marker):])
        except ValueError:
            return None
    return None


def extract_message_content(body: Dict[str, Any]) -> str:
    choices = body.get("choices") or []
    if not choices:
        raise ValueError("No choices in batch response body.")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"]
        if parts:
            return "".join(parts)
    raise ValueError("Unable to extract message content from batch response body.")


def flatten_batch_output(jsonl_text: str) -> pd.DataFrame:
    rows: list[Dict[str, Any]] = []
    for line in jsonl_text.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        row_number = row_number_from_custom_id(item.get("custom_id", ""))
        error = item.get("error")
        if error:
            rows.append({"row_number": row_number, "api_error": json.dumps(error, ensure_ascii=True)})
            continue
        try:
            payload = json.loads(extract_message_content((item.get("response") or {}).get("body") or {}))
            row: Dict[str, Any] = {"row_number": row_number, "api_error": ""}
            for field in EXTRACTION_FIELDS:
                row[field] = payload.get(field)
            row["status"] = payload.get("status", "")
            row["confidence"] = payload.get("confidence", "")
            row["note"] = payload.get("note", "")
            rows.append(row)
        except Exception as exc:
            rows.append({"row_number": row_number, "api_error": str(exc)})
    return pd.DataFrame(rows).sort_values("row_number").reset_index(drop=True)


def _number(value: object) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def apply_plausibility(row: pd.Series) -> pd.Series:
    out = row.copy()
    for field, (low, high) in PLAUSIBLE_BOUNDS.items():
        value = _number(out.get(field))
        if value is not None and (value < low or value > high):
            out[field] = None
            note = str(out.get("note") or "")
            out["note"] = (note + f" {field} implausible and dropped").strip()
            out["confidence"] = "low"
    return out


def merge_results(ground_source: pd.DataFrame, results: pd.DataFrame, model_version: str) -> pd.DataFrame:
    """Merge batch extractions into the GE10 frame with provenance columns."""
    frame = ground_source.copy()
    for field in ["max_height_m", "height_context", "max_storeys", "upper_floor_setback_m", "confidence", "note"]:
        frame[f"llm_{field}"] = None
    frame["llm_extraction_status"] = ""
    frame["llm_extraction_model"] = ""
    merged = results.set_index("row_number") if not results.empty else pd.DataFrame()
    for row_number, row in frame.iterrows():
        if merged.empty or row_number not in merged.index:
            continue
        result = apply_plausibility(merged.loc[row_number])
        frame.at[row_number, "llm_extraction_status"] = result.get("status", "")
        frame.at[row_number, "llm_extraction_model"] = model_version
        for field in ["max_height_m", "height_context", "max_storeys", "upper_floor_setback_m", "confidence", "note"]:
            frame.at[row_number, f"llm_{field}"] = result.get(field)
    return frame


def build_verification_sample(merged: pd.DataFrame, sample_size: int = 100, seed: int = 20260904) -> pd.DataFrame:
    """Deterministic verification sample: mostly extracted-value rows plus null rows."""
    frame = merged[merged["llm_extraction_status"].ne("")].copy()
    if frame.empty:
        return pd.DataFrame()
    with_values = frame[pd.to_numeric(frame["llm_max_height_m"], errors="coerce").notna() | pd.to_numeric(frame["llm_max_storeys"], errors="coerce").notna()]
    with_nulls = frame[pd.to_numeric(frame["llm_max_height_m"], errors="coerce").isna() & pd.to_numeric(frame["llm_max_storeys"], errors="coerce").isna()]
    value_count = min(int(sample_size * 0.6), len(with_values))
    null_count = min(sample_size - value_count, len(with_nulls))
    selected = pd.concat([
        with_values.sample(n=value_count, random_state=seed),
        with_nulls.sample(n=null_count, random_state=seed),
    ], ignore_index=True)
    columns = [
        "case_key", "PlanningAuthority", "ApplicationNumber", "DevelopmentDescription",
        "llm_max_height_m", "llm_height_context", "llm_max_storeys", "llm_upper_floor_setback_m",
        "llm_confidence", "llm_note",
    ]
    sample = selected[[column for column in columns if column in selected.columns]].copy()
    for column in ["verified_height_m", "verified_storeys", "verified_upper_floor_setback_m", "verified_by", "verified_at", "verify_notes"]:
        sample[column] = ""
    return sample.reset_index(drop=True)


def apply_verification(merged: pd.DataFrame, verification: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Overlay human-verified values and measure extraction error rates."""
    required = {"case_key", "verified_storeys", "verified_height_m", "verified_upper_floor_setback_m"}
    missing = required.difference(verification.columns)
    if missing:
        raise ValueError(f"verification sheet is missing columns: {', '.join(sorted(missing))}")
    frame = merged.copy()
    verified_rows = verification.set_index("case_key") if not verification.empty else pd.DataFrame()
    for field, column in [
        ("storeys", "verified_storeys"),
        ("height_m", "verified_height_m"),
        ("upper_floor_setback_m", "verified_upper_floor_setback_m"),
    ]:
        frame[f"verified_{field}"] = None
        frame[f"{field}_provenance"] = ""
        if verified_rows.empty:
            continue
        for case_key in verified_rows.index:
            if case_key not in frame.index and case_key not in frame["case_key"].values:
                continue
            row = verified_rows.loc[case_key]
            value = _number(row.get(column))
            mask = frame["case_key"] == case_key
            if not mask.any():
                continue
            idx = frame.index[mask][0]
            frame.at[idx, f"verified_{field}"] = value
            if value is not None:
                frame.at[idx, f"{field}_provenance"] = "verified"
    llm_storeys = pd.to_numeric(frame["llm_max_storeys"], errors="coerce")
    llm_height = pd.to_numeric(frame["llm_max_height_m"], errors="coerce")
    verified_storeys = pd.to_numeric(frame["verified_storeys"], errors="coerce")
    verified_height = pd.to_numeric(frame["verified_height_m"], errors="coerce")
    frame["storeys_final"] = verified_storeys.fillna(llm_storeys)
    frame["storeys_final"] = frame["storeys_final"].fillna(
        pd.to_numeric(frame["max_storeys_best"], errors="coerce").where(lambda s: s.between(1, 40))
    )
    frame["height_final_m"] = verified_height.fillna(llm_height)
    sample_mask = frame["case_key"].isin(set(verification["case_key"]))
    sample_llm_storeys = llm_storeys[sample_mask]
    sample_llm_height = llm_height[sample_mask]
    sample_verified_storeys = verified_storeys[sample_mask]
    sample_verified_height = verified_height[sample_mask]
    both_storeys = sample_llm_storeys.notna() & sample_verified_storeys.notna()
    both_height = sample_llm_height.notna() & sample_verified_height.notna()
    false_pos_storeys = int((sample_llm_storeys.notna() & sample_verified_storeys.isna()).sum())
    false_neg_storeys = int((sample_llm_storeys.isna() & sample_verified_storeys.notna()).sum())
    agreement_storeys = int((sample_llm_storeys[both_storeys] == sample_verified_storeys[both_storeys]).sum())
    comparable_storeys = int(both_storeys.sum())
    comparable_height = int(both_height.sum())
    agreement_height = int((sample_llm_height[both_height] == sample_verified_height[both_height]).sum())
    metrics = {
        "verification_rows": int(len(verification)),
        "storeys_rows_compared": comparable_storeys,
        "storeys_exact_agreement": agreement_storeys,
        "storeys_precision": round(agreement_storeys / comparable_storeys, 4) if comparable_storeys else None,
        "storeys_false_positives": false_pos_storeys,
        "storeys_false_negatives": false_neg_storeys,
        "storeys_recall_estimate": round(
            agreement_storeys / (agreement_storeys + false_neg_storeys), 4
        ) if agreement_storeys + false_neg_storeys else None,
        "height_rows_compared": comparable_height,
        "height_exact_agreement": agreement_height,
        "note": (
            "Storeys precision measures how often an extracted value matched verification; "
            "false positives include rows that were unverifiable (truncated descriptions), not "
            "only genuine errors."
        ),
    }
    return frame, metrics


def extraction_summary(merged: pd.DataFrame) -> dict[str, Any]:
    selected = merged[merged["llm_extraction_status"].ne("")]
    height = pd.to_numeric(selected.get("llm_max_height_m"), errors="coerce")
    storeys = pd.to_numeric(selected.get("llm_max_storeys"), errors="coerce")
    setback = pd.to_numeric(selected.get("llm_upper_floor_setback_m"), errors="coerce")
    return {
        "batch_rows": int(len(selected)),
        "height_extracted": int(height.notna().sum()),
        "storeys_extracted": int(storeys.notna().sum()),
        "upper_floor_setback_extracted": int(setback.notna().sum()),
        "confidence_counts": selected.get("llm_confidence").value_counts().to_dict() if not selected.empty else {},
        "note": (
            "Extracted values are LLM extractions with plausibility filters; they remain "
            "unverified until the verification sample is checked."
        ),
    }
