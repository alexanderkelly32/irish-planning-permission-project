"""Zero-day USP E1: likely FI topics.

Labels: FI-request letter texts already pulled from iDocs (readiness dirs),
classified by a keyword taxonomy. Zero-day features only. Temporal holdout
among FI'd apps. Metrics: per-topic prevalence/AUC/AP, top-1/top-3 recall,
calibration; baselines: prevalence, authority x type, description-keyword.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "usp" / "e1_fi_topics"
OUT.mkdir(parents=True, exist_ok=True)

TOPICS = {
    "access_roads": r"access|road|traffic|junction|turning|parking|visibility|sightline",
    "drainage_water": r"drainage|waste ?water|water supply|sewer|attenuation|suds|surface water|foul",
    "design_density": r"design|layout|density|height|storey|overlooking|scale|massing|setback",
    "ecology": r"ecolog|habitat|bat|bird|tree|natura|biodiversity|appropriate assessment|screening",
    "flood": r"flood",
    "landscaping_open_space": r"landscap|open space|amenity|play|public realm",
    "archaeology_heritage": r"archaeolog|heritage|conservation|protected structure|monument",
    "housing_mix_partv": r"part ?v|social housing|affordable|housing mix|tenure|mix of",
    "noise_environmental": r"noise|vibration|air quality|contamination|environmental impact",
    "documentation_clarification": r"clarif|further detail|additional information|documentation|submit|revised drawing|amended plan",
    "other": r".*",
}


def classify_topics(text: str) -> list[str]:
    hits = []
    for name, pat in TOPICS.items():
        if name == "other":
            continue
        if re.search(pat, text or "", re.I):
            hits.append(name)
    return hits or ["other"]


def main() -> None:
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "PlanningAuthority", "DevelopmentDescription",
                                   "NumResidentialUnits", "ReceivedDate", "FIRequestDate"])
    reg = reg.drop_duplicates("case_key")
    reg["units"] = pd.to_numeric(reg["NumResidentialUnits"], errors="coerce").fillna(1)
    reg["year"] = pd.to_datetime(reg["ReceivedDate"], utc=True, errors="coerce").dt.year

    rows = []
    for scheme_dir in sorted((SILVER / "idocs" / "docs").glob("*/readiness")):
        ck = scheme_dir.parent.name
        for dj in scheme_dir.glob("*.json"):
            try:
                d = json.loads(dj.read_text(encoding="utf-8"))
            except Exception:
                continue
            if d.get("status") != "ok" or not d.get("text"):
                continue
            dtype = f"{d.get('type', '')} {d.get('comment', '')}"
            if re.search(r"F\.?I\.? ?(Request|Request Letter)|Further Information Request", dtype, re.I):
                topics = classify_topics(d["text"])
                rows.append({"ck": ck, "docid": d.get("docid"), "topics": "|".join(topics),
                             "n_topics": len(topics), "text_head": d["text"][:400]})
    labels = pd.DataFrame(rows)
    labels.to_csv(OUT / "fi_topic_labels.csv", index=False)
    print("FI request docs with topics:", len(labels), "| unique schemes:", labels["ck"].nunique(), flush=True)

    # map ck -> case_key
    clean = pd.read_csv(SILVER / "dq" / "labels_clean.csv", dtype=str)
    ck_map = {}
    for k in clean["case_key"]:
        ck_map[k[:80]] = k
        ck_map[k.replace(" ", "_")[:80]] = k
    labels["case_key"] = labels["ck"].map(lambda c: ck_map.get(c) or ck_map.get(c.replace("_", " ")))
    labels = labels.dropna(subset=["case_key"])

    # app-level multi-label: one row per scheme, topics union across its FI docs
    app = labels.groupby("case_key")["topics"].apply(lambda s: sorted(set("|".join(s).split("|"))))
    app = app.reset_index().rename(columns={"topics": "topic_list"})
    base = app.merge(reg, on="case_key", how="left")
    base["fi"] = pd.notna(base["FIRequestDate"]).astype(int)
    base = base[base["fi"] == 1]
    desc = base["DevelopmentDescription"].fillna("").str.lower()
    for name in TOPICS:
        base[f"kw_{name}"] = desc.str.contains(TOPICS[name], regex=True).astype(int)
    base["desc_len"] = desc.str.len()
    base["log_units"] = np.log1p(base["units"])
    for name in TOPICS:
        base[f"y_{name}"] = base["topic_list"].apply(lambda ts, n=name: int(n in ts))
    base.to_csv(OUT / "fi_topic_app_level.csv", index=False)
    print("FI'd schemes with topic labels:", len(base), flush=True)

    feats = ["log_units", "desc_len", "year"] + [f"kw_{n}" for n in TOPICS]
    auth_d = pd.get_dummies(base["PlanningAuthority"], prefix="a").astype(int)
    train = base[base["year"] < 2020]
    test = base[base["year"] >= 2020]

    report = {"n_fi_labelled": int(len(base)), "n_train": int(len(train)), "n_test": int(len(test)),
              "prevalence": {}, "topics": {}}
    rng = np.random.default_rng(7)
    for name in TOPICS:
        if name == "other":
            continue
        report["prevalence"][name] = round(float(base[f"y_{name}"].mean()), 3)
        tr, te = train, test
        if tr[f"y_{name}"].sum() < 20 or te[f"y_{name}"].nunique() < 2:
            report["topics"][name] = {"status": "insufficient_support",
                                      "n_pos_train": int(tr[f"y_{name}"].sum())}
            continue
        X_tr = pd.concat([tr[feats], auth_d.loc[tr.index]], axis=1)
        X_te = pd.concat([te[feats], auth_d.loc[te.index]], axis=1)
        m = GradientBoostingClassifier(n_estimators=200, max_depth=2, learning_rate=0.05,
                                       min_samples_leaf=8, random_state=7)
        m.fit(X_tr, tr[f"y_{name}"])
        p = m.predict_proba(X_te)[:, 1]
        entry = {"n_pos_test": int(te[f"y_{name}"].sum()),
                 "auc": round(float(roc_auc_score(te[f"y_{name}"], p)), 3),
                 "ap": round(float(average_precision_score(te[f"y_{name}"], p)), 3)}
        kw = LogisticRegression(max_iter=3000, C=1.0)
        kw.fit(tr[[f"kw_{name}"]], tr[f"y_{name}"])
        p_kw = kw.predict_proba(te[[f"kw_{name}"]])[:, 1]
        entry["auc_keyword_baseline"] = round(float(roc_auc_score(te[f"y_{name}"], p_kw)), 3)
        entry["auc_prevalence_baseline"] = 0.5
        report["topics"][name] = entry

    # top-k recall (fitted model ranking vs actual topics)
    probs = {}
    for name in TOPICS:
        if name == "other":
            continue
        tr, te = train, test
        if tr[f"y_{name}"].sum() < 20:
            probs[name] = np.full(len(te), float(tr[f"y_{name}"].mean()))
            continue
        X_tr = pd.concat([tr[feats], auth_d.loc[tr.index]], axis=1)
        X_te = pd.concat([te[feats], auth_d.loc[te.index]], axis=1)
        m = GradientBoostingClassifier(n_estimators=200, max_depth=2, learning_rate=0.05,
                                       min_samples_leaf=8, random_state=7)
        m.fit(X_tr, tr[f"y_{name}"])
        probs[name] = m.predict_proba(X_te)[:, 1]
    p_df = pd.DataFrame(probs, index=test.index)
    top1 = top2 = top3 = 0
    for _, r in test.iterrows():
        actual = set(r["topic_list"])
        ranked = p_df.loc[r.name].sort_values(ascending=False).index.tolist()
        top1 += int(ranked[0] in actual)
        top2 += int(any(t in actual for t in ranked[:2]))
        top3 += int(any(t in actual for t in ranked[:3]))
    report["top_recall"] = {"top1": round(top1 / max(len(test), 1), 3),
                            "top2": round(top2 / max(len(test), 1), 3),
                            "top3": round(top3 / max(len(test), 1), 3)}
    # prevalence baseline: always predict the top-3 overall topics
    top3_prev = pd.Series({n: base[f"y_{n}"].mean() for n in TOPICS if n != "other"}).sort_values(
        ascending=False).head(3).index.tolist()
    base_top3 = sum(int(any(t in set(r["topic_list"]) for t in top3_prev)) for _, r in test.iterrows())
    report["top_recall"]["baseline_top3_overall_prevalence"] = round(base_top3 / max(len(test), 1), 3)

    # SD17A/0397 example (FI'd, granted 2018)
    ex = base[base["case_key"] == "South Dublin County Council__SD17A/0397"]
    if len(ex):
        actual = ex["topic_list"].iloc[0]
        report["sd17a_example"] = {"actual_topics": actual,
                                   "note": "2018 scheme predates the 2020+ prediction window; topic model not applicable - showing actual FI topics from the held request letters"}
    (OUT / "e1_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str)[:4500])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
