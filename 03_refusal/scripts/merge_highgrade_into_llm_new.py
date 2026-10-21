"""Merge the 150 high-grade OCR LLM extractions into llm_new (display source).

The 150 docs are re-extractions of weak rows already in the pool. The merge
only APPENDS cases that improve on what exists:
  - absent from llm_new AND master, or
  - present with reason_count == 0 and now has reasons (upgrade).
Precision-first: inferred reasons (schedule missing) get status='unclear',
tag_confidence='low' and NO case_top_primary_tag - they never enter the
theme-transfer evaluation. The canonical master is never modified.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

LLM_NEW = ROOT / "03_refusal" / "current" / "refusal_reasons_cases_llm_new.csv"
MASTER = ROOT / "03_refusal" / "current" / "refusal_reasons_cases_master.csv"
OUT_DIR = ROOT / "09_devrisk" / "data" / "silver" / "llm_highgrade_full"

INFERRED_HINTS = re.compile(
    r"(not provided|not included|typical refusal grounds|based on typical|"
    r"not provided in the text|does not (include|contain)|are not included)",
    re.IGNORECASE,
)


def parse_content(body: str) -> dict | None:
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    found = re.search(r'"found"\s*:\s*(\d)', body)
    if not found or found.group(1) != "1":
        return None
    return {"found": 1, "reasons": [], "notes": "truncated response; skipped for reasons"}


def snake_key(custom_id: str) -> tuple[str, str, str]:
    council, appno = str(custom_id).split("_", 1)
    return re.sub(r"[^a-z0-9]+", "_", council.lower()).strip("_") + "_" + re.sub(r"[^a-z0-9]+", "_", appno.lower()).strip("_"), council, appno


if __name__ == "__main__":
    existing = pd.read_csv(LLM_NEW, low_memory=False) if LLM_NEW.exists() else pd.DataFrame()
    existing["case_key"] = existing["case_key"].astype(str)
    existing["reason_count"] = pd.to_numeric(existing["reason_count"], errors="coerce").fillna(0)
    existing_rc = dict(zip(existing["case_key"], existing["reason_count"]))

    master = pd.read_csv(MASTER, low_memory=False)
    master["case_key"] = master["case_key"].astype(str)
    master_rc = dict(zip(master["case_key"], pd.to_numeric(master["reason_count"], errors="coerce").fillna(0)))

    rows = []
    for path in sorted(OUT_DIR.glob("batch_output_part*.jsonl")):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            custom_id = str(obj.get("custom_id", ""))
            if not custom_id or "_" not in custom_id:
                continue
            case_key, council, appno = snake_key(custom_id)
            old_rc = existing_rc.get(case_key, master_rc.get(case_key))
            if old_rc is not None and old_rc > 0:
                continue  # already has reasons; nothing to add
            body = obj["response"]["body"]["choices"][0]["message"]["content"]
            data = parse_content(body)
            if data is None or data.get("found") != 1 or not data.get("reasons"):
                continue
            notes = str(data.get("notes") or "")
            inferred = bool(INFERRED_HINTS.search(notes))
            reason_texts = []
            cats = set()
            for item in data["reasons"]:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("t") or "").strip()
                if not text:
                    continue
                reason_texts.append(text)
                cats.update(str(c) for c in item.get("cats", []) if str(c).strip())
            if not reason_texts:
                continue
            tags = sorted(cats)
            rows.append({
                "case_key": case_key,
                "council": council,
                "application_number": appno,
                "decision": "REFUSED",
                "decision_date": "",
                "status": "unclear" if inferred else "ok",
                "reason_count": len(reason_texts),
                "reasons_joined": " || ".join(reason_texts),
                "case_primary_tags": ";".join(tags),
                "case_top_primary_tag": "" if inferred else (tags[0] if tags else ""),
                "tag_evidence": "{}",
                "tag_confidence": "low" if inferred else "high",
                "tag_extraction_model": "deepseek-v4-pro",
                "note": notes[:200],
            })

    new = pd.DataFrame(rows)
    if new.empty:
        print("no rows to merge", flush=True)
    else:
        tagged = int((new["case_top_primary_tag"] != "").sum())
        print(f"new/upgraded cases: {len(new)} (tagged {tagged}, unclear {len(new) - tagged})", flush=True)
        merged = pd.concat([existing, new.reindex(columns=existing.columns)], ignore_index=True)
        merged.to_csv(LLM_NEW, index=False)
        print(f"llm_new now {len(merged)} rows -> {LLM_NEW}")
