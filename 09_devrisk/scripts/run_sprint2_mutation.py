"""Sprint 2: Refusal->Grant Mutation Engine + Minimum-Change Rescue Plan.

Longitudinal within-site problem. Builds refused->later-application pairs
from same-site lineage (ITM KD-tree clustering per authority), extracts
feature/text deltas, tests which deltas associate with the later
application being granted (vs refused), per refusal theme. Retrospective
rescue test on temporal holdout. Correlational language only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "sprint2"
OUT.mkdir(parents=True, exist_ok=True)

FAMILIES = {
    "access_roads": r"access|road|junction|roundabout|traffic|footpath|cycle",
    "parking": r"parking|car park",
    "height_storeys": r"storey|storeys|height|floor building",
    "open_space_amenity": r"open space|amenity|landscap|green|play area|park\b",
    "drainage_uisce": r"drainage|uisce|water|sewer|attenuation|suds",
    "flood": r"flood",
    "ecology": r"ecolog|habitat|bat |tree|natura|biodiversity",
    "archaeology": r"archaeolog|monument",
    "design_material": r"design|material|finish|render|brick|stone|cladding",
    "phasing": r"phas",
    "density_scale": r"density|scale|reduc",
    "social_housing": r"part v|social housing|affordable",
}
THEMES = {
    "density_scale": r"density|scale|overdevelop|height|storey|units|number of",
    "design": r"design|visual|amenity|character|appearance|material|finish",
    "access_roads": r"access|road|traffic|junction|parking|turning",
    "water_flood": r"flood|drainage|water|sewer|attenuation",
    "ecology_heritage": r"ecolog|habitat|tree|natura|archaeolog|heritage|protected",
    "other": r".*",
}


def family_delta(d1: str, d2: str) -> dict:
    out = {}
    for name, pat in FAMILIES.items():
        a = bool(__import__("re").search(pat, d1 or "", __import__("re").I))
        b = bool(__import__("re").search(pat, d2 or "", __import__("re").I))
        out[f"fam_{name}_added"] = int(b and not a)
        out[f"fam_{name}_removed"] = int(a and not b)
    return out


def theme_of(desc: str) -> str:
    import re
    for name, pat in THEMES.items():
        if name == "other":
            continue
        if re.search(pat, desc or "", re.I):
            return name
    return "other"


def main() -> None:
    import re
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "PlanningAuthority", "DevelopmentDescription",
                                   "NumResidentialUnits", "AreaofSite", "ITMEasting",
                                   "ITMNorthing", "ReceivedDate", "Decision", "DecisionDate",
                                   "ApplicantForename", "ApplicantSurname", "ApplicationType"])
    reg = reg.drop_duplicates("case_key")
    reg = reg.dropna(subset=["ITMEasting", "ITMNorthing", "ReceivedDate"])
    reg["units"] = pd.to_numeric(reg["NumResidentialUnits"], errors="coerce")
    reg["recv"] = pd.to_datetime(reg["ReceivedDate"], utc=True, errors="coerce").dt.tz_localize(None)
    reg["dec_dt"] = pd.to_datetime(reg["DecisionDate"], utc=True, errors="coerce").dt.tz_localize(None)
    reg["decision"] = reg["Decision"].fillna("").str.lower()
    reg["applicant"] = (reg["ApplicantForename"].fillna("") + "|" + reg["ApplicantSurname"].fillna("")).str.lower()
    reg = reg[reg["decision"].str.contains("refus|grant", regex=True)]
    reg = reg.dropna(subset=["recv"])
    reg = reg.sort_values("recv")

    pairs = []
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
        pairs_idx = tree.query_pairs(r=150.0, output_type="ndarray")
        for a, b in pairs_idx:
            union(int(a), int(b))
        g = g.copy()
        g["site_id"] = [find(i) for i in range(len(g))]
        g["site_id"] = authority + "|" + g["site_id"].astype(str)
        for site_id, sg in g.groupby("site_id"):
            if len(sg) < 2 or len(sg) > 12:
                continue
            apps = sg.sort_values("recv")
            for i in range(len(apps) - 1):
                first = apps.iloc[i]
                if "refus" not in first["decision"]:
                    continue
                later = apps.iloc[i + 1]
                if "refus" in later["decision"] or "grant" in later["decision"]:
                    gap_ok = True
                    if pd.notna(first["dec_dt"]) and pd.notna(later["recv"]):
                        gap_ok = (later["recv"] - first["dec_dt"]).days >= 14
                    pairs.append({
                        "site_id": site_id, "case_key_1": first["case_key"],
                        "case_key_2": later["case_key"], "authority": authority,
                        "recv_1": first["recv"], "dec_1": first["dec_dt"], "recv_2": later["recv"],
                        "decision_2": "grant" if "grant" in later["decision"] else "refuse",
                        "units_1": first["units"], "units_2": later["units"],
                        "desc_1": first["DevelopmentDescription"], "desc_2": later["DevelopmentDescription"],
                        "applicant_1": first["applicant"], "applicant_2": later["applicant"],
                        "type_1": first["ApplicationType"], "type_2": later["ApplicationType"],
                        "gap_ok": gap_ok,
                    })
    frame = pd.DataFrame(pairs)
    frame = frame[frame["gap_ok"]]
    frame["tok1"] = frame["desc_1"].fillna("").str.lower().apply(lambda s: set(re.findall(r"[a-z0-9]{3,}", s)))
    frame["tok2"] = frame["desc_2"].fillna("").str.lower().apply(lambda s: set(re.findall(r"[a-z0-9]{3,}", s)))
    frame["jaccard"] = frame.apply(lambda r: len(r["tok1"] & r["tok2"]) / max(len(r["tok1"] | r["tok2"]), 1), axis=1)
    frame["desc_len_ratio"] = frame["desc_2"].fillna("").str.len() / frame["desc_1"].fillna("").str.len().clip(lower=1)
    frame["units_log_ratio"] = np.log1p(frame["units_2"].fillna(0)) - np.log1p(frame["units_1"].fillna(0))
    frame["units_reduced"] = ((frame["units_2"].fillna(0) < frame["units_1"].fillna(0) * 0.9)).astype(int)
    frame["units_increased"] = ((frame["units_2"].fillna(0) > frame["units_1"].fillna(0) * 1.1)).astype(int)
    frame["applicant_change"] = (frame["applicant_1"] != frame["applicant_2"]).astype(int)
    frame["type_change"] = (frame["type_1"] != frame["type_2"]).astype(int)
    for _, r in frame.iterrows():
        for k, v in family_delta(r["desc_1"], r["desc_2"]).items():
            frame.loc[_, k] = v
    frame["theme"] = frame["desc_1"].fillna("").apply(theme_of)
    frame["year_1"] = frame["recv_1"].dt.year
    frame.to_csv(OUT / "refusal_grant_pairs.csv", index=False)
    print("pairs:", len(frame), "| granted-later:", (frame["decision_2"] == "grant").mean().round(3), flush=True)

    feats = ["jaccard", "desc_len_ratio", "units_log_ratio", "units_reduced", "units_increased",
             "applicant_change", "type_change"] + \
            [f"fam_{n}_{dir_}" for n in FAMILIES for dir_ in ("added", "removed")]
    y = (frame["decision_2"] == "grant").astype(int)
    train = frame[frame["year_1"] < 2021]
    test = frame[frame["year_1"] >= 2021]
    auth_dummies = pd.get_dummies(frame["authority"], prefix="a").astype(int)
    report = {"n_pairs": int(len(frame)), "n_train": int(len(train)), "n_test": int(len(test)),
              "grant_rate": round(float(y.mean()), 3)}

    model = LogisticRegression(max_iter=3000, C=0.5)
    X_tr = pd.concat([train[feats].fillna(0.0), auth_dummies.loc[train.index]], axis=1)
    X_te = pd.concat([test[feats].fillna(0.0), auth_dummies.loc[test.index]], axis=1)
    model.fit(X_tr, train["decision_2"].map({"grant": 1, "refuse": 0}))
    try:
        auc_te = roc_auc_score(test["decision_2"].map({"grant": 1, "refuse": 0}),
                               model.predict_proba(X_te)[:, 1])
    except ValueError:
        auc_te = float("nan")
    report["auc_test_conversion_model"] = round(float(auc_te), 3)

    univ = {}
    for f in feats:
        g1 = frame[frame["decision_2"] == "grant"][f].mean()
        g0 = frame[frame["decision_2"] == "refuse"][f].mean()
        univ[f] = {"grant_mean": round(float(g1), 3), "refuse_mean": round(float(g0), 3),
                   "delta": round(float(g1 - g0), 3)}
    report["univariate_deltas"] = univ

    themes_out = {}
    for theme, sub in frame.groupby("theme"):
        if len(sub) < 15:
            continue
        entry = {"n": int(len(sub)), "grant_rate": round(float((sub["decision_2"] == "grant").mean()), 3)}
        for f in ["units_reduced", "applicant_change", "type_change", "fam_design_material_added",
                  "fam_density_scale_added", "fam_access_roads_added"]:
            g1 = sub[sub["decision_2"] == "grant"][f].mean()
            g0 = sub[sub["decision_2"] == "refuse"][f].mean()
            entry[f] = {"grant_mean": round(float(g1), 3), "refuse_mean": round(float(g0), 3)}
        themes_out[theme] = entry
    report["by_theme"] = themes_out

    (OUT / "sprint2_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str)[:6000])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
