"""Runner: fold PACK_20 verdicts into the pull classifier, retrain, re-band."""
import json
import sys
from pathlib import Path

sys.path.insert(0, r"09_devrisk")
sys.path.insert(0, r"09_devrisk/scripts")

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold

from devrisk import settings
from run_train_pull_classifier import feature_row

RNG = 7


def build_training() -> pd.DataFrame:
    rows = []
    # PACK 19 row-level (Audit sheet)
    audit19 = pd.read_excel(settings.SILVER_DIR / "audit_packs" / "returned" / "audit_manual_pull_verify_v2_COMPLETED_2026-10-01.xlsx", sheet_name="Audit")
    # PACK 20
    audit20 = pd.read_excel(settings.SILVER_DIR / "audit_packs" / "returned" / "audit_pull_band_confirm_COMPLETED_2026-10-01.xlsx", sheet_name="Audit")
    fills = pd.read_csv(settings.SILVER_DIR / "audit_packs" / "manual_fills_pull.csv")
    fills["scheme_id"] = fills["scheme_id"].astype(str)
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    grant_map = dict(zip(cohort["case_key"].astype(str), pd.to_datetime(cohort["grant_date_dt"], utc=True, errors="coerce")))

    for audit in (audit19, audit20):
        for _, row in audit.iterrows():
            if str(row.get("verdict") or "").strip().lower() not in ("confirmed", "rejected"):
                continue
            fill = fills[fills["scheme_id"] == str(row["scheme_id"])]
            estate_fill = fill["estate_name_1"].iloc[0] if len(fill) else ""
            grant = grant_map.get(str(row["scheme_id"]))
            days = (pd.to_datetime(row["sale_date"], utc=True, errors="coerce") - grant).days if pd.notna(grant) else 0.0
            rows.append(feature_row(str(estate_fill), str(row.get("register_address") or ""), str(row["address"]),
                                    str(row.get("eircode") or ""), days,
                                    label=1 if str(row["verdict"]).strip().lower() == "confirmed" else 0))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    train = build_training()
    print("training rows:", len(train), "positives:", int(train["label"].sum()))
    X = train.drop(columns=["label"]).to_numpy()
    y = train["label"].to_numpy()
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=RNG)
    aucs = []
    for tr, va in skf.split(X, y):
        model = GradientBoostingClassifier(n_estimators=120, max_depth=2, learning_rate=0.05, random_state=RNG)
        model.fit(X[tr], y[tr])
        aucs.append(roc_auc_score(y[va], model.predict_proba(X[va])[:, 1]))

    model = GradientBoostingClassifier(n_estimators=120, max_depth=2, learning_rate=0.05, random_state=RNG)
    model.fit(X, y)

    verified = pd.read_csv(settings.SILVER_DIR / "scheme_sales_verified.csv", low_memory=False)
    verified["scheme_id"] = verified["scheme_id"].astype(str)
    pending = verified[verified["verification_status"].isin(["pending", "promoted_band"])].copy()
    fills = pd.read_csv(settings.SILVER_DIR / "audit_packs" / "manual_fills_pull.csv")
    fills["scheme_id"] = fills["scheme_id"].astype(str)
    scheme_fill = dict(zip(fills["scheme_id"], fills["estate_name_1"].fillna("").astype(str)))
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    addr_map = dict(zip(cohort["case_key"].astype(str), cohort["DevelopmentAddress"].fillna("").astype(str)))
    grant_map = dict(zip(cohort["case_key"].astype(str), pd.to_datetime(cohort["grant_date_dt"], utc=True, errors="coerce")))
    feat_rows = []
    for _, row in pending.iterrows():
        feat_rows.append(feature_row(scheme_fill.get(row["scheme_id"], ""), addr_map.get(row["scheme_id"], ""),
                                     str(row["address"]), str(row.get("eircode") or ""),
                                     (pd.to_datetime(row["sale_date"], utc=True, errors="coerce") - grant_map.get(row["scheme_id"])).days))
    pending["p_link"] = model.predict_proba(pd.DataFrame(feat_rows).drop(columns=["label"]).to_numpy())[:, 1]

    # Promote only confirmed-by-pack rows + the new p>=0.95 band, then re-pack.
    confirmed_schemes = set(train[train["label"] == 1]["scheme_id"]) if "scheme_id" in train.columns else set()
    report = {
        "cv_auc_140_labels": round(float(np.mean(aucs)), 3),
        "band_p95": {"rows": int((pending["p_link"] >= 0.95).sum()),
                     "schemes": int(pending[pending["p_link"] >= 0.95]["scheme_id"].nunique())},
        "band_p98": {"rows": int((pending["p_link"] >= 0.98).sum()),
                     "schemes": int(pending[pending["p_link"] >= 0.98]["scheme_id"].nunique())},
    }
    pending.to_csv(settings.SILVER_DIR / "pending_rows_scored_v2.csv", index=False)
    out = settings.SILVER_DIR / "pull_classifier_v2_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
