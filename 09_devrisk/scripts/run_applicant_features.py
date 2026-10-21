"""Runner: applicant entity resolution + time-safe track-record features.

From applicant_index.csv (eplanning scrape): normalise applicant names into
entity keys, dedupe variants (ltd/limited, &/and, punctuation), then per
cohort scheme compute time-safe features from EARLIER applications by the
same applicant: prior count, prior grant rate, prior median activation,
prior median time-to-first-sale, prior refusal rate. Writes
applicant_entities.csv + applicant_track_record_features.csv.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402


def entity_key(name: str) -> str:
    text = str(name).lower()
    text = re.sub(r"&", " and ", text)
    text = re.sub(r"\b(ltd|limited|teo|dac|uc|clg|inc)\b\.?", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


if __name__ == "__main__":
    index_path = settings.SILVER_DIR / "applicant_index.csv"
    if not index_path.exists():
        print("applicant_index.csv not ready", flush=True)
        raise SystemExit(0)
    index = pd.read_csv(index_path)
    index = index[index["applicant_name"].fillna("").str.strip().ne("")].copy()
    index["entity_key"] = index["applicant_name"].map(entity_key)
    index["case_key"] = index["case_key"].astype(str)
    index.to_csv(settings.SILVER_DIR / "applicant_entities.csv", index=False)
    print(f"applicant rows: {len(index)} | distinct entities: {index['entity_key'].nunique()}", flush=True)

    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv")
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    frame = register.merge(labels[["case_key", "activation_days", "activation_linked"]], on="case_key", how="inner")
    frame = frame.merge(exit_labels[["scheme_id", "time_to_first_sale_from_grant_days"]],
                        left_on="case_key", right_on="scheme_id", how="left").drop(columns=["scheme_id"])
    frame["received_dt"] = pd.to_datetime(frame["ReceivedDate"], utc=True, errors="coerce")
    frame = frame.merge(index[["case_key", "entity_key", "applicant_name"]], on="case_key", how="left")

    data = frame.sort_values("received_dt").reset_index(drop=True)
    received = data["received_dt"].to_numpy()
    entities = data["entity_key"].fillna("").astype(str).to_numpy()
    grant = pd.to_datetime(data["GrantDate"], utc=True, errors="coerce").to_numpy()
    refused = data["Decision"].fillna("").astype(str).str.upper().str.contains("REFUS").to_numpy()
    activation = pd.to_numeric(data["activation_days"], errors="coerce").to_numpy()
    tfs = pd.to_numeric(data["time_to_first_sale_from_grant_days"], errors="coerce").to_numpy()

    features = {
        "applicant_prior_n": np.zeros(len(data)),
        "applicant_prior_grant_rate": np.zeros(len(data)),
        "applicant_prior_refusal_rate": np.zeros(len(data)),
        "applicant_prior_median_activation": np.zeros(len(data)),
        "applicant_prior_median_tfs": np.zeros(len(data)),
    }
    for i in range(len(data)):
        if not entities[i]:
            continue
        prior = (received < received[i]) & (entities == entities[i])
        if not prior.any():
            continue
        features["applicant_prior_n"][i] = prior.sum()
        granted_prior = (~refused) & prior
        features["applicant_prior_grant_rate"][i] = granted_prior.sum() / prior.sum()
        features["applicant_prior_refusal_rate"][i] = refused[prior].mean()
        act = activation[prior]
        act = act[~np.isnan(act)]
        if len(act):
            features["applicant_prior_median_activation"][i] = np.nanmedian(act)
        sale = tfs[prior]
        sale = sale[~np.isnan(sale)]
        if len(sale):
            features["applicant_prior_median_tfs"][i] = np.nanmedian(sale)

    out = frame[["case_key", "entity_key", "applicant_name"]].copy()
    for column, values in features.items():
        out[column] = values
    out["has_applicant"] = out["entity_key"].fillna("").ne("").astype(int)
    out["applicant_prior_n"] = np.log1p(out["applicant_prior_n"])
    out_path = settings.SILVER_DIR / "applicant_track_record_features.csv"
    out.to_csv(out_path, index=False)
    summary = {
        "cohort_rows": int(len(out)),
        "with_applicant_name": int(out["has_applicant"].sum()),
        "with_prior_track_record": int((out["applicant_prior_n"] > 0).sum()),
        "out": str(out_path),
    }
    (settings.SILVER_DIR / "applicant_features_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
