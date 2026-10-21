"""Runner: CCC->sale feature model + decomposed end-to-end retest.

A. Feature model on attributed blocks (units, block order, developer
   group, type, county, CCC month) vs the 228d constant; scheme-grouped
   split. Freeze the leg if no meaningful gain.
B. Decomposed end-to-end on corrected labels: sequential conditional
   medians (grant->commencement -> first CCC -> first sale) vs the direct
   sale model, scheme-grouped split.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingRegressor  # noqa: E402

from devrisk import settings  # noqa: E402

RNG = np.random.default_rng(7)


if __name__ == "__main__":
    blocks = pd.read_csv(settings.SILVER_DIR / "ccc_blocks.csv")
    attribution = pd.read_csv(settings.SILVER_DIR / "ccc_sale_links_event.csv")
    attributed = attribution[attribution["status"] == "attributed"].copy()
    first_by_block = attributed.groupby("block_id").agg(
        first_sale=("sale_date", "min"), ccc_to_sale=("ccc_to_sale_days", "min")).reset_index()
    data = first_by_block.merge(blocks, on="block_id", how="inner")

    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = register[["case_key", "PlanningAuthority", "NumResidentialUnits", "DevelopmentDescription"]].drop_duplicates("case_key")
    groups = pd.read_csv(settings.SILVER_DIR / "developer_groups.csv")
    data = data.merge(reg, left_on="scheme_id", right_on="case_key", how="left").drop(columns=["case_key"])
    data = data.merge(groups[["case_key", "group_id"]], left_on="scheme_id", right_on="case_key", how="left").drop(columns=["case_key"])
    data["units_log"] = np.log1p(pd.to_numeric(data["units"], errors="coerce").fillna(0))
    data["scheme_units_log"] = np.log1p(pd.to_numeric(data["NumResidentialUnits"], errors="coerce").fillna(0))
    data["ccc_month"] = pd.to_datetime(data["first_ccc"], utc=True, errors="coerce").dt.month
    data["ccc_year"] = pd.to_datetime(data["first_ccc"], utc=True, errors="coerce").dt.year
    data["type_apartment"] = data["DevelopmentDescription"].fillna("").str.contains("apartment|duplex", case=False, regex=True).astype(int)
    data["county"] = data["PlanningAuthority"].astype(str).str.lower().str.extract(
        r"(carlow|cavan|clare|cork|donegal|dublin|galway|kerry|kildare|kilkenny|laois|leitrim|limerick|longford|louth|mayo|meath|monaghan|offaly|roscommon|sligo|tipperary|waterford|westmeath|wexford|wicklow)")[0].fillna("")
    # block order within scheme
    data["ccc_abs"] = pd.to_datetime(data["first_ccc"], utc=True, errors="coerce")
    data["block_order"] = data.sort_values("ccc_abs").groupby("scheme_id").cumcount()

    scheme_keys = sorted(data["scheme_id"].unique())
    rng = np.random.default_rng(7)
    rng.shuffle(scheme_keys)
    split = int(len(scheme_keys) * 0.7)
    train_schemes, test_schemes = set(scheme_keys[:split]), set(scheme_keys[split:])
    train = data[data["scheme_id"].isin(train_schemes)]
    test = data[data["scheme_id"].isin(test_schemes)]

    FEATURES = ["units_log", "scheme_units_log", "ccc_month", "ccc_year", "type_apartment", "block_order"]
    y_tr = train["ccc_to_sale"].to_numpy()
    y_te = test["ccc_to_sale"].to_numpy()
    constant = np.median(y_tr)
    const_mae = float(np.mean(np.abs(y_te - constant)))
    gbm = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=200, max_depth=3,
                                    learning_rate=0.05, min_samples_leaf=20, random_state=7)
    gbm.fit(train[FEATURES].fillna(0.0), y_tr)
    pred = np.maximum(gbm.predict(test[FEATURES].fillna(0.0)), 1.0)
    gbm_mae = float(np.mean(np.abs(y_te - pred)))
    boot = []
    for _ in range(400):
        idx = RNG.integers(0, len(y_te), len(y_te))
        boot.append(float(np.mean(np.abs(y_te[idx] - pred[idx]))))
    report = {
        "ccc_sale_feature_model": {
            "train_blocks": int(len(train)), "test_blocks": int(len(test)),
            "constant_mae": round(const_mae, 0),
            "gbm_mae": round(gbm_mae, 0),
            "gbm_mae_ci95": [round(float(np.percentile(boot, 2.5)), 0), round(float(np.percentile(boot, 97.5)), 0)],
            "gbm_pm180": round(float(np.mean(np.abs(y_te - pred) <= 180)), 3),
            "constant_pm180": round(float(np.mean(np.abs(y_te - constant) <= 180)), 3),
        }
    }

    # ---- B. Decomposed end-to-end ----
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    completion = pd.read_csv(settings.SILVER_DIR / "completion_targets.csv")
    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv")
    chain = labels.merge(register[["case_key", "GrantDate"]].drop_duplicates("case_key"), on="case_key", how="inner")
    chain = chain.merge(completion[["scheme_id", "t_first_ccc"]], left_on="case_key", right_on="scheme_id", how="left").drop(columns=["scheme_id"])
    exit_cols = [c for c in ("sales_linked", "time_to_first_sale_from_grant_days") if c not in chain.columns]
    chain = chain.merge(exit_labels[["scheme_id"] + exit_cols].rename(columns={"scheme_id": "case_key"}),
                        on="case_key", how="left")
    chain["activation"] = pd.to_numeric(chain["activation_days"], errors="coerce")
    chain["tfs"] = pd.to_numeric(chain["time_to_first_sale_from_grant_days"], errors="coerce")
    chain = chain[chain["activation_linked"].astype(str).str.lower() == "true"]
    chain = chain[pd.to_numeric(chain["sales_linked"], errors="coerce").gt(0)]
    chain = chain.dropna(subset=["activation", "t_first_ccc", "tfs"])
    chain = chain[(chain["tfs"] - chain["activation"] - chain["t_first_ccc"]) > -365]
    chain["grant_dt"] = pd.to_datetime(chain["GrantDate"], utc=True, errors="coerce")
    chain = chain[chain["grant_dt"] < pd.Timestamp("2022-01-01", tz="UTC")]
    ccc_to_sale = chain["tfs"] - chain["activation"] - chain["t_first_ccc"]
    leg_medians = {
        "grant_to_commencement_median": float(chain["activation"].median()),
        "commencement_to_first_ccc_median": float(chain["t_first_ccc"].median()),
        "ccc_to_sale_median": float(ccc_to_sale.clip(lower=0).median()),
    }
    chain["decomposed_pred"] = chain["activation"].median() + chain["t_first_ccc"].median() + ccc_to_sale.clip(lower=0).median()
    chain["direct_pred"] = chain["tfs"].median()
    report["decomposed_vs_direct"] = {
        "n_schemes": int(len(chain)),
        **leg_medians,
        "decomposed_mae": round(float(np.mean(np.abs(chain["tfs"] - chain["decomposed_pred"]))), 0),
        "direct_mae": round(float(np.mean(np.abs(chain["tfs"] - chain["direct_pred"]))), 0),
        "decomposed_pm180": round(float(np.mean(np.abs(chain["tfs"] - chain["decomposed_pred"]) <= 180)), 3),
        "direct_pm180": round(float(np.mean(np.abs(chain["tfs"] - chain["direct_pred"]) <= 180)), 3),
        "decomposed_pm365": round(float(np.mean(np.abs(chain["tfs"] - chain["decomposed_pred"]) <= 365)), 3),
        "direct_pm365": round(float(np.mean(np.abs(chain["tfs"] - chain["direct_pred"]) <= 365)), 3),
    }
    # error budget: variance contribution of each leg
    budget = {
        "grant_to_commencement_iqr": round(float(np.percentile(chain["activation"], 75) - np.percentile(chain["activation"], 25)), 0),
        "commencement_to_ccc_iqr": round(float(np.percentile(chain["t_first_ccc"], 75) - np.percentile(chain["t_first_ccc"], 25)), 0),
        "ccc_to_sale_iqr": round(float(np.percentile(ccc_to_sale.clip(lower=0), 75) - np.percentile(ccc_to_sale.clip(lower=0), 25)), 0),
    }
    total_iqr = sum(budget.values())
    budget["share"] = {k: round(v / max(total_iqr, 1), 3) for k, v in budget.items() if k != "share"}
    report["error_budget"] = budget

    out = settings.SILVER_DIR / "ccc_sale_model_and_budget.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
