"""Runner: CRO financial-statements audit + time-safe features.

Schema audit: the open FS datasets are filing-metadata indexes
(file_name, company_num, submission dates, accounts-to date) - NO
balance-sheet line items (no assets/cash/equity/turnover in the open
data). Time-safe features therefore = filing recency, filing count,
accounts-to lag, dormancy (no filing in 24m pre-grant), group
aggregation. Joined by company_num (exact, not fuzzy). Commencement
ablation vs the frozen protocol + bootstrap CI.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingRegressor  # noqa: E402

from devrisk import settings  # noqa: E402

RNG = np.random.default_rng(7)


if __name__ == "__main__":
    report: dict = {}
    frames = []
    for year in ("2022", "2023", "2024"):
        frame = pd.read_csv(settings.RAW_DIR / "cro_fs" / f"fs_{year}.csv", low_memory=False, dtype=str)
        frames.append(frame)
    fs = pd.concat(frames, ignore_index=True)
    fs["company_num"] = fs["company_num"].astype(str).str.strip()
    fs["rec_dt"] = pd.to_datetime(fs["submission_rec_date"], utc=True, errors="coerce")
    fs["eff_dt"] = pd.to_datetime(fs["submission_eff_date"], utc=True, errors="coerce")
    fs["accounts_to"] = pd.to_datetime(fs["submissions_accounts_to_date"], utc=True, errors="coerce")
    report["fs_schema"] = {
        "rows_total": int(len(fs)),
        "unique_companies": int(fs["company_num"].nunique()),
        "columns": list(frames[0].columns),
        "note": "filing metadata only; no balance-sheet line items in open data",
    }

    # Join to our CRO crosswalk by company_num (exact).
    crosswalk = pd.read_csv(settings.SILVER_DIR / "applicant_entities_with_cro.csv", dtype=str)
    crosswalk = crosswalk.dropna(subset=["company_number"])
    crosswalk["company_number"] = crosswalk["company_number"].astype(str).str.strip()
    groups = pd.read_csv(settings.SILVER_DIR / "developer_groups.csv")
    crosswalk = crosswalk.merge(groups[["case_key", "group_id"]], on="case_key", how="left")
    crosswalk = crosswalk.merge(fs[["company_num", "rec_dt", "eff_dt", "accounts_to"]],
                                left_on="company_number", right_on="company_num", how="inner")
    report["match_coverage"] = {
        "companies_in_crosswalk": int(crosswalk["company_number"].nunique()),
        "companies_with_fs": int(crosswalk["company_num"].nunique()),
        "schemes_with_fs": int(crosswalk["case_key"].nunique()),
    }

    # Time-safe features at each scheme's grant date.
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = register[["case_key", "GrantDate", "NumResidentialUnits", "DevelopmentDescription"]].drop_duplicates("case_key")
    base = labels.merge(reg, on="case_key", how="inner")
    base["grant_dt"] = pd.to_datetime(base["GrantDate"], utc=True, errors="coerce")
    base["grant_year"] = base["grant_dt"].dt.year
    base["activation"] = pd.to_numeric(base["activation_days"], errors="coerce").clip(lower=0)
    base["log_units"] = np.log1p(pd.to_numeric(base["NumResidentialUnits"], errors="coerce").fillna(0))
    base["type_apartment"] = base["DevelopmentDescription"].fillna("").str.contains("apartment|duplex", case=False, regex=True).astype(int)

    rows = []
    for _, scheme in base.iterrows():
        grant = scheme["grant_dt"]
        company_filings = crosswalk[crosswalk["case_key"] == str(scheme["case_key"])]
        prior = company_filings[company_filings["rec_dt"] < grant] if len(company_filings) else company_filings
        row = {"case_key": str(scheme["case_key"])}
        if len(prior):
            row["fs_prior_filings"] = int(len(prior))
            row["fs_recency_days"] = float((grant - prior["rec_dt"].max()).days)
            row["fs_accounts_lag_days"] = float((prior["rec_dt"].max() - prior["accounts_to"].max()).days) if pd.notna(prior["accounts_to"].max()) else np.nan
            row["fs_dormant_24m"] = int((grant - prior["rec_dt"].max()).days > 730)
        else:
            row["fs_prior_filings"] = 0
            row["fs_recency_days"] = 5000.0
            row["fs_accounts_lag_days"] = np.nan
            row["fs_dormant_24m"] = 1
        rows.append(row)
    fs_features = pd.DataFrame(rows)
    fs_features.to_csv(settings.SILVER_DIR / "cro_fs_features.csv", index=False)

    data = base.merge(fs_features, on="case_key", how="left")
    comm = data[data["activation_linked"].astype(str).str.lower() == "true"].dropna(subset=["activation", "grant_dt"])
    train = comm[comm["grant_dt"] < pd.Timestamp("2022-01-01", tz="UTC")]
    test = comm[comm["grant_dt"] >= pd.Timestamp("2022-01-01", tz="UTC")]
    BASE = ["log_units", "type_apartment", "grant_year"]
    FS_COLS = [c for c in ("fs_prior_filings", "fs_recency_days", "fs_accounts_lag_days", "fs_dormant_24m") if c in data.columns]

    def run(cols):
        model = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=250, max_depth=3,
                                          learning_rate=0.05, min_samples_leaf=15, random_state=7)
        model.fit(train[cols].fillna(0.0), train["activation"])
        pred = np.maximum(model.predict(test[cols].fillna(0.0)), 1.0)
        return pred

    p_base = run(BASE)
    p_fs = run(BASE + FS_COLS)
    y = test["activation"].to_numpy()
    mae_base = float(np.mean(np.abs(y - p_base)))
    mae_fs = float(np.mean(np.abs(y - p_fs)))
    boot = []
    for _ in range(400):
        idx = RNG.integers(0, len(y), len(y))
        boot.append(float(np.mean(np.abs(y[idx] - p_fs[idx]))))
    report["ablation"] = {
        "n_train": int(len(train)), "n_test": int(len(test)),
        "base_mae": round(mae_base, 0),
        "fs_mae": round(mae_fs, 0),
        "delta": round(mae_fs - mae_base, 0),
        "fs_mae_ci95": [round(float(np.percentile(boot, 2.5)), 0), round(float(np.percentile(boot, 97.5)), 0)],
    }
    out = settings.SILVER_DIR / "cro_fs_ablation.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
