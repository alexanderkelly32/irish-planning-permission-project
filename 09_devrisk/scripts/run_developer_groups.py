"""Runner: developer group model (todo 6).

Resolve applicant entities into developer groups via (a) shared CRO
registered address, (b) normalised name-prefix clustering. Then per scheme
compute time-safe group-level features and a hierarchically shrunk estimate:
spv_weight = n_spv/(n_spv + k); estimate = w*spv + (1-w)*(group -> global).
Evaluates whether the shrunk group estimate beats raw applicant medians on
activation and sale timing.
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

K = 5.0


def addr_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


if __name__ == "__main__":
    cro = pd.read_csv(settings.SILVER_DIR / "applicant_entities_with_cro.csv", dtype=str)
    cro = cro[cro["company_number"].notna()].copy()
    cro["addr_key"] = cro["registered_address"].fillna("").map(addr_key)

    # Union-find over shared registered addresses (only informative ones).
    addr_groups: dict[str, set] = {}
    for _, row in cro.iterrows():
        key = row["addr_key"]
        if len(key) < 8:
            continue
        addr_groups.setdefault(key, set()).add(row["company_number"])
    parent = {num: num for num in cro["company_number"]}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for group in addr_groups.values():
        if len(group) < 2:
            continue
        root = min(group)
        for num in group:
            parent[find(num)] = find(root)
    cro["group_id"] = cro["company_number"].map(lambda num: find(num))

    # Name-prefix clustering for unmatched/unmatched-name variants.
    def prefix_key(name: str) -> str:
        text = re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()
        words = text.split()
        return " ".join(words[:3]) if words else ""
    cro["prefix"] = cro["company_name"].map(prefix_key)
    prefix_counts = cro.groupby("prefix")["company_number"].nunique()
    multi_prefixes = set(prefix_counts[prefix_counts >= 2].index)
    cro["group_id"] = np.where(cro["prefix"].isin(multi_prefixes), cro["prefix"], cro["group_id"])

    entities = cro[["case_key", "entity_key", "company_number", "company_name", "company_status", "group_id"]]
    entities.to_csv(settings.SILVER_DIR / "developer_groups.csv", index=False)

    features = pd.read_csv(settings.SILVER_DIR / "applicant_track_record_features.csv")
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv")
    frame = features.merge(labels[["case_key", "activation_days", "activation_linked"]], on="case_key", how="inner")
    frame = frame.merge(exit_labels[["scheme_id", "time_to_first_sale_from_grant_days", "sales_linked"]],
                        left_on="case_key", right_on="scheme_id", how="left").drop(columns=["scheme_id"])
    frame = frame.merge(entities[["case_key", "group_id", "company_status"]], on="case_key", how="left")
    frame["activation"] = pd.to_numeric(frame["activation_days"], errors="coerce").clip(lower=0)
    frame["tfs"] = pd.to_numeric(frame["time_to_first_sale_from_grant_days"], errors="coerce")
    frame["distressed"] = frame["company_status"].fillna("").astype(str).str.lower().str.contains(
        "dissolved|strike|liquidat|receivership", na=False).astype(int)

    report = {
        "cro_matched": int(cro["company_number"].notna().sum()),
        "groups_via_address_or_prefix": int(cro["group_id"].nunique()),
        "grouped_companies": int(cro["group_id"].notna().sum()),
        "distressed_companies_in_cohort": int(frame["distressed"].sum()),
    }

    # Group-level time-safe medians + shrunk estimate (computed on train-era
    # rows only, applied to test-era rows; era split grant <2020 / >=2020 not
    # available here, so use received-year split via register).
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    frame = frame.merge(register[["case_key", "ReceivedDate"]], on="case_key", how="left")
    frame["received_dt"] = pd.to_datetime(frame["ReceivedDate"], utc=True, errors="coerce")
    frame["received_year"] = frame["received_dt"].dt.year
    train = frame[frame["received_year"] < 2021]
    test = frame[frame["received_year"] >= 2021]

    def shrunk_estimates(part: pd.DataFrame, group_col: str, target_col: str):
        spv_med = train.groupby("entity_key")[target_col].median()
        group_med = train.groupby(group_col)[target_col].median()
        global_med = train[target_col].median()
        n_spv = train.groupby("entity_key")[target_col].size()
        preds = []
        for _, row in part.iterrows():
            spv = spv_med.get(row["entity_key"], np.nan)
            grp = group_med.get(row[group_col], global_med)
            n = n_spv.get(row["entity_key"], 0)
            w = n / (n + K)
            base = spv if not np.isnan(spv) else np.nan
            if np.isnan(base):
                preds.append(grp)
            else:
                preds.append(w * base + (1 - w) * grp)
        return np.array(preds)

    results = {}
    for target_col, mask_col, name in (("activation", "activation_linked", "activation"), ("tfs", "sales_linked", "sale")):
        if target_col == "activation":
            sub_train = train[train["activation"].notna()]
            sub_test = test[test["activation"].notna()].copy()
        else:
            sub_train = train[pd.to_numeric(train["sales_linked"], errors="coerce").gt(0)]
            sub_test = test[pd.to_numeric(test["sales_linked"], errors="coerce").gt(0)].copy()
        sub_train = sub_train[sub_train[target_col].notna()]
        sub_test = sub_test[sub_test[target_col].notna()]
        if len(sub_train) < 20 or len(sub_test) < 20:
            continue
        y_test = sub_test[target_col].to_numpy()
        spv_med = sub_train.groupby("entity_key")[target_col].median()
        group_med = sub_train.groupby("group_id")[target_col].median()
        global_med = sub_train[target_col].median()
        n_spv = sub_train.groupby("entity_key")[target_col].size()
        spv_preds, shrunk_preds, group_preds = [], [], []
        for _, row in sub_test.iterrows():
            spv = spv_med.get(row["entity_key"], np.nan)
            grp = group_med.get(row["group_id"], global_med)
            n = n_spv.get(row["entity_key"], 0)
            spv_preds.append(spv if not np.isnan(spv) else global_med)
            group_preds.append(grp)
            w = n / (n + K)
            base = spv if not np.isnan(spv) else grp
            shrunk_preds.append(w * base + (1 - w) * grp)
        results[name] = {
            "n_test": int(len(sub_test)),
            "mae_global": round(float(np.mean(np.abs(y_test - global_med))), 0),
            "mae_spv_raw": round(float(np.mean(np.abs(y_test - np.array(spv_preds)))), 0),
            "mae_group": round(float(np.mean(np.abs(y_test - np.array(group_preds)))), 0),
            "mae_shrunk": round(float(np.mean(np.abs(y_test - np.array(shrunk_preds)))), 0),
        }
    report["shrunk_estimates"] = results

    out = settings.SILVER_DIR / "developer_group_model_v1.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
