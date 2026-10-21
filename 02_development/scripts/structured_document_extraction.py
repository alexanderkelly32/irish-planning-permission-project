"""Scaled structured extraction from the document layer (decision notices + FI texts)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable

import pandas as pd

EXTRACTION_FIELDS = [
    "max_height_m",
    "height_context",
    "max_storeys",
    "front_setback_m",
    "rear_setback_m",
    "side_setback_m",
    "upper_floor_setback_m",
    "nearest_dwelling_separation_m",
    "opposing_window_separation_m",
    "parking_spaces",
    "cycle_parking_spaces",
    "private_open_space_sqm",
    "communal_open_space_sqm",
    "vehicular_access_points",
]
PLAUSIBLE_BOUNDS = {
    "max_height_m": (2.0, 150.0),
    "max_storeys": (1.0, 40.0),
    "front_setback_m": (0.0, 100.0),
    "rear_setback_m": (0.0, 100.0),
    "side_setback_m": (0.0, 50.0),
    "upper_floor_setback_m": (0.0, 30.0),
    "nearest_dwelling_separation_m": (0.0, 300.0),
    "opposing_window_separation_m": (0.0, 100.0),
    "parking_spaces": (0.0, 5000.0),
    "cycle_parking_spaces": (0.0, 10000.0),
    "private_open_space_sqm": (0.0, 200000.0),
    "communal_open_space_sqm": (0.0, 200000.0),
    "vehicular_access_points": (0.0, 20.0),
}

SYSTEM_PROMPT = """You are extracting structured building details from Irish planning application documents (decision notices, refusal schedules and further-information requests).

Rules:
- Extract only values explicitly stated in the document text. Silence is not evidence; return null for anything not stated.
- max_height_m: maximum building height in metres explicitly stated. Do not convert storeys to metres.
- height_context: "overall"|"eaves"|"ridge"|"parapet"|"other", or null when no height.
- max_storeys: maximum number of storeys explicitly stated (digits or words). Use 1.5 for "storey and a half". For ranges (e.g. "3-4 storey") return the maximum.
- setback fields: distances in metres explicitly stated for front, rear, side or upper-floor setbacks of the proposed building. Do not reuse one setback for another position.
- nearest_dwelling_separation_m / opposing_window_separation_m: distances in metres explicitly stated between the proposed building and existing neighbouring dwellings / opposing windows. Site boundary distances are NOT separation distances; do not record them.
- parking_spaces / cycle_parking_spaces: counts of proposed car / cycle parking spaces explicitly stated.
- private_open_space_sqm / communal_open_space_sqm: proposed open-space areas in square metres explicitly stated. Convert stated hectares to square metres.
- vehicular_access_points: the number of proposed vehicle entrances/access points explicitly stated.
- Return exactly one compact JSON object and nothing else:
  {
    "status": "ok|unclear",
    "max_height_m": 16.2, "height_context": "overall", "max_storeys": 5,
    "front_setback_m": null, "rear_setback_m": null, "side_setback_m": null,
    "upper_floor_setback_m": null, "nearest_dwelling_separation_m": null,
    "opposing_window_separation_m": null, "parking_spaces": 40,
    "cycle_parking_spaces": null, "private_open_space_sqm": null,
    "communal_open_space_sqm": null, "vehicular_access_points": 1,
    "confidence": "high|medium|low",
    "note": "short factual note"
  }
- Keep notes short and factual."""


def _number(value: object) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


KNOWN_COUNCILS = [
    "dublin city council",
    "south dublin county council",
    "dun laoghaire rathdown county council",
    "fingal county council",
    "cork city council",
    "cork county council",
    "galway city council",
    "galway county council",
    "limerick county council",
    "waterford city and county council",
    "kildare county council",
    "meath county council",
    "wicklow county council",
    "wexford county council",
    "louth county council",
    "donegal county council",
    "kerry county council",
    "mayo county council",
    "clare county council",
    "tipperary county council",
    "kilkenny county council",
    "laois county council",
    "offaly county council",
    "westmeath county council",
    "longford county council",
    "cavan county council",
    "monaghan county council",
    "leitrim county council",
    "sligo county council",
    "roscommon county council",
    "carlow county council",
]


def parse_authority_and_number(filename: str) -> tuple[str, str]:
    """Match a known council name and the first digit-bearing token after it."""
    lower = filename.lower()
    authority = next(
        (
            council
            for council in sorted(KNOWN_COUNCILS, key=len, reverse=True)
            if council in lower or council.replace(" ", "_") in lower
        ),
        "",
    )
    if not authority:
        return "", ""
    marker = authority if authority in lower else authority.replace(" ", "_")
    after = lower.split(marker, 1)[1]
    tokens = re.findall(r"[a-z0-9]+", after)
    number = next((token for token in tokens if re.search(r"\d", token)), "")
    return authority, number


def build_document_cohort(ocr_dir: Path, fi_dir: Path) -> pd.DataFrame:
    """Index on-disk OCR decision texts and FI texts into one cohort."""
    rows: list[dict[str, Any]] = []

    for path in sorted(Path(ocr_dir).glob("*_ocr.txt")):
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            continue
        authority, number = parse_authority_and_number(path.name)
        case_key = re.sub(r"[^a-z0-9]+", "_", f"{authority}_{number}", flags=re.IGNORECASE).strip("_").lower()
        rows.append({
            "case_key": case_key,
            "authority": authority,
            "document_type": "decision",
            "text_path": str(path),
            "doc_chars": len(text),
        })
    for path in sorted(Path(fi_dir).glob("*_fi_text.txt")):
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            continue
        authority, number = parse_authority_and_number(path.name)
        case_key = re.sub(r"[^a-z0-9]+", "_", f"{authority}_{number}", flags=re.IGNORECASE).strip("_").lower()
        rows.append({
            "case_key": case_key,
            "authority": authority,
            "document_type": "fi",
            "text_path": str(path),
            "doc_chars": len(text),
        })
    frame = pd.DataFrame(rows).drop_duplicates("text_path").reset_index(drop=True)
    frame["row_number"] = frame.index
    return frame


def chunk_text(text: str, max_chars: int = 12000, overlap: int = 300) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def build_request(custom_id: str, user_prompt: str, model: str) -> Dict[str, object]:
    return {
        "custom_id": custom_id,
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": model,
            "reasoning_effort": "minimal",
            "verbosity": "low",
            "max_completion_tokens": 500,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        },
    }


def prepare_campaign(
    cohort: pd.DataFrame,
    model: str = "gpt-5",
    max_chars_per_request: int = 12000,
    requests_per_part: int = 300,
) -> tuple[list[list[Dict[str, object]]], pd.DataFrame]:
    """Split the cohort into token-bounded request parts plus a request manifest."""
    parts: list[list[Dict[str, object]]] = []
    current: list[Dict[str, object]] = []
    manifest_rows: list[dict[str, Any]] = []
    for _, row in cohort.iterrows():
        text = Path(str(row["text_path"])).read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            continue
        chunks = chunk_text(text, max_chars_per_request)
        for chunk_index, chunk in enumerate(chunks):
            payload = {
                "row_number": int(row["row_number"]),
                "case_key": str(row["case_key"]),
                "authority": str(row["authority"]),
                "document_type": str(row["document_type"]),
                "chunk_index": chunk_index,
                "chunk_count": len(chunks),
                "text": chunk,
            }
            request = build_request(
                f"doc-extract-row-{row['row_number']}-c{chunk_index}",
                json.dumps(payload, ensure_ascii=True),
                model,
            )
            current.append(request)
            manifest_rows.append({
                "row_number": int(row["row_number"]),
                "case_key": str(row["case_key"]),
                "document_type": str(row["document_type"]),
                "chunk_index": chunk_index,
            })
            if len(current) >= requests_per_part:
                parts.append(current)
                current = []
    if current:
        parts.append(current)
    return parts, pd.DataFrame(manifest_rows)


def row_number_from_custom_id(custom_id: str) -> int | None:
    marker = "doc-extract-row-"
    if custom_id.startswith(marker):
        try:
            return int(custom_id[len(marker):].split("-c")[0])
        except (ValueError, IndexError):
            return None
    return None


def flatten_doc_batch_output(jsonl_text: str) -> pd.DataFrame:
    rows: list[Dict[str, Any]] = []
    for line in jsonl_text.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        custom_id = item.get("custom_id", "")
        row_number = row_number_from_custom_id(custom_id)
        error = item.get("error")
        if error:
            rows.append({"row_number": row_number, "api_error": json.dumps(error, ensure_ascii=True)})
            continue
        try:
            body = (item.get("response") or {}).get("body") or {}
            choices = body.get("choices") or []
            content = (choices[0].get("message") or {}).get("content")
            if isinstance(content, list):
                content = "".join(part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text")
            payload = json.loads(content)
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


def merge_campaign_results(cohort: pd.DataFrame, results: pd.DataFrame, model_version: str) -> pd.DataFrame:
    """Merge per-document extractions into the cohort with provenance columns."""
    merged = cohort.copy()
    for field in EXTRACTION_FIELDS:
        merged[f"doc_{field}"] = None
    merged["doc_status"] = ""
    merged["doc_confidence"] = ""
    merged["doc_note"] = ""
    merged["doc_extraction_model"] = ""
    by_row: dict[int, dict[str, Any]] = {}
    for _, result in results.iterrows():
        row_number = result.get("row_number")
        if row_number is None or pd.isna(row_number):
            continue
        existing = by_row.get(int(row_number))
        if existing is None or str(existing.get("confidence", "")) > str(result.get("confidence", "")):
            candidate = result.to_dict()
            for field in EXTRACTION_FIELDS:
                value = _number(candidate.get(field))
                if value is not None and field in PLAUSIBLE_BOUNDS:
                    low, high = PLAUSIBLE_BOUNDS[field]
                    if value < low or value > high:
                        candidate[field] = None
                        candidate["confidence"] = "low"
                        candidate["note"] = f"{candidate.get('note', '')} {field} implausible and dropped".strip()
            by_row[int(row_number)] = candidate
    for row_number, payload in by_row.items():
        mask = merged["row_number"] == row_number
        if not mask.any():
            continue
        index = merged.index[mask][0]
        for field in EXTRACTION_FIELDS:
            merged.at[index, f"doc_{field}"] = payload.get(field)
        merged.at[index, "doc_status"] = payload.get("status", "")
        merged.at[index, "doc_confidence"] = payload.get("confidence", "")
        merged.at[index, "doc_note"] = payload.get("note", "")
        merged.at[index, "doc_extraction_model"] = model_version
    return merged


def campaign_coverage_report(merged: pd.DataFrame) -> dict[str, Any]:
    report: dict[str, Any] = {"document_rows": int(len(merged))}
    for field in EXTRACTION_FIELDS:
        column = f"doc_{field}"
        if column not in merged.columns:
            report[field] = {"non_null": 0, "fraction": 0.0}
            continue
        values = pd.to_numeric(merged[column], errors="coerce")
        report[field] = {
            "non_null": int(values.notna().sum()),
            "fraction": round(float(values.notna().mean()), 4) if len(values) else 0.0,
        }
    return report


def apply_human_verification(campaign_merged: pd.DataFrame, human_frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Overlay the human-extracted verified tier and measure LLM extraction error rates."""
    merged = campaign_merged.copy()
    merged["_source_file"] = merged["text_path"].map(lambda value: Path(str(value)).name)
    human = human_frame.copy()
    human["_source_file"] = human["source_file"].astype(str)
    for field in EXTRACTION_FIELDS:
        merged[f"verified_{field}"] = None
        merged[f"{field}_provenance"] = ""
    human_by_file = human.set_index("_source_file") if not human.empty else pd.DataFrame()
    for source_file, row in human_by_file.iterrows():
        mask = merged["_source_file"] == source_file
        if not mask.any():
            continue
        index = merged.index[mask][0]
        for field in EXTRACTION_FIELDS:
            value = _number(row.get(f"extracted_{field}"))
            if value is not None:
                merged.at[index, f"verified_{field}"] = value
                merged.at[index, f"{field}_provenance"] = "human_verified"

    metrics: dict[str, Any] = {"human_rows": int(len(human_frame))}
    for field in EXTRACTION_FIELDS:
        if field == "height_context":
            continue
        llm_values = pd.to_numeric(merged.get(f"doc_{field}"), errors="coerce")
        human_values = pd.to_numeric(merged.get(f"verified_{field}"), errors="coerce")
        both = llm_values.notna() & human_values.notna()
        llm_only = llm_values.notna() & human_values.isna()
        human_only = llm_values.isna() & human_values.notna()
        comparable = int(both.sum())
        agreement = int((llm_values[both] == human_values[both]).sum())
        metrics[field] = {
            "human_non_null": int(human_values.notna().sum()),
            "llm_non_null": int(llm_values.notna().sum()),
            "comparable": comparable,
            "exact_agreement": agreement,
            "llm_precision": round(agreement / comparable, 4) if comparable else None,
            "llm_false_positives": int(llm_only.sum()),
            "llm_false_negatives": int(human_only.sum()),
            "llm_recall": round(agreement / (agreement + int(human_only.sum())), 4) if agreement + int(human_only.sum()) else None,
        }
    metrics["caveat"] = (
        "Comparison is restricted to the 200 human-reviewed documents. False positives include "
        "LLM values in documents the human could not confirm; false negatives are values the "
        "human found that the LLM missed."
    )
    return merged.drop(columns="_source_file"), metrics


def build_verification_sample(merged: pd.DataFrame, sample_size: int = 100, seed: int = 20260904) -> pd.DataFrame:
    """Deterministic sample with extracted values plus nulls, ready for human verification."""
    frame = merged[merged["doc_status"].ne("")].copy()
    if frame.empty:
        return pd.DataFrame()
    value_mask = pd.Series(False, index=frame.index)
    for field in EXTRACTION_FIELDS:
        value_mask |= pd.to_numeric(frame[f"doc_{field}"], errors="coerce").notna()
    with_values = frame[value_mask]
    with_nulls = frame[~value_mask]
    value_count = min(int(sample_size * 0.6), len(with_values))
    null_count = min(sample_size - value_count, len(with_nulls))
    sample = pd.concat([
        with_values.sample(n=value_count, random_state=seed),
        with_nulls.sample(n=null_count, random_state=seed),
    ], ignore_index=True)
    columns = [
        "row_number", "case_key", "authority", "document_type", "text_path",
        *[f"doc_{field}" for field in EXTRACTION_FIELDS],
        "doc_confidence", "doc_note",
    ]
    sample = sample[[column for column in columns if column in sample.columns]].copy()
    for field in EXTRACTION_FIELDS:
        sample[f"verified_{field}"] = ""
    for column in ["verified_by", "verified_at", "verify_notes"]:
        sample[column] = ""
    return sample.reset_index(drop=True)
