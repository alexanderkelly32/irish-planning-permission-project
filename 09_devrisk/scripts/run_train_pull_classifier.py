"""Runner: pull-verification classifier on the 80 row-level verdicts.

Features: estate-fill token overlap with the pulled address, anchor
(register-address) overlap, total overlap, eircode presence, sale-to-grant
gap. Trains GBM, CV AUC, re-scores the 60k pending rows, promotes the
high-confidence band, and packs PACK_20 for its confirmation.
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
from run_phase_ppr_linking import tokens  # noqa: E402

RNG = 7


def feature_row(fill: str, anchor: str, address: str, eircode: str, days: float, label: int = 0) -> dict:
    fill_tokens = tokens(fill)
    anchor_tokens = tokens(anchor)
    address_tokens = tokens(address)
    return {
        "estate_overlap": len(fill_tokens & address_tokens),
        "estate_size": max(1, len(fill_tokens)),
        "anchor_overlap": len(anchor_tokens & address_tokens),
        "total_overlap": len((fill_tokens | anchor_tokens) & address_tokens),
        "has_eircode": int(bool(str(eircode or "").strip())),
        "days_after_grant": float(days) if pd.notna(days) else 0.0,
        "label": int(label),
    }


if __name__ == "__main__":
    audit = pd.read_excel(settings.SILVER_DIR / "audit_packs" / "returned" / "audit_manual_pull_verify_v2_COMPLETED_2026-10-01.xlsx",
                          sheet_name="Audit")
    fills = pd.read_csv(settings.SILVER_DIR / "audit_packs" / "manual_fills_pull.csv")
    fills["scheme_id"] = fills["scheme_id"].astype(str)
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    grant_map = dict(zip(cohort["case_key"].astype(str), pd.to_datetime(cohort["grant_date_dt"], utc=True, errors="coerce")))

    train_rows = []
    for _, row in audit.iterrows():
        fill = fills[fills["scheme_id"] == str(row["scheme_id"])]
        estate_fill = fill["estate_name_1"].iloc[0] if len(fill) else ""
        anchor = str(row.get("register_address") or "")
        grant = grant_map.get(str(row["scheme_id"]))
        days = (pd.to_datetime(row["sale_date"], utc=True, errors="coerce") - grant).days if pd.notna(grant) else 0.0
        verdict = str(row["verdict"]).strip().lower()
        train_rows.append(feature_row(str(estate_fill), anchor, str(row["address"]), str(row.get("eircode") or ""), days,
                                      label=1 if verdict == "confirmed" else 0))

    train = pd.DataFrame(train_rows)
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
    pending = verified[verified["verification_status"] == "pending"].copy()
    scheme_fill = dict(zip(fills["scheme_id"], fills["estate_name_1"].fillna("").astype(str)))
    addr_map = dict(zip(cohort["case_key"].astype(str), cohort["DevelopmentAddress"].fillna("").astype(str)))
    feature_rows = []
    for _, row in pending.iterrows():
        feature_rows.append(feature_row(
            scheme_fill.get(row["scheme_id"], ""), addr_map.get(row["scheme_id"], ""),
            str(row["address"]), str(row.get("eircode") or ""),
            (pd.to_datetime(row["sale_date"], utc=True, errors="coerce") - grant_map.get(row["scheme_id"])).days,
        ))
    pending_feat = pd.DataFrame(feature_rows).drop(columns=["label"])
    pending["p_link"] = model.predict_proba(pending_feat.to_numpy())[:, 1]

    report = {
        "cv_auc": round(float(np.mean(aucs)), 3),
        "band_sizes": {str(t): int((pending["p_link"] >= t).sum()) for t in (0.9, 0.8, 0.7, 0.5)},
        "band_schemes": {str(t): int(pending[pending["p_link"] >= t]["scheme_id"].nunique()) for t in (0.9, 0.8, 0.7, 0.5)},
    }

    # Promote only the p>=0.9 band (expect high precision), pack for confirmation.
    high = pending[pending["p_link"] >= 0.9].copy()
    verified.loc[verified["verification_status"] == "pending", "verification_status"] = "pending"
    promoted_ids = set(high["scheme_id"])
    if promoted_ids:
        verified.loc[verified["scheme_id"].isin(promoted_ids) & (verified["verification_status"] == "pending"), "verification_status"] = "promoted_band"
        verified.to_csv(settings.SILVER_DIR / "scheme_sales_verified.csv", index=False)
    report["promoted_schemes"] = len(promoted_ids)

    sample = high.groupby("scheme_id").first().reset_index().sample(min(60, len(high)), random_state=7)
    sample = sample[["scheme_id", "address", "sale_date", "price", "p_link"]]
    sample["register_address"] = sample["scheme_id"].map(addr_map)
    sample["verdict"] = ""
    sample["verdict_note"] = ""
    csv_path = settings.SILVER_DIR / "audit" / "audit_pull_band_confirm.csv"
    sample.to_csv(csv_path, index=False)
    pack_dir = settings.SILVER_DIR / "audit_packs"
    zip_path = pack_dir / "PACK_20_pull_band_confirm.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(csv_path, arcname=csv_path.name)
        archive.writestr("INSTRUCTIONS.txt", (
            "PACK 20: classifier-promoted pull band (p>=0.9).\n"
            "Mark verdict PER ROW on the Audit sheet (confirmed/rejected).\n"
            "RETURN: into the 'returned' folder next to this zip.\n"
        ))
    report["pack20"] = str(zip_path)

    pending.to_csv(settings.SILVER_DIR / "pending_rows_scored.csv", index=False)
    out = settings.SILVER_DIR / "pull_classifier_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
