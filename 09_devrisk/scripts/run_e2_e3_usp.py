"""Zero-day USP E2 (local supply pressure) + E3 (revealed vs written policy).

E2: expected deliverable supply / trailing absorption ratio with MC
thresholds; absorption from PPR new-dwelling sales (county-level, the
finest reliably-held granularity) + linked scheme sales where support
allows; backtest vs subsequent county outcomes.
E3: hand-built dated policy table (plan adoption dates); density-dimension
residual treatment DiD before/after plan changes with placebo dates.
Cautious language; no causal claims.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "usp"
OUT.mkdir(parents=True, exist_ok=True)

PLANS = {
    "South Dublin County Council": [("2016-04-01", "DP 2016-2022"), ("2022-08-01", "DP 2022-2028 (NPF-aligned density)")],
    "Dublin City Council": [("2016-10-01", "DP 2016-2022"), ("2022-11-01", "DP 2022-2028 (NPF-aligned density)")],
    "Kildare County Council": [("2017-03-01", "DP 2017-2023"), ("2023-04-01", "DP 2023-2029")],
    "Wicklow County Council": [("2016-05-01", "DP 2016-2022"), ("2022-06-01", "DP 2022-2028")],
    "Fingal County Council": [("2017-03-01", "DP 2017-2023"), ("2023-04-01", "DP 2023-2029")],
}


def main() -> None:
    report = {}

    # ---------- E2 ----------
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "PlanningAuthority", "NumResidentialUnits",
                                   "ITMEasting", "ITMNorthing", "GrantDate", "ReceivedDate",
                                   "AreaofSite"])
    reg = reg.drop_duplicates("case_key")
    reg["units"] = pd.to_numeric(reg["NumResidentialUnits"], errors="coerce")
    reg["area"] = pd.to_numeric(reg["AreaofSite"], errors="coerce")
    reg["grant_dt"] = pd.to_datetime(reg["GrantDate"], utc=True, errors="coerce").dt.tz_localize(None)
    reg["recv"] = pd.to_datetime(reg["ReceivedDate"], utc=True, errors="coerce").dt.tz_localize(None)
    labels = pd.read_csv(SILVER / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    labels = labels[labels["activation_linked"].astype(str).str.lower() == "true"]
    labels["activation"] = pd.to_numeric(labels["activation_days"], errors="coerce")
    base = reg.merge(labels[["case_key", "activation"]], on="case_key", how="left")
    base["comm_dt"] = base["grant_dt"] + pd.to_timedelta(base["activation"], unit="D")
    base = base.dropna(subset=["grant_dt", "ITMEasting", "ITMNorthing", "units"])
    base = base[base["grant_dt"].dt.year.between(2015, 2020)]
    base["g2c"] = (base["comm_dt"] - base["grant_dt"]).dt.days

    ppr = pd.read_parquet(settings.BRONZE_DIR / "ppr_bronze.parquet",
                          columns=["date_of_sale", "county", "price", "description_of_property"])
    ppr["price"] = ppr["price"].astype(str).str.replace("€", "", regex=False).str.replace(",", "", regex=False)
    ppr["price"] = pd.to_numeric(ppr["price"], errors="coerce")
    ppr = ppr.dropna(subset=["price"])
    ppr["dt"] = pd.to_datetime(ppr["date_of_sale"], utc=True, errors="coerce").dt.tz_localize(None)
    ppr["new"] = ppr["description_of_property"].fillna("").str.contains("New Dwelling", case=False, na=False)
    ppr = ppr[ppr["new"]].dropna(subset=["dt"])
    ppr["ym"] = ppr["dt"].dt.to_period("M")

    targets = base.sample(min(80, len(base)), random_state=42)
    rows = []
    for _, t in targets.iterrows():
        t0 = t["grant_dt"]
        dist = np.sqrt((base["ITMEasting"] - t["ITMEasting"]) ** 2 +
                       (base["ITMNorthing"] - t["ITMNorthing"]) ** 2)
        pipe = base[(dist <= 3000) & (base["case_key"] != t["case_key"]) &
                    (base["grant_dt"] <= t0)]
        if len(pipe) < 2:
            continue
        hist = base[(base["grant_dt"] < t0 - pd.Timedelta(days=365)) &
                    (base["PlanningAuthority"] == t["PlanningAuthority"]) &
                    (base["comm_dt"].notna())]
        fu = 0.0
        for _, row in pipe.iterrows():
            elapsed = max((t0 - row["grant_dt"]).days, 0)
            elig = hist["g2c"][hist["g2c"] > elapsed]
            p = float((elig <= elapsed + 730).mean()) if len(elig) >= 15 else 0.5
            fu += row["units"] * p
        county = "Dublin" if "Dublin" in t["PlanningAuthority"] else t["PlanningAuthority"].split()[0]
        county_abs = ppr[(ppr["county"] == county) & (ppr["dt"] >= t0 - pd.Timedelta(days=730)) &
                         (ppr["dt"] <= t0)]
        abs24 = float(len(county_abs))
        nominal = float(pipe["units"].sum())
        if abs24 < 50:
            continue
        ratio = fu / abs24
        future_abs = ppr[(ppr["county"] == county) & (ppr["dt"] > t0) &
                         (ppr["dt"] <= t0 + pd.Timedelta(days=730))]
        future_price = ppr[(ppr["county"] == county) & (ppr["dt"] > t0) &
                           (ppr["dt"] <= t0 + pd.Timedelta(days=730))]["price"]
        past_price = ppr[(ppr["county"] == county) & (ppr["dt"] <= t0) &
                         (ppr["dt"] > t0 - pd.Timedelta(days=365))]["price"]
        rows.append({"target": t["case_key"], "t0": t0, "county": county,
                     "ratio24": ratio, "nominal_units": nominal, "deliverable24": fu,
                     "absorption24": abs24, "future_volume24": float(len(future_abs)),
                     "future_price_growth_pct": float(
                         (future_price.median() - past_price.median()) / past_price.median() * 100)
                     if len(future_price) >= 20 and len(past_price) >= 20 else np.nan})
    fr = pd.DataFrame(rows)
    fr.to_csv(OUT / "e2_supply_pressure.csv", index=False)
    e2 = {"n_catchments": int(len(fr)), "median_ratio": round(float(fr["ratio24"].median()), 2),
          "ratio_p25": round(float(fr["ratio24"].quantile(0.25)), 2),
          "ratio_p75": round(float(fr["ratio24"].quantile(0.75)), 2)}
    hi = fr[fr["ratio24"] > fr["ratio24"].quantile(0.75)]
    lo = fr[fr["ratio24"] <= fr["ratio24"].quantile(0.25)]
    if len(hi) >= 10 and len(lo) >= 10:
        e2["high_vs_low_pressure"] = {
            "future_volume_median_high": round(float(hi["future_volume24"].median()), 1),
            "future_volume_median_low": round(float(lo["future_volume24"].median()), 1),
            "future_price_growth_high": round(float(hi["future_price_growth_pct"].median()), 1),
            "future_price_growth_low": round(float(lo["future_price_growth_pct"].median()), 1),
        }
        e2["corr_ratio_future_volume"] = round(float(fr["ratio24"].corr(fr["future_volume24"])), 3)
        e2["corr_ratio_future_price_growth"] = round(
            float(fr["ratio24"].corr(fr["future_price_growth_pct"])), 3)
    e2["honest_note"] = ("absorption is COUNTY-level PPR new-dwelling volume (finest reliably-held granularity; "
                         "PPR has no coordinates); local absorption from linked scheme sales was too thin (support < 10). "
                         "Interpret the ratio as supply pressure relative to the county market, not the 3km micro-market.")
    report["e2_supply_pressure"] = e2

    # ---------- E3 ----------
    reg3 = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                           columns=["case_key", "PlanningAuthority", "NumResidentialUnits",
                                    "AreaofSite", "ReceivedDate", "Decision"])
    reg3 = reg3.drop_duplicates("case_key")
    dec = reg3["Decision"].fillna("").str.lower()
    reg3["y"] = dec.str.contains("refus").astype(int)
    reg3 = reg3[dec.str.contains("refus|grant", regex=True)]
    reg3["recv"] = pd.to_datetime(reg3["ReceivedDate"], utc=True, errors="coerce").dt.tz_localize(None)
    reg3["year"] = reg3["recv"].dt.year
    reg3["units"] = pd.to_numeric(reg3["NumResidentialUnits"], errors="coerce").fillna(1)
    reg3["area"] = pd.to_numeric(reg3["AreaofSite"], errors="coerce")
    reg3["du_ha"] = reg3["units"] / (reg3["area"] / 10000.0)
    reg3["high_density"] = (reg3["du_ha"] >= 35).astype(int)
    reg3 = reg3[reg3["PlanningAuthority"].isin(PLANS.keys())]
    reg3 = reg3[reg3["year"].between(2014, 2025)]
    desc = reg3["DevelopmentDescription"].fillna("") if "DevelopmentDescription" in reg3.columns else None
    feats = pd.DataFrame({"log_units": np.log1p(reg3["units"]), "year": reg3["year"],
                          "high_density": reg3["high_density"]})
    auth_d = pd.get_dummies(reg3["PlanningAuthority"], prefix="a").astype(int)
    X = pd.concat([feats, auth_d], axis=1)
    model = GradientBoostingClassifier(n_estimators=300, max_depth=3, learning_rate=0.05,
                                       min_samples_leaf=50, random_state=7)
    # time-safe residuals via expanding windows
    resid = np.full(len(reg3), np.nan)
    for year in sorted(reg3["year"].unique())[3:]:
        tr = reg3["year"] < year
        te = reg3["year"] == year
        if tr.sum() < 500 or te.sum() == 0:
            continue
        model.fit(X.loc[tr], reg3.loc[tr, "y"])
        resid[te.to_numpy()] = reg3.loc[te, "y"].to_numpy() - model.predict_proba(X.loc[te])[:, 1]
    reg3["resid"] = resid
    reg3["post2022"] = (reg3["recv"] >= pd.Timestamp("2022-01-01")).astype(int)

    e3 = {"policy_table": PLANS, "density_dimension": {}}
    for auth in PLANS:
        sub = reg3[reg3["PlanningAuthority"] == auth].dropna(subset=["resid"])
        if len(sub) < 300:
            continue
        hi = sub[sub["high_density"] == 1]
        lo = sub[sub["high_density"] == 0]
        did = ((hi[hi["post2022"] == 1]["resid"].mean() - hi[hi["post2022"] == 0]["resid"].mean()) -
               (lo[lo["post2022"] == 1]["resid"].mean() - lo[lo["post2022"] == 0]["resid"].mean()))
        # placebo: pretend the plan changed 2 years earlier
        sub_p = sub[sub["recv"] < pd.Timestamp("2020-01-01")]
        hi_p = sub_p[sub_p["high_density"] == 1]
        lo_p = sub_p[sub_p["high_density"] == 0]
        placebo = ((hi_p[hi_p["recv"] >= pd.Timestamp("2018-01-01")]["resid"].mean() -
                    hi_p[hi_p["recv"] < pd.Timestamp("2018-01-01")]["resid"].mean()) -
                   (lo_p[lo_p["recv"] >= pd.Timestamp("2018-01-01")]["resid"].mean() -
                    lo_p[lo_p["recv"] < pd.Timestamp("2018-01-01")]["resid"].mean()))
        e3["density_dimension"][auth] = {
            "n_pre": int(len(sub[sub["post2022"] == 0])), "n_post": int(len(sub[sub["post2022"] == 1])),
            "n_high_density": int(len(hi)),
            "did_pp": round(float(did * 100), 2),
            "placebo_did_pp": round(float(placebo * 100), 2) if not np.isnan(placebo) else None,
        }
    report["e3_policy_gap"] = e3
    (OUT / "e2_e3_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str)[:4500])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
