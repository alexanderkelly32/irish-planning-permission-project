#!/usr/bin/env python3
"""Text-encoder experiment on the E feature set (register ratios + policy + flood + unused).

Variants:
  word12_50k        TF-IDF (1,2) 50k min_df2   [reference, = variant E text step]
  word13_50k        TF-IDF (1,3) 50k
  word13_100k       TF-IDF (1,3) 100k min_df1
  word12_char25     word (1,2) 50k + char_wb (2,5) 100k
  emb_word12        MiniLM embeddings (384d) + word (1,2) 50k
  emb_only          MiniLM embeddings only (no TF-IDF)

Same frozen split; holdout + GE10 subset reported.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "05_policy" / "current"

sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
from build_comparable_feature_experiment import COMPARABLE_FEATURES_PATH, V3_FEATURES  # noqa: E402
from build_national_residential_model_v2 import TRAIN_CUTOFF, load_data_with_history  # noqa: E402
from build_spatial_history_feature_experiment import CATEGORICAL  # noqa: E402
import build_v3_context_features_challenger as cc  # noqa: E402
import build_v3_policy_features_challenger as pc  # noqa: E402

EMBED_CACHE = ROOT / "07_context" / "current" / "description_embeddings_minilm.npy"


def build_pipeline(numeric: list[str], text_steps: list[tuple[str, object]], emb_columns: list[str] | None = None) -> Pipeline:
    from scipy import sparse as sp

    text_transformers = [("txt" if len(text_steps) == 1 else f"txt{i}", vec, "description_stripped") for i, (_, vec) in enumerate(text_steps)]
    blocks = [
        ("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric),
        ("cat", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]), CATEGORICAL),
        *text_transformers,
    ]
    if emb_columns:
        from sklearn.preprocessing import FunctionTransformer

        blocks.append(("emb", FunctionTransformer(lambda x: sp.csr_matrix(x.to_numpy())), emb_columns))
    preprocessor = ColumnTransformer(blocks, sparse_threshold=1.0)
    model = LogisticRegression(max_iter=3000, class_weight="balanced", C=0.5, solver="liblinear")
    return Pipeline([("preprocessor", preprocessor), ("model", model)])


def main() -> None:
    t0 = time.time()
    data = load_data_with_history().reset_index(drop=True)
    comparable = pd.read_parquet(COMPARABLE_FEATURES_PATH)
    data = data.merge(comparable, on="case_key", how="left")
    norm = lambda s: re.sub(r"[^a-z0-9]+", "", str(s).lower())
    corrected = pd.read_csv(ROOT / "02_development" / "current" / "ground_source_units_corrected.csv", low_memory=False)
    corrected_norm = {norm(k): v for k, v in zip(corrected["case_key"].astype(str), pd.to_numeric(corrected["units_corrected"], errors="coerce")) if pd.notna(v)}
    holdout_units = pd.read_csv(ROOT / "02_development" / "current" / "holdout_units_extracted.csv", low_memory=False)
    holdout_norm = {norm(k): v for k, v in zip(holdout_units["case_key"].astype(str), pd.to_numeric(holdout_units["units_final"], errors="coerce")) if pd.notna(v)}
    data["_nk"] = data["case_key"].astype(str).map(norm)
    data["units"] = pd.to_numeric(data["NumResidentialUnits"], errors="coerce")
    data["units"] = data["units"].fillna(data["_nk"].map(lambda k: corrected_norm.get(k)))
    data["units"] = data["units"].fillna(data["_nk"].map(lambda k: holdout_norm.get(k)))
    flood = pd.read_parquet(cc.FLOOD_CSV)
    flood = flood[["case_key", *pc.FLOOD_FEATURES]].drop_duplicates("case_key", keep="first")
    data = data.merge(flood, on="case_key", how="left")
    for feature in pc.FLOOD_FEATURES:
        data[feature] = pd.to_numeric(data[feature], errors="coerce")
    data["log_units"] = np.log1p(pd.to_numeric(data["units"], errors="coerce").clip(lower=0))
    data["log_site_area_sqm"] = np.log1p(pd.to_numeric(data["AreaofSite"], errors="coerce").clip(lower=0) * 10000)
    data["log_floor_area_sqm"] = np.log1p(pd.to_numeric(data["FloorArea"], errors="coerce").clip(lower=0))
    data["units_missing"] = data["log_units"].isna().astype(int)
    data["flood_any"] = pd.concat([pd.to_numeric(data[f], errors="coerce") for f in ["fluvial_hit_any", "coastal_hit_any"]], axis=1).max(axis=1).fillna(0)
    data["applicant_id"] = data["ApplicantForename"].fillna("").astype(str).str.lower() + "|" + data["ApplicantSurname"].fillna("").astype(str).str.lower()
    data["applicant_id"] = data["applicant_id"].replace({"|": "", "||": ""}, regex=False).replace("", np.nan)
    data = data.sort_values("received_date_dt").reset_index(drop=True)
    applicant_history = {}
    prior_count = np.zeros(len(data))
    prior_refusal = np.zeros(len(data))
    for i, (_, row) in enumerate(data.iterrows()):
        key = row.get("applicant_id")
        if pd.notna(key) and key:
            for _, refused in applicant_history.get(str(key), []):
                prior_count[i] += 1
                prior_refusal[i] += refused
            if pd.notna(row.get("target_refused")):
                applicant_history.setdefault(str(key), []).append((i, int(row["target_refused"])))
    data["applicant_prior_count"] = prior_count
    data["applicant_prior_refusal_rate"] = np.divide(prior_refusal, prior_count, out=np.zeros_like(prior_count), where=prior_count > 0)
    data = data.reset_index(drop=True)
    data["received_year"] = pd.to_numeric(data["received_year"], errors="coerce")
    plan_feats = pc.build_plan_features(data)
    data = data.merge(plan_feats, on="case_key", how="left")
    plan_cols = ["plan_unique_codes", "plan_mentions", "plan_codes_match_desc", "plan_mentions_match_desc"] + [f"plan_theme_{t}" for t in pc.THEME_ORDER] + ["plan_theme_other"]
    for col in plan_cols:
        if col not in data.columns:
            data[col] = 0.0
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data["policy_plan_covered"] = data["plan_unique_codes"].notna().astype(int)
    for col in plan_cols:
        data[col] = data[col].fillna(0)
    data["log_plan_unique_codes"] = np.log1p(data["plan_unique_codes"])
    data["log_plan_mentions"] = np.log1p(data["plan_mentions"])
    data["log_plan_codes_match_desc"] = np.log1p(data["plan_codes_match_desc"])
    site_ha = pd.to_numeric(data["AreaofSite"], errors="coerce")
    floor = pd.to_numeric(data["FloorArea"], errors="coerce").clip(lower=0)
    units = pd.to_numeric(data["units"], errors="coerce")
    data["density_units_per_ha"] = np.divide(units, site_ha, out=np.full(len(data), np.nan), where=(site_ha > 0) & units.notna()).clip(upper=1000)
    data["floor_area_ratio"] = np.divide(floor, site_ha * 10000, out=np.full(len(data), np.nan), where=site_ha > 0).clip(upper=5)
    data["site_sqm_per_unit"] = np.divide(site_ha * 10000, units, out=np.full(len(data), np.nan), where=units > 0).clip(upper=5000)
    data["avg_unit_floor_sqm"] = np.divide(floor, units, out=np.full(len(data), np.nan), where=units > 0).clip(upper=300)
    density = data["density_units_per_ha"]
    data["density_band_low"] = (density < 35).astype(int)
    data["density_band_mid"] = ((density >= 35) & (density <= 50)).astype(int)
    data["density_band_high"] = (density > 50).astype(int)
    data["density_over_45"] = (density > 45).astype(int)
    data["density_missing"] = density.isna().astype(int)
    landuse = cc.landuse_flags(data["LandUseCode"])
    data = pd.concat([data, landuse], axis=1)
    print(f"prep done in {time.time() - t0:.0f}s", flush=True)

    base_extras = [
        "log_units", "log_site_area_sqm", "log_floor_area_sqm", "units_missing",
        "applicant_prior_count", "applicant_prior_refusal_rate",
        *pc.FLOOD_FEATURES, "flood_any",
    ]
    policy_extras = [
        "log_plan_unique_codes", "log_plan_mentions", "policy_plan_covered",
        *[f"plan_theme_{t}" for t in pc.THEME_ORDER], "plan_theme_other",
        "log_plan_codes_match_desc",
    ]
    ratio_extras = [
        "density_units_per_ha", "floor_area_ratio", "site_sqm_per_unit", "avg_unit_floor_sqm",
        "density_band_low", "density_band_mid", "density_band_high", "density_over_45", "density_missing",
        "landuse_new_house", "landuse_housing_new", "landuse_extension", "landuse_retention", "landuse_missing",
    ]
    extras = base_extras + policy_extras + ratio_extras
    numeric = V3_FEATURES[3:] + extras

    embeddings = None
    if EMBED_CACHE.exists():
        embeddings = np.load(EMBED_CACHE)
    else:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("all-MiniLM-L6-v2")
        texts = data["description_stripped"].fillna("").astype(str).tolist()
        embeddings = model.encode(texts, batch_size=256, show_progress_bar=True, convert_to_numpy=True)
        np.save(EMBED_CACHE, embeddings)
    emb_cols = [f"emb_{i}" for i in range(embeddings.shape[1])]
    data = pd.concat([data, pd.DataFrame(embeddings, index=data.index, columns=emb_cols)], axis=1)
    print("embeddings ready", embeddings.shape, flush=True)

    train = data[data["received_date_dt"] < TRAIN_CUTOFF].copy()
    test = data[data["received_date_dt"] >= TRAIN_CUTOFF].copy().reset_index(drop=True)
    y = test["target_refused"]

    variants = {
        "word12_50k": [("w12", TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=50000, min_df=2))],
        "word13_50k": [("w13", TfidfVectorizer(stop_words="english", ngram_range=(1, 3), max_features=50000, min_df=2))],
        "word13_100k": [("w13b", TfidfVectorizer(stop_words="english", ngram_range=(1, 3), max_features=100000, min_df=1))],
        "word12_char25": [
            ("w12", TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=50000, min_df=2)),
            ("char25", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), max_features=100000, min_df=2)),
        ],
        "emb_only": [],
        "emb_word12": [("w12", TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=50000, min_df=2))],
    }
    results: dict[str, object] = {
        "frozen_v3_baseline": {"roc_auc": 0.7989, "average_precision": 0.4202},
        "train_n": int(len(train)),
        "test_n": int(len(test)),
    }
    result_path = OUTPUT_DIR / "raw_planning_v3_text_encoder_experiment.json"
    if result_path.exists():
        previous = json.loads(result_path.read_text(encoding="utf-8"))
        for key, value in previous.items():
            if key in variants and "error" not in value:
                results[key] = value
                print(json.dumps({key: value}), flush=True)
    for name, text_steps in variants.items():
        if name in results:
            continue
        t1 = time.time()
        use_emb = name.startswith("emb")
        num = numeric + emb_cols if use_emb else numeric
        features = V3_FEATURES + extras + (emb_cols if use_emb else [])
        pipeline = build_pipeline(num, text_steps, emb_columns=emb_cols if use_emb else None)
        try:
            pipeline.fit(train[features], train["target_refused"])
            p = pipeline.predict_proba(test[features])[:, 1]
        except Exception as exc:
            results[name] = {"error": type(exc).__name__, "detail": str(exc)[:200]}
            print(json.dumps({name: results[name]}), flush=True)
            continue
        results[name] = {
            "roc_auc": round(float(roc_auc_score(y, p)), 4),
            "average_precision": round(float(average_precision_score(y, p)), 4),
            "seconds": round(time.time() - t1, 0),
        }
        ge10_test = test[test["units"] >= 10].reset_index(drop=True)
        if len(ge10_test) >= 20 and ge10_test["target_refused"].nunique() == 2:
            p_ge10 = p[test["units"] >= 10]
            results[name]["ge10_subset"] = {
                "n": int(len(ge10_test)),
                "auc": round(float(roc_auc_score(ge10_test["target_refused"], p_ge10)), 4),
                "ap": round(float(average_precision_score(ge10_test["target_refused"], p_ge10)), 4),
            }
        print(json.dumps({name: results[name]}), flush=True)
    result_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
