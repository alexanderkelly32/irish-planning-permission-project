"""Prelim read: applicant identity - signal check + PPR bridge potential.

1. Does applicant track record correlate with scheme timing (activation,
   time-to-sale)?
2. Can applicant identity bridge PPR: for schemes WITHOUT sales, do their
   applicant's other schemes have known estate names we could reuse?
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
    features = pd.read_csv(settings.SILVER_DIR / "applicant_track_record_features.csv")
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv")
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")

    frame = features.merge(labels[["case_key", "activation_days", "activation_linked"]], on="case_key", how="inner")
    frame = frame.merge(exit_labels[["scheme_id", "time_to_first_sale_from_grant_days", "sales_linked"]],
                        left_on="case_key", right_on="scheme_id", how="left").drop(columns=["scheme_id"])
    frame["activation"] = pd.to_numeric(frame["activation_days"], errors="coerce").clip(lower=0)
    frame["tfs"] = pd.to_numeric(frame["time_to_first_sale_from_grant_days"], errors="coerce")

    report = {
        "coverage": {
            "cohort": int(len(frame)),
            "with_applicant": int(frame["has_applicant"].sum()),
            "with_track_record": int((frame["applicant_prior_n"] > 0).sum()),
        },
    }

    # Signal check on the track-record subset.
    tr = frame[(frame["applicant_prior_n"] > 0) & frame["activation_linked"].astype(bool)].copy()
    if len(tr) >= 20:
        report["activation_signal"] = {
            "n": int(len(tr)),
            "corr_prior_median_activation_vs_actual": round(float(np.corrcoef(tr["applicant_prior_median_activation"], tr["activation"])[0, 1]), 3) if tr["applicant_prior_median_activation"].notna().sum() >= 10 else None,
        }
    tr_sale = frame[(frame["applicant_prior_n"] > 0) & frame["sales_linked"].gt(0)].copy()
    if len(tr_sale) >= 20:
        valid = tr_sale.dropna(subset=["applicant_prior_median_tfs", "tfs"])
        report["sale_signal"] = {
            "n": int(len(valid)),
            "corr_prior_median_tfs_vs_actual": round(float(np.corrcoef(valid["applicant_prior_median_tfs"], valid["tfs"])[0, 1]), 3) if len(valid) >= 10 else None,
        }

    # PPR bridge: for schemes without sales, what estate names does their
    # applicant's sold schemes give us?
    entities = pd.read_csv(settings.SILVER_DIR / "applicant_entities.csv")
    entities["case_key"] = entities["case_key"].astype(str)
    have_sales = set(exit_labels[exit_labels["sales_linked"] > 0]["scheme_id"].astype(str))
    sold_entities = entities[entities["case_key"].isin(have_sales)]
    entity_to_estate: dict[str, list[str]] = {}
    for entity, group in sold_entities.groupby("entity_key"):
        entity_to_estate[entity] = sorted(set(group["applicant_name"].astype(str)))

    uncovered = entities[~entities["case_key"].isin(have_sales)].copy()
    uncovered["bridge_names"] = uncovered["entity_key"].map(lambda e: " || ".join(entity_to_estate.get(e, [])))
    bridgeable = uncovered[uncovered["bridge_names"].ne("")]
    report["ppr_bridge"] = {
        "uncovered_schemes_with_applicant": int(len(uncovered)),
        "bridgeable_via_same_applicant_estate_names": int(len(bridgeable)),
        "note": "applicant's sold schemes give estate names usable as pull candidates",
    }

    out = settings.SILVER_DIR / "applicant_prelim_read.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
