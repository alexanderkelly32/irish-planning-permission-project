#!/usr/bin/env python3
"""Benchmark the submission-time text model on the raw planning table.

This deliberately stays small: authority, numeric received year, broad
residential type, and leakage-scrubbed application description. It is intended
to answer whether the Dublin GE10 result generalises before adding enrichment.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
RAW_DATA = ROOT / "old_original_attempt" / "first_attempt_messy" / "irish_planning_dataset_clean_model.parquet"
OUTPUT_DIR = ROOT / "05_policy" / "current"

sys.path.insert(0, str(SCRIPT_DIR))
from build_dublin_submission_model import (  # noqa: E402
    bootstrap_metric_ci,
    build_simple_pipeline,
    decision_to_submission_target,
    strip_text_leakage_clues,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=["dublin", "national"], default="dublin")
    parser.add_argument("--input", type=Path, default=RAW_DATA)
    return parser.parse_args()


def clean_text(value: object) -> str:
    return str(value or "").replace("\ufffd", " ").strip()


def residential_bucket(row: pd.Series) -> str:
    text = clean_text(row.get("DevelopmentDescription")).lower()
    units = pd.to_numeric(pd.Series([row.get("NumResidentialUnits")]), errors="coerce").iloc[0]
    application_type = clean_text(row.get("ApplicationType")).lower()
    if "retention" in application_type or "retention" in text or "retain" in text:
        return "retention"
    if "change of use" in text or "change use" in text:
        return "change of use"
    if any(token in text for token in ["extension", "alteration", "renovation", "refurbishment"]):
        return "extension / alteration"
    if pd.notna(units) and units == 1:
        return "single dwelling"
    if pd.notna(units) and 2 <= units <= 9:
        return "2-9 units"
    if pd.notna(units) and units >= 10:
        return "10+ units"
    if any(token in text for token in ["one-off", "one off", "single house", "single dwelling", "house"]):
        return "single dwelling"
    return "other residential"


def add_raw_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["received_date_dt"] = pd.to_datetime(out["ReceivedDate"], utc=True, errors="coerce")
    out["received_year"] = out["received_date_dt"].dt.year.astype(float)
    out["description_stripped"] = out["DevelopmentDescription"].map(strip_text_leakage_clues)
    out["application_bucket"] = out.apply(residential_bucket, axis=1)
    targets = out["Decision"].map(decision_to_submission_target)
    out["target_refused"] = [item[0] for item in targets]
    out["target_mapping_status"] = [item[1] for item in targets]
    out["case_key"] = (
        out["PlanningAuthority"].fillna("").astype(str).str.strip()
        + "__"
        + out["ApplicationNumber"].fillna("").astype(str).str.strip()
    )
    return out


def metrics(y: pd.Series, proba: np.ndarray) -> dict[str, float | int]:
    return {
        "n": int(len(y)),
        "refusal_rate": float(y.mean()),
        "roc_auc": float(roc_auc_score(y, proba)),
        "average_precision": float(average_precision_score(y, proba)),
        "brier": float(brier_score_loss(y, proba)),
        "log_loss": float(log_loss(y, np.clip(proba, 1e-6, 1 - 1e-6))),
        **bootstrap_metric_ci(y, proba, n_boot=500),
    }


def fit_one(train: pd.DataFrame, test: pd.DataFrame) -> tuple[dict[str, object], pd.DataFrame]:
    features = ["received_year", "PlanningAuthority", "application_bucket", "description_stripped"]
    model = build_simple_pipeline(
        numeric=["received_year"],
        categorical=["PlanningAuthority", "application_bucket"],
        include_text=True,
        text_column="description_stripped",
    )
    model.fit(train[features], train["target_refused"])
    proba = model.predict_proba(test[features])[:, 1]
    scored = test[["case_key", "PlanningAuthority", "application_bucket", "target_refused", "received_date_dt"]].copy()
    scored["refusal_score"] = proba
    result: dict[str, object] = {
        "features": features,
        "train_n": int(len(train)),
        "holdout": metrics(test["target_refused"], proba),
        "holdout_by_authority": {},
        "holdout_by_bucket": {},
    }
    for column, key in [("PlanningAuthority", "holdout_by_authority"), ("application_bucket", "holdout_by_bucket")]:
        for value, group in scored.groupby(column, dropna=False):
            if group["target_refused"].nunique() < 2:
                result[key][str(value)] = {"n": int(len(group)), "status": "only_one_class"}
            else:
                result[key][str(value)] = metrics(group["target_refused"], group["refusal_score"].to_numpy())
    return result, scored


def main() -> None:
    args = parse_args()
    raw = pd.read_parquet(args.input)
    data = add_raw_features(raw)
    if args.scope == "dublin":
        authorities = {
            "Dublin City Council",
            "Dun Laoghaire Rathdown County Council",
            "Fingal County Council",
            "South Dublin County Council",
        }
        data = data[data["PlanningAuthority"].isin(authorities)].copy()

    residential_terms = r"\b(?:apartment|apartments|dwelling|dwellings|house|houses|residential|home|extension|retention|change of use|one-off|one off)\b"
    units = pd.to_numeric(data["NumResidentialUnits"], errors="coerce")
    residential = units.gt(0) | data["OneOffHouse"].fillna("").astype(str).str.strip().str.lower().isin({"y", "yes", "one", "single house"})
    residential |= data["DevelopmentDescription"].fillna("").astype(str).str.contains(residential_terms, case=False, regex=True)
    eligible = data[residential & data["target_refused"].notna() & data["received_date_dt"].notna()].copy()
    eligible = eligible.drop_duplicates("case_key").sort_values(["received_date_dt", "case_key"])
    split = max(1, int(len(eligible) * 0.8))
    train = eligible.iloc[:split].copy()
    test = eligible.iloc[split:].copy()
    if train["target_refused"].nunique() < 2 or test["target_refused"].nunique() < 2:
        raise RuntimeError("Temporal split does not contain both grant and refusal outcomes")

    result, scored = fit_one(train, test)
    result.update(
        {
            "scope": args.scope,
            "source": str(args.input),
            "eligible_n": int(len(eligible)),
            "class_balance": {
                "train_grant_rate": float(1 - train["target_refused"].mean()),
                "train_refusal_rate": float(train["target_refused"].mean()),
                "holdout_grant_rate": float(1 - test["target_refused"].mean()),
                "holdout_refusal_rate": float(test["target_refused"].mean()),
            },
            "train_start": str(train["received_date_dt"].min()),
            "train_end": str(train["received_date_dt"].max()),
            "holdout_start": str(test["received_date_dt"].min()),
            "holdout_end": str(test["received_date_dt"].max()),
        }
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prefix = f"raw_planning_{args.scope}"
    (OUTPUT_DIR / f"{prefix}_benchmark.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    scored.to_csv(OUTPUT_DIR / f"{prefix}_predictions.csv", index=False)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
