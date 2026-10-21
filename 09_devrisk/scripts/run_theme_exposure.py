"""Theme-exposure model v6: multi-label refusal-theme exposure at submission time.

Framing: CONDITIONAL on refusal, which themes is this application exposed to.
This is not a refusal predictor and not a single-label classifier.

Label sources: retagged master (canonical) + llm_new extractions (display merge).
Features: submission-time only (description text, units, site area, authority,
year). Themes are labels only.

Models compared (time-safe train<2022 / test>=2022, refused GE10 with labels):
  base  - marginal theme prevalence
  ref   - authority x size reference-class theme rates (smoothed)
  lex   - lexicon-hit logistic (lexicons fit on train text only)
  tfidf - full-text TF-IDF L1 logistic (fitted benchmark)
  prec  - precedent vote: theme share among top-20 TF-IDF-matched refused cases
  ens   - simple average of ref + lex + prec (calibrated)

Outputs: 09_devrisk/data/silver/theme_exposure/
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.special import xlogy
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "09_devrisk" / "data" / "silver" / "theme_exposure"
OUT.mkdir(parents=True, exist_ok=True)
CUTOFF = pd.Timestamp("2022-01-01", tz="UTC")

sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from build_8020_regime_experiment import build_data  # noqa: E402

CANONICAL = ROOT / "03_refusal" / "current" / "theme_retag_2026-09-10" / "refusal_reasons_cases_master_retagged.csv"
LLM_NEW = ROOT / "03_refusal" / "current" / "refusal_reasons_cases_llm_new.csv"


def _norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def wilson(k: float, n: int, z: float = 1.96):
    if n == 0:
        return 0.0, 0.0, 1.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, max(centre - half, 0.0), min(centre + half, 1.0)


def load_themes() -> pd.DataFrame:
    frames = []
    for path, priority in ((CANONICAL, 1), (LLM_NEW, 2)):
        if not path.exists():
            continue
        f = pd.read_csv(path, low_memory=False)
        f["_join"] = f["council"].map(_norm) + "__" + f["application_number"].map(_norm)
        f["priority"] = priority
        frames.append(f[["_join", "case_primary_tags", "case_top_primary_tag", "priority"]])
    t = pd.concat(frames, ignore_index=True)
    t["case_primary_tags"] = t["case_primary_tags"].fillna("").astype(str)
    t = t[t["case_primary_tags"].ne("") & t["case_primary_tags"].ne("nan")]
    return t.sort_values("priority").drop_duplicates("_join", keep="first")


def main() -> None:
    data, _tr, _te, _y = build_data()
    themes = load_themes()
    data["_join"] = data["PlanningAuthority"].map(_norm) + "__" + data["ApplicationNumber"].map(_norm)
    data = data.merge(themes[["_join", "case_primary_tags", "case_top_primary_tag"]], on="_join", how="left")
    cohort = data[(data["units"] >= 10) & (data["target_refused"] == 1)
                  & data["case_primary_tags"].notna()].copy()
    cohort["tags"] = cohort["case_primary_tags"].str.split(";")
    all_tags = sorted({t for tags in cohort["tags"] for t in tags if t.strip()})
    all_tags = [t for t in all_tags if t in {"design_layout", "land_use_policy", "density_scale",
                                             "traffic_access", "premature_or_info_gap", "heritage_archaeology",
                                             "flooding_drainage", "residential_amenity", "ecology_trees",
                                             "water_wastewater", "other"}]
    for t in all_tags:
        cohort[t] = cohort["tags"].apply(lambda tags: 1 if t in tags else 0)
    cohort["text"] = cohort["description_stripped"].fillna("").astype(str)
    cohort["size"] = pd.cut(cohort["units"], [9, 30, 80, 500], labels=["s", "m", "l"])
    train = cohort[cohort["received_date_dt"] < CUTOFF].copy()
    test = cohort[cohort["received_date_dt"] >= CUTOFF].copy()
    report = {"themes": all_tags, "train_n": int(len(train)), "test_n": int(len(test)),
              "test_year_range": [int(test["received_date_dt"].dt.year.min()), int(test["received_date_dt"].dt.year.max())],
              "tag_multiplicity": {"train": round(float(train["tags"].apply(len).mean()), 2),
                                   "test": round(float(test["tags"].apply(len).mean()), 2)}}
    print(json.dumps({k: report[k] for k in ("train_n", "test_n", "test_year_range", "tag_multiplicity")}, indent=1))

    # per-theme baseline rates
    base = {t: float(train[t].mean()) for t in all_tags}
    # reference-class: authority x size smoothed rates
    ref_rates = {}
    global_sm = {t: (train[t].sum() + 1) / (len(train) + 2) for t in all_tags}
    for (auth, size), g in train.groupby(["PlanningAuthority", "size"], observed=True):
        if len(g) < 5:
            continue
        for t in all_tags:
            ref_rates[(auth, size, t)] = (g[t].sum() + 1) / (len(g) + 2)
    def ref_row(row):
        out = {}
        for t in all_tags:
            r = ref_rates.get((row["PlanningAuthority"], row["size"], t), None)
            out[t] = r if r is not None else global_sm[t]
        return out
    # lexicon fit on train only
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=20000, min_df=3, sublinear_tf=True)
    X_train = vectorizer.fit_transform(train["text"])
    X_test = vectorizer.transform(test["text"])
    lexicon = {}
    for t in all_tags:
        y = train[t].to_numpy()
        # chi2-like: mean tf-idf weight among positives vs negatives, weighted by df
        pos = X_train[y == 1].mean(axis=0)
        neg = X_train[y == 0].mean(axis=0)
        diff = np.asarray(pos - neg).ravel()
        words = np.array(vectorizer.get_feature_names_out())
        top = words[np.argsort(-diff)[:40]]
        lexicon[t] = [w for w in top if re.search(r"[a-z]", w)][:30]
    lex_counts = {}
    for t in all_tags:
        pat = "|".join(re.escape(w) for w in lexicon[t])
        lex_counts[t] = train["text"].str.count(pat, flags=re.IGNORECASE).to_numpy(), \
                        test["text"].str.count(pat, flags=re.IGNORECASE).to_numpy()
    # precedent vote: top-20 TF-IDF matches among train refused cases (time-safe)
    from sklearn.metrics.pairwise import cosine_similarity
    sims = cosine_similarity(X_test, X_train)
    sims = np.nan_to_num(sims, 0.0)
    topk = 20
    order = np.argsort(-sims, axis=1)[:, :topk]
    prec = {}
    for t in all_tags:
        votes = np.take(train[t].to_numpy(), order).mean(axis=1)
        prec[t] = votes
    # tfidf logistic per theme
    tfidf_pred = {}
    lex_pred = {}
    lex_models = {}
    for t in all_tags:
        m = LogisticRegression(C=0.5, solver="liblinear", max_iter=2000, class_weight="balanced")
        m.fit(X_train, train[t])
        tfidf_pred[t] = m.predict_proba(X_test)[:, 1]
        ml = LogisticRegression(C=1.0, solver="liblinear", max_iter=2000, class_weight="balanced")
        feats_t = np.column_stack([lex_counts[t][0], np.log1p(train["units"].fillna(0).to_numpy())])
        ml.fit(feats_t, train[t])
        lex_models[t] = ml
        feats_e = np.column_stack([lex_counts[t][1], np.log1p(test["units"].fillna(0).to_numpy())])
        lex_pred[t] = ml.predict_proba(feats_e)[:, 1]
    # ensemble: average of ref + lex + prec
    ens = {}
    for t in all_tags:
        ref_vec = np.array([ref_row(r)[t] for _, r in test.iterrows()])
        ens[t] = (ref_vec + lex_pred[t] + prec[t]) / 3.0

    metrics = {}
    per_theme = []
    for t in all_tags:
        y = test[t].to_numpy()
        row = {"theme": t, "n_test": int(y.sum()),
               "prevalence_train": round(float(train[t].mean()), 3)}
        for name, pred in (("base", np.full(len(y), base[t])), ("ref", np.array([ref_row(r)[t] for _, r in test.iterrows()])),
                           ("lex", lex_pred[t]), ("tfidf", tfidf_pred[t]),
                           ("prec", prec[t]), ("ens", ens[t])):
            p = np.nan_to_num(np.asarray(pred, dtype=float), 0.0)
            row[f"{name}_auc"] = round(float(roc_auc_score(y, p)), 3) if y.sum() >= 3 and (y == 0).sum() >= 3 else None
            row[f"{name}_ap"] = round(float(average_precision_score(y, p)), 3) if y.sum() >= 3 else None
            row[f"{name}_brier"] = round(float(np.mean((p - y) ** 2)), 3)
        per_theme.append(row)
        metrics[t] = row
    # coverage: top themes under each model vs true theme set
    model_names = ["base", "ref", "lex", "tfidf", "prec", "ens"]
    coverage = {}
    for name in model_names:
        if name == "base":
            P = np.tile(np.array([base[t] for t in all_tags]), (len(test), 1))
        elif name == "ref":
            P = np.array([[ref_row(r)[t] for t in all_tags] for _, r in test.iterrows()])
        elif name == "lex":
            P = np.column_stack([lex_pred[t] for t in all_tags])
        elif name == "tfidf":
            P = np.column_stack([tfidf_pred[t] for t in all_tags])
        elif name == "prec":
            P = np.column_stack([prec[t] for t in all_tags])
        else:
            P = np.column_stack([ens[t] for t in all_tags])
        Y = test[all_tags].to_numpy()
        coverage[name] = {}
        for k in (1, 2, 3):
            top = np.argsort(-P, axis=1)[:, :k]
            hit = np.array([any(Y[i, j] == 1 for j in top[i]) for i in range(len(Y))])
            coverage[name][f"top{k}"] = round(float(hit.mean()), 3)
        coverage[name]["mean_multilabel_prob"] = round(float(P.mean()), 3)
    report["coverage"] = coverage
    report["per_theme"] = per_theme
    report["lexicons"] = lexicon
    report["caveats"] = [
        "Conditional on refusal; not a refusal probability.",
        "Multi-label: themes co-occur; top-k coverage is the product metric.",
        "Test era 2022+ only; small n per theme - wide confidence.",
        "Lexicons fitted on train text only.",
    ]
    (OUT / "manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    joblib.dump({"vectorizer": vectorizer, "lex_models": lex_models, "lexicons": lexicon,
                 "base": base, "ref_rates": ref_rates, "global_sm": global_sm,
                 "all_tags": all_tags, "train": train[["_join", "text", "units"] + all_tags]},
                OUT / "theme_exposure_v6.joblib")
    print(json.dumps(coverage, indent=1))
    for row in per_theme:
        print(json.dumps(row))
    print("saved ->", OUT)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
