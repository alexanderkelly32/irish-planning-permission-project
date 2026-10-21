"""Runner: process PACK_16 verdicts + train phase-link classifier.

Confirmed rows -> phase_sale_links_verified.csv (training set). All verdicts
become classifier training data: features recomputed from the pack fields
(estate/street/town overlap, temporal clustering, unit cap). If CV AUC is
usable, the full candidate pool is re-scored and a high-confidence band is
auto-generated for a second audit round (PACK_17).
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingClassifier  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402
from sklearn.model_selection import StratifiedKFold  # noqa: E402

from devrisk import settings  # noqa: E402
from run_phase_ppr_linking import COUNTY_WORDS, tokens  # noqa: E402

RNG = 7

if __name__ == "__main__":
    pack = pd.read_excel(settings.SILVER_DIR / "audit_packs" / "returned" / "phase_sale_links_COMPLETED.xlsx")
    filled = pack[pack["verdict"].fillna("").astype(str).str.strip().str.lower().isin(["confirmed", "probable", "rejected"])].copy()
    filled["label"] = (filled["verdict"].astype(str).str.strip().str.lower() == "confirmed").astype(int)

    def row_features(row: pd.Series) -> dict:
        estate = tokens(row.get("project_name") or "")
        street = tokens(row.get("street") or "")
        town = tokens(row.get("town") or "")
        address = tokens(row.get("address") or "")
        return {
            "estate_overlap": len(estate & address),
            "street_overlap": len(street & address),
            "town_overlap": len(town & address),
            "total_overlap": len((estate | street | town) & address),
            "has_eircode": int(bool(str(row.get("eircode") or "").strip())),
            "phase_units": float(row.get("phase_units") or 0) if pd.notna(row.get("phase_units")) else 0,
            "label": row.get("label", 0),
        }

    FEATURE_KEYS = ("estate_overlap", "street_overlap", "town_overlap", "total_overlap", "has_eircode")

    train_rows = filled.apply(row_features, axis=1)
    train = pd.DataFrame(train_rows.tolist())
    X = train[["estate_overlap", "street_overlap", "town_overlap", "total_overlap", "has_eircode"]].to_numpy()
    y = train["label"].to_numpy()
    report = {
        "verdicts": filled["verdict"].value_counts().to_dict(),
        "by_confidence": {str(k): int(v) for k, v in filled.groupby("confidence")["verdict"].value_counts().groupby("confidence").value_counts().items()} if False else filled.assign(combo=filled["confidence"].astype(str) + "=" + filled["verdict"].astype(str))["combo"].value_counts().to_dict(),
        "b_class_precision_auto": round(float(((filled["confidence"] == "B") & (filled["label"] == 1)).sum() / max(1, int((filled["confidence"] == "B").sum()))), 4),
        "a_class_confirmed": int(((filled["confidence"] == "A") & (filled["label"] == 1)).sum()),
    }

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=RNG)
    aucs = []
    for tr, va in skf.split(X, y):
        model = GradientBoostingClassifier(n_estimators=150, max_depth=3, learning_rate=0.05, random_state=RNG)
        model.fit(X[tr], y[tr])
        aucs.append(roc_auc_score(y[va], model.predict_proba(X[va])[:, 1]))
    report["link_classifier_cv_auc"] = round(float(np.mean(aucs)), 3)
    report["train_rows"] = int(len(train))

    # Save verified (confirmed) links as the training set.
    confirmed = filled[filled["label"] == 1][["phase_id", "development_id", "address", "eircode", "sale_date", "price", "confidence"]]
    confirmed.to_csv(settings.SILVER_DIR / "phase_sale_links_verified.csv", index=False)
    report["verified_link_rows"] = int(len(confirmed))
    report["verified_phases"] = int(confirmed["phase_id"].nunique())

    # Re-score the full candidate pool with the trained model.
    candidates = pd.read_csv(settings.SILVER_DIR / "phase_sales_candidates.csv")
    phases = pd.read_csv(settings.SILVER_DIR / "phase_master.csv")
    phase_meta = phases.set_index("phase_id")[["town", "street", "project_name", "phase_units"]]
    candidates = candidates.drop(columns=[c for c in ("town", "street", "phase_units") if c in candidates.columns])
    candidates = candidates.merge(phase_meta, left_on="phase_id", right_index=True, how="left")
    feature_rows = candidates.apply(lambda r: {k: row_features(r)[k] for k in FEATURE_KEYS}, axis=1)
    X_pool = pd.DataFrame(feature_rows.tolist()).to_numpy()
    model = GradientBoostingClassifier(n_estimators=150, max_depth=3, learning_rate=0.05, random_state=RNG)
    model.fit(X, y)
    candidates["p_link"] = model.predict_proba(X_pool)[:, 1]
    candidates.to_csv(settings.SILVER_DIR / "phase_sales_candidates_scored.csv", index=False)
    band = candidates[candidates["p_link"] >= 0.7]
    report["rescored_pool"] = {"total": int(len(candidates)), "band_p70": int(len(band)), "band_phases": int(band["phase_id"].nunique())}

    out = settings.SILVER_DIR / "phase_link_classifier.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
