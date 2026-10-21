#!/usr/bin/env python3
"""Theme-tagging campaign for untagged refused-arm cases (DeepSeek batch).

Builds requests for accepted refused-arm rows without existing tags and with
available OCR decision text, submits a DeepSeek batch, polls, downloads, and
merges into refused_arm_themes.csv. Resume-safe across restarts.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
DECISIONS = ROOT / "02_development" / "source_data" / "refused_arm_decisions"
CAMPAIGN_DIR = CURRENT / "refused_arm_theme_campaign"
THEMES_CSV = CURRENT / "refused_arm_themes.csv"

sys.path.insert(0, str(ROOT / "02_development" / "scripts"))
from openai_batch_utils import make_deepseek_client  # noqa: E402
from run_refused_theme_tagging import SYSTEM_PROMPT, build_request, flatten  # noqa: E402

LOG = CAMPAIGN_DIR / "campaign_log.txt"


def log(message: str) -> None:
    CAMPAIGN_DIR.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    print(message, flush=True)


def main() -> None:
    log("campaign start")
    merged = pd.read_csv(CURRENT / "refused_refused_audit_merged.csv", low_memory=False)
    accepted = merged[merged["manual_review_status"].fillna("").astype(str).str.lower().eq("accepted")].copy()
    log(f"accepted rows: {len(accepted)}")

    themes = pd.read_csv(THEMES_CSV, low_memory=False)
    tagged_keys = set(themes.loc[themes["case_primary_tags"].notna(), "original_case_key"].astype(str))
    untagged = accepted[~accepted["original_case_key"].astype(str).isin(tagged_keys)].copy()
    log(f"untagged accepted rows: {len(untagged)}")

    rows = []
    with_ocr = 0
    for _, row in untagged.iterrows():
        text = ""
        url = str(row.get("original_source_url") or "")
        ref = url.rsplit("/", 2)[1] if "/" in url else ""
        if DECISIONS.exists():
            for council_dir in sorted(DECISIONS.iterdir()):
                if not council_dir.is_dir():
                    continue
                ocr_path = council_dir / "ocr_text" / f"{ref}_decision_ocr.txt"
                if ocr_path.exists():
                    text = ocr_path.read_text(encoding="utf-8", errors="replace")
                    break
        rows.append({"original_case_key": str(row.get("original_case_key")), "text": text[:14000]})
        if len(text) > 100:
            with_ocr += 1
    log(f"rows with OCR text: {with_ocr} / {len(rows)}")

    requests_path = CAMPAIGN_DIR / "batch_requests.jsonl"
    request_rows = [r for r in rows if len(r["text"]) > 100]
    requests = [build_request(f"rr-camp-{i}", json.dumps(r, ensure_ascii=True)) for i, r in enumerate(request_rows)]
    CAMPAIGN_DIR.mkdir(parents=True, exist_ok=True)
    requests_path.write_text("\n".join(json.dumps(rq, ensure_ascii=True) for rq in requests) + "\n", encoding="utf-8")
    log(f"built {len(requests)} requests")

    manifest_path = CAMPAIGN_DIR / "batch_job.json"
    client = make_deepseek_client()
    batch_id = None
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        batch_id = manifest.get("batch_id") or manifest.get("id")
        log(f"existing manifest batch_id={batch_id}")
    if batch_id:
        batch = client.batches.retrieve(batch_id)
    else:
        try:
            with requests_path.open("rb") as handle:
                uploaded = client.files.create(file=handle, purpose="user_data")
            batch = client.batches.create(input_file_id=uploaded.id, endpoint="/v1/chat/completions", completion_window="24h")
            manifest_path.write_text(json.dumps({"batch_id": batch.id, "status": batch.status, "input": str(requests_path)}, indent=2), encoding="utf-8")
            log(f"submitted batch {batch.id}")
        except Exception as exc:
            log(f"batch submit failed ({type(exc).__name__}: {str(exc)[:160]}) - falling back to sequential completions")
            batch_id = None

    if batch_id is None:
        log("sequential fallback: scoring requests one by one")
        mapped = []
        for i, row in enumerate(request_rows):
            request = requests[i]
            body = request["body"]
            try:
                completion = client.chat.completions.create(
                    model=body["model"],
                    max_completion_tokens=body.get("max_completion_tokens", 500),
                    messages=body["messages"],
                )
                content = completion.choices[0].message.content
                payload = json.loads(content)
                mapped.append({
                    "original_case_key": row["original_case_key"],
                    "case_primary_tags": payload.get("case_primary_tags", ""),
                    "case_top_primary_tag": payload.get("case_top_primary_tag", ""),
                    "confidence": payload.get("confidence", ""),
                    "evidence": json.dumps(payload.get("evidence") or {}, ensure_ascii=True),
                })
            except Exception as exc:
                log(f"row {i} failed: {type(exc).__name__} {str(exc)[:120]}")
        if mapped:
            new_tags = pd.DataFrame(mapped)
            existing = pd.read_csv(THEMES_CSV, low_memory=False)
            combined = pd.concat([existing, new_tags], ignore_index=True).drop_duplicates("original_case_key", keep="last")
            combined.to_csv(THEMES_CSV, index=False)
            newly_tagged = int(new_tags["case_primary_tags"].fillna("").astype(str).str.strip().ne("").sum())
            (CAMPAIGN_DIR / "campaign_summary.json").write_text(json.dumps({
                "mode": "sequential_fallback",
                "requests": len(requests),
                "new_rows_merged": len(new_tags),
                "newly_tagged": newly_tagged,
            }, indent=2), encoding="utf-8")
            log(f"sequential fallback done: {len(new_tags)} merged, {newly_tagged} newly tagged")
        else:
            log("sequential fallback produced no results")
        return

    deadline = time.time() + 24 * 3600
    while time.time() < deadline:
        batch = client.batches.retrieve(batch.id)
        log(f"batch {batch.id} status={batch.status}")
        if batch.status in {"completed", "failed", "expired", "cancelled"}:
            break
        time.sleep(300)
    if batch.status != "completed":
        log(f"batch ended with status {batch.status}")
        return

    output_id = getattr(batch, "output_file_id", None) or (batch.output_file_id if hasattr(batch, "output_file_id") else None)
    if not output_id:
        log("no output file id")
        return
    content = client.files.content(output_id)
    output_path = CAMPAIGN_DIR / "batch_output.jsonl"
    output_path.write_bytes(content.content)
    log(f"downloaded output {len(content.content)} bytes")

    lookup = {f"rr-camp-{i}": r["original_case_key"] for i, r in enumerate(request_rows)}
    mapped = []
    for line in output_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        key = lookup.get(item.get("custom_id"))
        if key is None:
            continue
        if item.get("error"):
            continue
        try:
            body = (item.get("response") or {}).get("body") or {}
            content_text = (body.get("choices") or [{}])[0].get("message", {}).get("content")
            if isinstance(content_text, list):
                content_text = "".join(p.get("text", "") for p in content_text if isinstance(p, dict) and p.get("type") == "text")
            payload = json.loads(content_text)
        except Exception:
            continue
        mapped.append({
            "original_case_key": key,
            "case_primary_tags": payload.get("case_primary_tags", ""),
            "case_top_primary_tag": payload.get("case_top_primary_tag", ""),
            "confidence": payload.get("confidence", ""),
            "evidence": json.dumps(payload.get("evidence") or {}, ensure_ascii=True),
        })
    new_tags = pd.DataFrame(mapped)
    if new_tags.empty:
        log("no new tags produced")
        return
    existing = pd.read_csv(THEMES_CSV, low_memory=False)
    combined = pd.concat([existing, new_tags], ignore_index=True).drop_duplicates("original_case_key", keep="last")
    combined.to_csv(THEMES_CSV, index=False)
    newly_tagged = int(new_tags["case_primary_tags"].fillna("").astype(str).str.strip().ne("").sum())
    (CAMPAIGN_DIR / "campaign_summary.json").write_text(json.dumps({
        "requests": len(requests),
        "rows_with_ocr": with_ocr,
        "new_rows_merged": len(new_tags),
        "newly_tagged": newly_tagged,
    }, indent=2), encoding="utf-8")
    log(f"done: {len(new_tags)} merged, {newly_tagged} newly tagged")


if __name__ == "__main__":
    main()
