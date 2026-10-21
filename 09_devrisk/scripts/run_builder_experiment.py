"""Builder identity resolution from held iDocs texts + capacity experiment.

Step 1: extract builder-name candidates from readiness correspondence
texts (pattern-based), report coverage + consistency proxy.
Step 2 (if coverage allows): time-safe builder histories (workload,
experience, prior delivery) -> completion-within-18/24/36m logistic,
controls for units/type/authority/year/developer, out-of-time split.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "usp" / "builder"
OUT.mkdir(parents=True, exist_ok=True)

NAME_RE = re.compile(
    r"\b((?:[A-Z][A-Za-z&'\-\. ]{2,40})\s+(?:Ltd|Limited|Contractors?|Builders?|Construction|Developments?|"
    r"Building Contractors?))\b")
STOP = {"the development", "building control", "planning authority", "county council",
        "city council", "this development", "building regulations"}


def main() -> None:
    schemes = {}
    for doc_dir in [SILVER / "idocs" / "docs"]:
        for scheme_dir in sorted(doc_dir.glob("*/readiness")):
            ck = scheme_dir.parent.name
            names = []
            for dj in scheme_dir.glob("*.json"):
                try:
                    d = json.loads(dj.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if d.get("status") != "ok" or not d.get("text"):
                    continue
                for m in NAME_RE.finditer(d["text"]):
                    name = " ".join(m.group(1).split())
                    if name.lower() not in STOP and len(name) > 6:
                        names.append(name)
            if names:
                schemes[ck] = names
    rows = []
    for ck, names in schemes.items():
        from collections import Counter
        cnt = Counter(names)
        top = cnt.most_common(1)[0]
        rows.append({"ck": ck, "n_mentions": len(names), "n_unique_names": len(cnt),
                     "top_name": top[0], "top_count": top[1],
                     "consistency": top[1] / max(len(names), 1)})
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT / "builder_resolution.csv", index=False)
    report = {"n_schemes_with_any_name": int(len(frame)),
              "n_schemes_with_consistent_name": int((frame["consistency"] >= 0.5).sum()),
              "median_consistency": round(float(frame["consistency"].median()), 3),
              "sample_names": frame.sort_values("top_count", ascending=False)["top_name"].head(15).tolist()}
    print("resolution:", json.dumps(report, indent=2), flush=True)

    # Step 2: experiment only if coverage allows
    if len(frame) < 40:
        report["experiment"] = {"verdict": "BLOCKED - builder resolution coverage insufficient",
                                "n_schemes_with_names": int(len(frame))}
        (OUT / "builder_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return

    ck_map = {}
    clean = pd.read_csv(SILVER / "dq" / "labels_clean.csv", dtype=str)
    for k in clean["case_key"]:
        ck_map[k[:80]] = k
        ck_map[k.replace(" ", "_")[:80]] = k
    frame["case_key"] = frame["ck"].map(lambda c: ck_map.get(c) or ck_map.get(c.replace("_", " ")))
    frame = frame.dropna(subset=["case_key"])
    frame = frame[frame["consistency"] >= 0.5]
    names = frame.drop_duplicates("case_key").set_index("case_key")["top_name"]

    labels = pd.read_csv(SILVER / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    labels = labels[labels["activation_linked"].astype(str).str.lower() == "true"]
    labels["activation"] = pd.to_numeric(labels["activation_days"], errors="coerce")
    labels["completion"] = pd.to_numeric(labels["completion_days"], errors="coerce")
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "PlanningAuthority", "NumResidentialUnits",
                                   "DevelopmentDescription", "GrantDate"])
    reg = reg.drop_duplicates("case_key")
    reg["grant_dt"] = pd.to_datetime(reg["GrantDate"], utc=True, errors="coerce").dt.tz_localize(None)
    base = labels.merge(reg, on="case_key", how="inner").dropna(subset=["activation", "completion"])
    base["comm_dt"] = base["grant_dt"] + pd.to_timedelta(base["activation"], unit="D")
    base["builder"] = base["case_key"].map(names)
    base = base.dropna(subset=["builder"])
    base = base.sort_values("comm_dt")
    base["units"] = pd.to_numeric(base["NumResidentialUnits"], errors="coerce").fillna(1)
    base["type_apartment"] = base["DevelopmentDescription"].fillna("").str.lower().str.contains(
        "apartment|duplex", regex=True).astype(int)
    base["comm_year"] = base["comm_dt"].dt.year
    dev = pd.read_csv(SILVER / "developer_groups.csv", dtype=str).dropna(subset=["group_id"])
    dev_map = dev.drop_duplicates("case_key").set_index("case_key")["group_id"]
    base["group_id"] = base["case_key"].map(dev_map)

    hist = []
    for _, r in base.iterrows():
        prior = base[base["comm_dt"] < r["comm_dt"]]
        bp = prior[prior["builder"] == r["builder"]] if len(prior) else prior
        entry = {"case_key": r["case_key"], "comm_dt": r["comm_dt"],
                 "builder_prior_schemes": int(len(bp)),
                 "builder_prior_units": float(bp["units"].sum()),
                 "builder_prior_med_completion": float(bp["completion"].median()) if len(bp) else np.nan,
                 "builder_prior_on_time_rate": float((bp["completion"] <= 730).mean()) if len(bp) else np.nan,
                 "builder_concurrent_units": float(prior[prior["builder"] == r["builder"]]["units"].sum()),
                 "units": r["units"], "type_apartment": r["type_apartment"],
                 "authority": r["PlanningAuthority"], "comm_year": r["comm_year"],
                 "group_id": r["group_id"], "completion": r["completion"]}
        hist.append(entry)
    df = pd.DataFrame(hist)
    df["y18"] = (df["completion"] <= 548).astype(int)
    df["y24"] = (df["completion"] <= 730).astype(int)
    df["y36"] = (df["completion"] <= 1095).astype(int)
    auth_d = pd.get_dummies(df["authority"], prefix="a").astype(int)
    dev_d = pd.get_dummies(df["group_id"], prefix="d").astype(int)
    ctrl = ["units", "type_apartment", "comm_year"]
    bfeats = ["builder_prior_schemes", "builder_prior_units", "builder_prior_med_completion",
              "builder_prior_on_time_rate", "builder_concurrent_units"]
    tr = df[df["comm_year"] < 2022]
    te = df[df["comm_year"] >= 2022]
    out = {"n_schemes_with_builder": int(len(df)), "n_builders": int(df["builder"].nunique() if "builder" in df.columns else 0),
           "n_train": int(len(tr)), "n_test": int(len(te))}
    for target in ("y18", "y24", "y36"):
        if te[target].nunique() < 2:
            continue
        Xtr_c = pd.concat([tr[ctrl], auth_d.loc[tr.index], dev_d.loc[tr.index].fillna(0)], axis=1)
        Xte_c = pd.concat([te[ctrl], auth_d.loc[te.index], dev_d.loc[te.index].fillna(0)], axis=1)
        m_c = GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.05,
                                         min_samples_leaf=10, random_state=7)
        m_c.fit(Xtr_c, tr[target])
        auc_c = roc_auc_score(te[target], m_c.predict_proba(Xte_c)[:, 1])
        Xtr_b = pd.concat([Xtr_c, tr[bfeats].fillna(0)], axis=1)
        Xte_b = pd.concat([Xte_c, te[bfeats].fillna(0)], axis=1)
        m_b = GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.05,
                                         min_samples_leaf=10, random_state=7)
        m_b.fit(Xtr_b, tr[target])
        auc_b = roc_auc_score(te[target], m_b.predict_proba(Xte_b)[:, 1])
        out[target] = {"auc_controls": round(float(auc_c), 3),
                       "auc_with_builder": round(float(auc_b), 3),
                       "lift": round(float(auc_b - auc_c), 3),
                       "n_test": int(len(te))}
    out["verdict_note"] = "builder resolution via correspondence-name extraction (consistency >= 0.5) - coverage limited to iDocs-pulled schemes"
    report["experiment"] = out
    (OUT / "builder_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
