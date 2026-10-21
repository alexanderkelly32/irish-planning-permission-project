"""Smoke-verify the previously extracted GE10 unit counts.

Samples rows from ground_source_storeys_verified.csv whose register units are
NULL (extraction was the only source - DLRCOCO, Dublin City, South Dublin,
Fingal, Cork County are the big blocks), re-extracts the unit total from the
description with the same strict prompt, and compares against the stored value.

READ-ONLY: the ground-source CSV is never modified.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "02_development" / "current"
OUT_DIR = CURRENT / "ge10_units_smoke_2026-09-19"
SOURCE = CURRENT / "height_storeys_extraction_2026-09-04" / "ground_source_storeys_verified.csv"

SYSTEM_PROMPT = """You are extracting the total number of residential units proposed in an Irish planning application description.

Rules:
- The total is the sum of all dwelling types stated (houses + apartments + duplexes + units + dwellings).
- Count only units the application PROPOSES to build or convert to residential use.
- If the description does not state a total or the component counts, return null - silence is not evidence.
- Return exactly one compact JSON object and nothing else:
  {"units": 42}  or  {"units": null}
"""


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    source = pd.read_csv(SOURCE, low_memory=False)
    register = pd.to_numeric(source["NumResidentialUnits"], errors="coerce")
    extracted = pd.to_numeric(source["units_total_best"], errors="coerce")
    pool = source[register.isna() & extracted.notna()].copy()

    authorities = [
        "Cork County Council",
        "Dun Laoghaire Rathdown County Council",
        "Dublin City Council",
        "South Dublin County Council",
        "Fingal County Council",
    ]
    parts = []
    per_authority = max(8, 40 // len(authorities))
    for authority in authorities:
        group = pool[pool["PlanningAuthority"] == authority]
        parts.append(group.sample(n=min(per_authority, len(group)), random_state=19))
    sample = pd.concat(parts, ignore_index=True)

    requests = []
    rows = []
    for index, (_, row) in enumerate(sample.iterrows()):
        description = str(row.get("DevelopmentDescription") or "")[:4000]
        requests.append({
            "custom_id": f"smoke-{index}",
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": "deepseek-v4-pro",
                "max_completion_tokens": 200,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps({"description": description}, ensure_ascii=True)},
                ],
            },
        })
        rows.append({
            "case_key": str(row.get("case_key")),
            "authority": str(row.get("PlanningAuthority")),
            "stored_units_total_best": float(row["units_total_best"]) if pd.notna(row.get("units_total_best")) else None,
            "description": description,
        })
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT_DIR / "sample.csv", index=False)
    (OUT_DIR / "batch_requests_part01.jsonl").write_text(
        "\n".join(json.dumps(request, ensure_ascii=True) for request in requests) + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(ROOT / "02_development" / "scripts" / "run_deepseek_extraction.py"),
         "--out-dir", str(OUT_DIR), "--model", "deepseek-v4-pro", "--parts", "1"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    print(result.stdout[-400:])

    extracted_values: dict[int, float | None] = {}
    output_path = OUT_DIR / "batch_output_part01.jsonl"
    for line in output_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        custom_id = item.get("custom_id", "")
        index = int(custom_id.rsplit("-", 1)[1]) if custom_id.startswith("smoke-") else None
        if item.get("error") or index is None:
            continue
        try:
            content = (item.get("response") or {}).get("body", {}).get("choices", [{}])[0].get("message", {}).get("content")
            payload = json.loads(content) if content else {}
            extracted_values[index] = payload.get("units")
        except Exception:
            continue

    comparisons = []
    for index, row in frame.iterrows():
        new_value = extracted_values.get(index)
        stored = pd.to_numeric(row.get("stored_units_total_best"), errors="coerce")
        comparisons.append({
            "case_key": row["case_key"],
            "authority": row["authority"],
            "stored": float(stored) if pd.notna(stored) else None,
            "re_extracted": float(new_value) if new_value is not None else None,
            "agrees": bool(pd.notna(stored) and new_value is not None and abs(float(stored) - float(new_value)) <= max(0.5, float(stored) * 0.05)),
        })
    results = pd.DataFrame(comparisons)
    results.to_csv(OUT_DIR / "comparison.csv", index=False)
    both = results.dropna(subset=["stored", "re_extracted"])
    agree = int(both["agrees"].sum()) if not both.empty else 0
    by_authority = {}
    for authority, group in results.groupby("authority"):
        g = group.dropna(subset=["stored", "re_extracted"])
        by_authority[authority] = {
            "n": int(len(g)),
            "agreement": round(float(g["agrees"].mean()), 3) if len(g) else None,
        }
    summary = {
        "sampled": int(len(results)),
        "re_extracted_nonnull": int(results["re_extracted"].notna().sum()),
        "compared": int(len(both)),
        "agreement_rate": round(agree / len(both), 4) if len(both) else None,
        "by_authority": by_authority,
        "disagreements": results[~results["agrees"] & results["re_extracted"].notna() & results["stored"].notna()][["case_key", "authority", "stored", "re_extracted"]].to_dict("records"),
    }
    (OUT_DIR / "smoke_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
