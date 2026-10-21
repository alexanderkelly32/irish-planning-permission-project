"""Runner: build the unified event ledger (gold layer).

Every development as an event chain: planning -> FI/appeal -> JR ->
commencement -> declared end -> CCC -> sales. Only confirmed links produce
events. Writes gold/event_ledger.csv + summary.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.labels.event_ledger import build_ledger  # noqa: E402

if __name__ == "__main__":
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    pool = pd.read_parquet(settings.SILVER_DIR / "pilot_candidates_pool.parquet")
    cohort = register[register["case_key"].isin(pool["case_key"])].drop_duplicates("case_key").copy()
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    links = pd.read_csv(settings.SILVER_DIR / "bcms_links_all_granted.csv")
    overlay = settings.SILVER_DIR / "audit" / "bcms_verdict_overlay.csv"
    if overlay.exists():
        links = pd.concat([links, pd.read_csv(overlay).reindex(columns=links.columns)], ignore_index=True)
    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv")
    jr_path = settings.SILVER_DIR / "jr_events.csv"
    jr = pd.read_csv(jr_path) if jr_path.exists() else None

    ledger = build_ledger(cohort, bcms, links, exit_labels, jr)
    out = settings.GOLD_DIR / "event_ledger.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    ledger.to_csv(out, index=False)

    summary = {
        "events": int(len(ledger)),
        "developments": int(ledger["development_id"].nunique()),
        "by_event_type": ledger["event_type"].value_counts().to_dict(),
        "out": str(out),
    }
    (settings.GOLD_DIR / "event_ledger_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
