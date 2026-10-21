"""Zero-day stats part 1: reference-class nearest-neighbor rates +
divergence-flag validation + two-dimensional calibration bands.

All built from held data at submission time; no new models.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "report" / "zero_day"
OUT.mkdir(parents=True, exist_ok=True)

FAMILIES = ["access", "road", "parking", "storey", "drainage", "water", "flood",
            "ecolog", "archaeolog", "design", "phase", "demolition", "protected",
            "change of use", "apartment", "amenity"]


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * np.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return max(centre - margin, 0.0), min(centre + margin, 1.0)


def main() -> None:
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "PlanningAuthority", "DevelopmentDescription",
                                   "NumResidentialUnits", "ITMEasting", "ITMNorthing",
                                   "ReceivedDate", "Decision", "DecisionDate", "FIRequestDate"])
    reg = reg.drop_duplicates("case_key")
    reg["recv"] = pd.to_datetime(reg["ReceivedDate"], utc=True, errors="coerce").dt.tz_localize(None)
    dec = reg["Decision"].fillna("").str.lower()
    reg["y"] = dec.str.contains("refus").astype(int)
    reg = reg[dec.str.contains("refus|grant", regex=True)].dropna(subset=["recv"])
    reg["fi"] = pd.notna(reg["FIRequestDate"]).astype(int)
    reg["units"] = pd.to_numeric(reg["NumResidentialUnits"], errors="coerce").fillna(1)
    reg["year"] = reg["recv"].dt.year
    desc = reg["DevelopmentDescription"].fillna("").str.lower()
    for fam in FAMILIES:
        reg[f"f_{fam}"] = desc.str.contains(fam, regex=False).astype(int)
    reg["desc_len"] = desc.str.len()
    reg["log_units"] = np.log1p(reg["units"])
    reg = reg[reg["year"] >= 2014].reset_index(drop=True)

    feats = ["log_units", "desc_len", "year"] + [f"f_{f}" for f in FAMILIES]
    auth_d = pd.get_dummies(reg["PlanningAuthority"], prefix="a").astype(int)
    train = reg[reg["year"] < 2022]
    test = reg[reg["year"] >= 2022]
    X_tr = pd.concat([train[feats], auth_d.loc[train.index]], axis=1)
    X_te = pd.concat([test[feats], auth_d.loc[test.index]], axis=1)
    model = GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.05,
                                       min_samples_leaf=30, random_state=7)
    model.fit(X_tr, train["y"])
    test = test.copy()
    test["p_ref"] = model.predict_proba(X_te)[:, 1]

    # reference-class KNN: same-authority prior apps, nearest in
    # (log_units, apartment-family) space, K=15
    nn_rate, nn_n, nn_fi = [], [], []
    prior_idx = {}
    for i, r in test.iterrows():
        hist = train[(train["PlanningAuthority"] == r["PlanningAuthority"]) &
                     (train["recv"] < r["recv"])]
        if len(hist) < 15:
            hist = train[train["recv"] < r["recv"]]
        if len(hist) < 15:
            nn_rate.append(np.nan)
            nn_n.append(0)
            nn_fi.append(np.nan)
            continue
        d = np.sqrt((hist["log_units"] - r["log_units"]) ** 2 * 2.0 +
                    (hist["f_apartment"] - r["f_apartment"]) ** 2 * 4.0 +
                    (hist["units"] - r["units"]) ** 2 / 400.0)
        k = min(15, len(d))
        idx = np.argsort(d)[:k]
        nn_rate.append(float(hist["y"].iloc[idx].mean()))
        nn_n.append(k)
        nn_fi.append(float(hist["fi"].iloc[idx].mean()))
    test["nn_refusal_rate"] = nn_rate
    test["nn_n"] = nn_n
    test["nn_fi_rate"] = nn_fi
    test["resid"] = np.abs(test["y"] - test["p_ref"])
    test["divergence"] = (test["p_ref"] - test["nn_refusal_rate"]).abs()
    test.to_csv(OUT / "reference_class_test.csv", index=False)

    sub = test.dropna(subset=["nn_refusal_rate"])
    out = {"n_test": int(len(test)), "n_with_neighbours": int(len(sub)),
           "median_nn_rate": round(float(sub["nn_refusal_rate"].median()), 3),
           "median_model_rate": round(float(sub["p_ref"].median()), 3),
           "corr_model_vs_nn": round(float(sub["p_ref"].corr(sub["nn_refusal_rate"])), 3)}
    # divergence-flag validation: does divergence predict model error?
    sub["div_flag"] = sub["divergence"] > 0.15
    out["divergence_flag"] = {
        "n_flagged": int(sub["div_flag"].sum()),
        "mean_abs_residual_flagged": round(float(sub[sub["div_flag"]]["resid"].mean()), 3),
        "mean_abs_residual_unflagged": round(float(sub[~sub["div_flag"]]["resid"].mean()), 3),
        "refusal_auc_flag_subset_vs_full": None,
    }
    flag = sub[sub["div_flag"]]
    if len(flag) >= 300:
        out["divergence_flag"]["auc_model_on_flagged"] = round(
            float(roc_auc_score(flag["y"], flag["p_ref"])), 3)
        out["divergence_flag"]["auc_model_on_unflagged"] = round(
            float(roc_auc_score(sub[~sub["div_flag"]]["y"], sub[~sub["div_flag"]]["p_ref"])), 3)
        out["divergence_flag"]["auc_nn_on_flagged"] = round(
            float(roc_auc_score(flag["y"], flag["nn_refusal_rate"])), 3)

    # 2D calibration: predicted-p decile x authority-group x type, n>=15 cells
    sub["p_decile"] = pd.qcut(sub["p_ref"], 8, labels=False, duplicates="drop")
    sub["type"] = np.where(sub["f_apartment"] == 1, "apartment", "house")
    sub["auth_group"] = sub["PlanningAuthority"].map(
        lambda a: "Dublin" if "Dublin" in a or "Dun Laoghaire" in a or "Fingal" in a or "South Dublin" in a
        else ("Cork" if "Cork" in a else ("large" if a in
              ("Kildare County Council", "Meath County Council", "Wicklow County Council",
               "Galway City Council", "Galway County Council", "Limerick County Council",
               "Waterford City and County Council") else "other")))
    cells = []
    for (dec, ag, tp), g in sub.groupby(["p_decile", "auth_group", "type"], observed=True):
        if len(g) < 15:
            continue
        k, n = int(g["y"].sum()), int(len(g))
        lo, hi = wilson(k, n)
        global_rate = sub[sub["p_decile"] == dec]["y"].mean()
        cells.append({"p_decile": int(dec), "auth_group": ag, "type": tp,
                      "n": n, "cell_rate": round(k / n, 4), "ci_low": round(lo, 4),
                      "ci_high": round(hi, 4),
                      "delta_vs_decile_pp": round((k / n - global_rate) * 100, 2)})
    cells_df = pd.DataFrame(cells)
    cells_df.to_csv(OUT / "calibration_2d_cells.csv", index=False)
    out["calibration_2d"] = {"n_cells": int(len(cells_df)),
                             "n_cells_large": int((cells_df["n"] >= 100).sum()),
                             "max_cell_delta_pp": round(float(cells_df["delta_vs_decile_pp"].abs().max()), 2) if len(cells_df) else None,
                             "sd_cell_delta_pp": round(float(cells_df["delta_vs_decile_pp"].std()), 2) if len(cells_df) else None,
                             "top_delta_cells": cells_df.reindex(cells_df["delta_vs_decile_pp"].abs().sort_values(ascending=False).index).head(5).to_dict(orient="records") if len(cells_df) else []}
    (OUT / "zero_day_part1_report.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str)[:4000])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
