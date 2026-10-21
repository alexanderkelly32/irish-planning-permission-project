"""Runner: train a BCMS link classifier on the human audit verdicts.

The audit queues provide labelled candidate pairs (confirmed vs rejected)
with match features. Train a classifier, apply it to ALL candidate pairs for
unlinked schemes, and take high-probability links as new confirmeds (audit
only the uncertain band). This replaces hand-tuned thresholds with learned
matching.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingClassifier  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402
from sklearn.model_selection import StratifiedKFold  # noqa: E402

from devrisk import settings  # noqa: E402

RNG = 7

FEATURES = ["distance_metres", "uncommon_token_overlap", "name_token_overlap", "unit_abs_diff"]


def build_training_set() -> pd.DataFrame:
    rows = []
    audit_files = [
        ("audit_bcms_name_links_FULL_COMPLETED.xlsx", "xlsx"),
        ("audit_bcms_name_links_COMPLETED.csv", "csv"),
    ]
    for name, kind in audit_files:
        path = settings.SILVER_DIR / name
        if not path.exists():
            continue
        frame = pd.read_excel(path) if kind == "xlsx" else pd.read_csv(path)
        if "verdict" not in frame.columns:
            continue
        filled = frame[frame["verdict"].fillna("").astype(str).str.strip().str.lower().isin(["confirmed", "rejected"])].copy()
        filled["scheme_units"] = pd.to_numeric(filled.get("scheme_units"), errors="coerce")
        filled["bcms_units"] = pd.to_numeric(filled.get("bcms_units"), errors="coerce")
        filled["unit_abs_diff"] = (filled["scheme_units"] - filled["bcms_units"]).abs()
        for _, row in filled.iterrows():
            label = 1 if str(row["verdict"]).strip().lower() == "confirmed" else 0
            feature_row = {}
            for feature in FEATURES:
                value = row.get(feature)
                feature_row[feature] = float(value) if pd.notna(value) else np.nan
            feature_row["label"] = label
            rows.append(feature_row)
    frame = pd.DataFrame(rows)
    for feature in FEATURES:
        frame[feature] = frame[feature].fillna(frame[feature].median())
    return frame


if __name__ == "__main__":
    training = build_training_set()
    print(f"labelled pairs: {len(training)} (positives {int(training['label'].sum())})", flush=True)

    X = training[FEATURES].to_numpy()
    y = training["label"].to_numpy()

    # Cross-validated discrimination on the audit labels.
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=RNG)
    aucs = []
    for tr_idx, va_idx in skf.split(X, y):
        model = GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=RNG)
        model.fit(X[tr_idx], y[tr_idx])
        p = model.predict_proba(X[va_idx])[:, 1]
        aucs.append(roc_auc_score(y[va_idx], p))
    print(f"CV AUC on audit labels: {np.mean(aucs):.3f} (+/- {np.std(aucs):.3f})", flush=True)

    # Apply to the unadjudicated candidates (the rest of the FULL queue).
    full_path = settings.SILVER_DIR / "audit" / "audit_bcms_name_links_FULL.csv"
    candidates = pd.read_csv(full_path)
    candidates["scheme_units"] = pd.to_numeric(candidates.get("scheme_units"), errors="coerce")
    candidates["bcms_units"] = pd.to_numeric(candidates.get("bcms_units"), errors="coerce")
    candidates["unit_abs_diff"] = (candidates["scheme_units"] - candidates["bcms_units"]).abs()
    X_cand = candidates[FEATURES].fillna(candidates[FEATURES].median()).to_numpy()

    model = GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=RNG)
    model.fit(X, y)
    candidates["p_link"] = model.predict_proba(X_cand)[:, 1]

    # Precision-first thresholds: only take the top band as new confirms.
    report = {"cv_auc": round(float(np.mean(aucs)), 3)}
    for threshold in (0.9, 0.8, 0.7):
        high = candidates[candidates["p_link"] >= threshold]
        report[f"threshold_{threshold}"] = {
            "new_confirmed_pairs": int(len(high)),
            "new_schemes": int(high["scheme_id"].nunique()),
        }
    candidates.to_csv(settings.SILVER_DIR / "bcms_link_classifier_scores.csv", index=False)
    out = settings.SILVER_DIR / "bcms_link_classifier.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
