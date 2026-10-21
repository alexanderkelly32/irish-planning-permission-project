"""Sprint 3 substrate: site clusters + fast time-safe observable-difficulty
baseline. (The frozen model is substituted for scale by a transparent
time-safe GBM; noted in the registry as a deviation.)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.ensemble import GradientBoostingClassifier

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "sprint3"
OUT.mkdir(parents=True, exist_ok=True)

FAMILIES = ["access", "road", "parking", "storey", "drainage", "water", "flood",
            "ecolog", "archaeolog", "design", "phase", "demolition", "protected",
            "change of use", "apartment", "amenity", "open space"]


def main() -> None:
    import re
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "PlanningAuthority", "DevelopmentDescription",
                                   "NumResidentialUnits", "AreaofSite", "ITMEasting",
                                   "ITMNorthing", "ReceivedDate", "Decision"])
    reg = reg.drop_duplicates("case_key")
    reg = reg.dropna(subset=["ITMEasting", "ITMNorthing", "ReceivedDate"])
    reg["units"] = pd.to_numeric(reg["NumResidentialUnits"], errors="coerce").fillna(1)
    reg["area"] = pd.to_numeric(reg["AreaofSite"], errors="coerce")
    reg["recv"] = pd.to_datetime(reg["ReceivedDate"], utc=True, errors="coerce").dt.tz_localize(None)
    reg["y"] = reg["Decision"].fillna("").str.lower().str.contains("refus").astype(int)
    reg = reg[reg["Decision"].fillna("").str.lower().str.contains("refus|grant", regex=True)]
    reg = reg.dropna(subset=["recv"])
    reg = reg.sort_values("recv")
    desc = reg["DevelopmentDescription"].fillna("").str.lower()
    for fam in FAMILIES:
        reg[f"f_{fam.replace(' ', '_')}"] = desc.str.contains(fam, regex=False).astype(int)
    reg["desc_len"] = desc.str.len()
    reg["log_units"] = np.log1p(reg["units"])
    reg["year"] = reg["recv"].dt.year

    rows = []
    for authority, g in reg.groupby("PlanningAuthority"):
        if len(g) < 2:
            continue
        coords = g[["ITMEasting", "ITMNorthing"]].to_numpy()
        tree = cKDTree(coords)
        parent = list(range(len(g)))
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
        for a, b in tree.query_pairs(r=150.0, output_type="ndarray"):
            union(int(a), int(b))
        g = g.copy().reset_index(drop=True)
        g["site_id"] = authority + "|" + pd.Series([find(i) for i in range(len(g))]).astype(str)
        rows.append(g)
    frame = pd.concat(rows, ignore_index=True)
    site_counts = frame.groupby("site_id").size()
    frame = frame[frame["site_id"].map(site_counts).between(2, 10)]
    frame.to_csv(OUT / "site_apps.csv", index=False)

    feats = ["log_units", "desc_len", "year"] + [f"f_{f.replace(' ', '_')}" for f in FAMILIES]
    auth_d = pd.get_dummies(frame["PlanningAuthority"], prefix="a").astype(int)
    preds = np.full(len(frame), np.nan)
    for year in sorted(frame["year"].unique())[1:]:
        tr = (frame["year"] < year)
        te = (frame["year"] == year)
        if tr.sum() < 300 or te.sum() == 0:
            continue
        model = GradientBoostingClassifier(n_estimators=200, max_depth=3,
                                           learning_rate=0.05, min_samples_leaf=25,
                                           random_state=7)
        X_tr = pd.concat([frame.loc[tr, feats], auth_d.loc[tr]], axis=1)
        X_te = pd.concat([frame.loc[te, feats], auth_d.loc[te]], axis=1)
        model.fit(X_tr, frame.loc[tr, "y"])
        preds[te.to_numpy()] = model.predict_proba(X_te)[:, 1]
    frame["expected_p"] = preds
    frame["residual"] = frame["y"] - frame["expected_p"]
    frame.to_csv(OUT / "site_apps_scored.csv", index=False)
    print("sites:", frame["site_id"].nunique(), "apps:", len(frame),
          "coverage:", round(float((~np.isnan(preds)).mean()), 3), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
