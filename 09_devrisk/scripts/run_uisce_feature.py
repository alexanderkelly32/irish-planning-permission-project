"""Runner: Uisce county capacity-status features + commencement ablation.

Parses the saved county register pages into an available/constrained
ratio per county, joins schemes by county, ablates on commencement.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingRegressor  # noqa: E402

from devrisk import settings  # noqa: E402

RNG = np.random.default_rng(7)

AVAILABLE_RE = re.compile(r"capacity available|available capacity|has capacity|spare capacity", re.I)
CONSTRAINED_RE = re.compile(r"constrained|not available|no capacity|under pressure|at capacity", re.I)


if __name__ == "__main__":
    uisce_dir = settings.RAW_DIR / "infrastructure" / "uisce_counties"
    county_scores = {}
    for page in uisce_dir.glob("*.html"):
        text = page.read_text(encoding="utf-8", errors="ignore")
        county = page.stem
        available = len(AVAILABLE_RE.findall(text))
        constrained = len(CONSTRAINED_RE.findall(text))
        total = available + constrained
        county_scores[county] = {
            "uisce_available_mentions": available,
            "uisce_constrained_mentions": constrained,
            "uisce_capacity_ratio": available / max(total, 1),
        }
    scores = pd.DataFrame(county_scores).T.reset_index().rename(columns={"index": "county"})
    scores.to_csv(settings.SILVER_DIR / "uisce_county_status.csv", index=False)

    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = register[["case_key", "PlanningAuthority", "GrantDate", "NumResidentialUnits", "DevelopmentDescription"]].drop_duplicates("case_key")
    base = labels.merge(reg, on="case_key", how="inner")
    base["county"] = base["PlanningAuthority"].astype(str).str.lower().str.extract(
        r"(carlow|cavan|clare|cork|donegal|dublin|galway|kerry|kildare|kilkenny|laois|leitrim|limerick|longford|louth|mayo|meath|monaghan|offaly|roscommon|sligo|tipperary|waterford|westmeath|wexford|wicklow)")[0]
    base["county"] = base["county"].replace({"dublin": "fingal"}).fillna("")
    base = base.merge(scores, on="county", how="left")
    base["grant_dt"] = pd.to_datetime(base["GrantDate"], utc=True, errors="coerce")
    base["grant_year"] = base["grant_dt"].dt.year
    base["activation"] = pd.to_numeric(base["activation_days"], errors="coerce").clip(lower=0)
    base["log_units"] = np.log1p(pd.to_numeric(base["NumResidentialUnits"], errors="coerce").fillna(0))
    base["type_apartment"] = base["DevelopmentDescription"].fillna("").str.contains("apartment|duplex", case=False, regex=True).astype(int)
    comm = base[base["activation_linked"].astype(str).str.lower() == "true"].dropna(subset=["activation", "grant_dt"])
    train = comm[comm["grant_dt"] < pd.Timestamp("2022-01-01", tz="UTC")]
    test = comm[comm["grant_dt"] >= pd.Timestamp("2022-01-01", tz="UTC")]
    CBASE = ["log_units", "type_apartment", "grant_year"]
    UISCE = ["uisce_capacity_ratio", "uisce_constrained_mentions"]

    def run(cols):
        model = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=250, max_depth=3,
                                          learning_rate=0.05, min_samples_leaf=15, random_state=7)
        model.fit(train[cols].fillna(0.0), train["activation"])
        return np.maximum(model.predict(test[cols].fillna(0.0)), 1.0)

    p_base, p_u = run(CBASE), run(CBASE + UISCE)
    y = test["activation"].to_numpy()
    report = {
        "counties_parsed": int(len(county_scores)),
        "scheme_coverage": round(float(base["uisce_capacity_ratio"].notna().mean()), 3),
        "n_train": int(len(train)), "n_test": int(len(test)),
        "base_mae": round(float(np.mean(np.abs(y - p_base))), 0),
        "uisce_mae": round(float(np.mean(np.abs(y - p_u))), 0),
        "delta": round(float(np.mean(np.abs(y - p_u)) - np.mean(np.abs(y - p_base))), 0),
    }
    out = settings.SILVER_DIR / "uisce_status_ablation.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
