"""Runner: live updating model - landmark re-forecast.

At each observed landmark (grant -> FSC/DAC -> commencement -> first CCC
-> first sale), recompute the remaining-timeline distribution from the
conditional tables (event ledger + ccc blocks + FSC events). Outputs the
forecast-snapshot table: per landmark, median + 80% interval of time to
first sale, showing uncertainty collapse.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402


if __name__ == "__main__":
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    completion = pd.read_csv(settings.SILVER_DIR / "completion_targets.csv")
    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv")
    infra = pd.read_csv(settings.SILVER_DIR / "infrastructure_readiness_features.csv")
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = register[["case_key", "GrantDate"]].drop_duplicates("case_key")

    chain = labels.merge(reg, on="case_key", how="inner")
    chain = chain.merge(completion[["scheme_id", "t_first_ccc"]], left_on="case_key", right_on="scheme_id", how="left").drop(columns=["scheme_id"])
    exit_cols = [c for c in ("time_to_first_sale_from_grant_days",) if c not in chain.columns]
    chain = chain.merge(exit_labels[["scheme_id"] + exit_cols].rename(columns={"scheme_id": "case_key"}), on="case_key", how="left")
    chain = chain.merge(infra.drop_duplicates("case_key"), on="case_key", how="left")
    chain["activation"] = pd.to_numeric(chain["activation_days"], errors="coerce")
    chain["tfs"] = pd.to_numeric(chain["time_to_first_sale_from_grant_days"], errors="coerce")
    chain["fsc_grant_days"] = pd.to_numeric(chain["fsc_first_grant_days_from_grant"], errors="coerce")
    chain = chain[pd.to_numeric(chain["sales_linked"], errors="coerce").gt(0)]
    chain = chain.dropna(subset=["tfs"])
    chain = chain[chain["tfs"] > -90]

    def snapshot(condition, name, anchor):
        part = chain[condition]
        if len(part) < 20:
            return {"landmark": name, "n": int(len(part))}
        remaining = part["tfs"] - anchor(part)
        return {
            "landmark": name,
            "n": int(len(part)),
            "median_days_to_sale": round(float(remaining.median()), 0),
            "p10": round(float(np.percentile(remaining, 10)), 0),
            "p90": round(float(np.percentile(remaining, 90)), 0),
            "width_80": round(float(np.percentile(remaining, 90) - np.percentile(remaining, 10)), 0),
        }

    # CCC landmark uses the event-level attributed table (correct anchor).
    attribution = pd.read_csv(settings.SILVER_DIR / "ccc_sale_links_event.csv")
    attributed = attribution[attribution["status"] == "attributed"].dropna(subset=["ccc_to_sale_days"])
    report = [
        snapshot(chain["tfs"].notna(), "at_grant", lambda p: 0.0),
        snapshot(chain["fsc_grant_days"].notna() & (chain["fsc_grant_days"] >= 0), "after_fsc_grant", lambda p: p["fsc_grant_days"]),
        snapshot(chain["activation"].notna(), "after_commencement", lambda p: p["activation"]),
        {
            "landmark": "after_first_ccc (event-level attributed)",
            "n": int(len(attributed)),
            "median_days_to_sale": round(float(attributed["ccc_to_sale_days"].median()), 0),
            "p10": round(float(np.percentile(attributed["ccc_to_sale_days"], 10)), 0),
            "p90": round(float(np.percentile(attributed["ccc_to_sale_days"], 90)), 0),
            "width_80": round(float(np.percentile(attributed["ccc_to_sale_days"], 90) - np.percentile(attributed["ccc_to_sale_days"], 10)), 0),
        },
    ]
    out = settings.SILVER_DIR / "live_updating_snapshots.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
