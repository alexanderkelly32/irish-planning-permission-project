"""Runner: fold PACK_21 verdicts (OSM-confirmed scheme labels) into the
pull classifier; retrain with the OSM flag as a feature; re-score pending."""
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
from run_phase_ppr_linking import tokens

RNG = 7


def osm_feature(appno: str, address: str, inventory: dict) -> int:
    token_set = inventory.get(appno, set())
    if not token_set:
        return 0
    return int(len(tokens(address) & token_set) >= 2)


if __name__ == "__main__":
    osm_dir = settings.RAW_DIR / "osm_estates"
    inventory = {}
    for osm_file in osm_dir.glob("*.geojson"):
        payload = json.loads(osm_file.read_text(encoding="utf-8"))
        token_set = set()
        for element in payload.get("elements", []):
            tag_map = element.get("tags", {})
            token_set |= tokens(f"{tag_map.get('addr:street', '')} {tag_map.get('addr:place', '')} {tag_map.get('name', '')}")
        inventory[osm_file.stem] = token_set

    fills = pd.read_csv(settings.SILVER_DIR / "audit_packs" / "manual_fills_pull.csv")
    fills["scheme_id"] = fills["scheme_id"].astype(str)
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    grant_map = dict(zip(cohort["case_key"].astype(str), pd.to_datetime(cohort["grant_date_dt"], utc=True, errors="coerce")))

    packs = [
        (settings.SILVER_DIR / "audit_packs" / "returned" / "audit_manual_pull_verify_v2_COMPLETED_2026-10-01.xlsx", "Audit"),
        (settings.SILVER_DIR / "audit_packs" / "returned" / "audit_pull_band_confirm_COMPLETED_2026-10-01.xlsx", "Audit"),
        (settings.SILVER_DIR / "audit_packs" / "returned" / "audit_osm_band_confirm_COMPLETED_2026-10-02.xlsx", "Audit"),
    ]
    rows = []
    for path, sheet in packs:
        if not path.exists():
            continue
        audit = pd.read_excel(path, sheet_name=sheet)
        for _, row in audit.iterrows():
            if str(row.get("verdict") or "").strip().lower() not in ("confirmed", "rejected"):
                continue
            fill = fills[fills["scheme_id"] == str(row["scheme_id"])]
            estate_fill = fill["estate_name_1"].iloc[0] if len(fill) else ""
            grant = grant_map.get(str(row["scheme_id"]))
            days = (pd.to_datetime(row["sale_date"], utc=True, errors="coerce") - grant).days if pd.notna(grant) else 0.0
            base = feature_row(str(estate_fill), str(row.get("register_address") or ""), str(row["address"]),
                               str(row.get("eircode") or ""), days)
            base["osm_flag"] = osm_feature(str(row["scheme_id"]).split("__")[1], str(row["address"]), inventory)
            base["label"] = 1 if str(row["verdict"]).strip().lower() == "confirmed" else 0
            rows.append(base)
    train = pd.DataFrame(rows)
    print("training rows:", len(train), "positives:", int(train["label"].sum()))

    FEATURES = [c for c in train.columns if c != "label"]
    X = train[FEATURES].to_numpy()
    y = train["label"].to_numpy()
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=RNG)
    aucs = []
    for tr, va in skf.split(X, y):
        model = GradientBoostingClassifier(n_estimators=150, max_depth=2, learning_rate=0.05, random_state=RNG)
        model.fit(X[tr], y[tr])
        aucs.append(roc_auc_score(y[va], model.predict_proba(X[va])[:, 1]))

    model = GradientBoostingClassifier(n_estimators=150, max_depth=2, learning_rate=0.05, random_state=RNG)
    model.fit(X, y)

    verified = pd.read_csv(settings.SILVER_DIR / "scheme_sales_verified.csv", low_memory=False)
    verified["scheme_id"] = verified["scheme_id"].astype(str)
    pending = verified[verified["verification_status"].isin(["pending", "promoted_band"])].copy()
    scheme_fill = dict(zip(fills["scheme_id"], fills["estate_name_1"].fillna("").astype(str)))
    addr_map = dict(zip(cohort["case_key"].astype(str), cohort["DevelopmentAddress"].fillna("").astype(str)))
    feat_rows = []
    for _, row in pending.iterrows():
        base = feature_row(scheme_fill.get(row["scheme_id"], ""), addr_map.get(row["scheme_id"], ""),
                           str(row["address"]), str(row.get("eircode") or ""),
                           (pd.to_datetime(row["sale_date"], utc=True, errors="coerce") - grant_map.get(row["scheme_id"])).days)
        base["osm_flag"] = osm_feature(row["scheme_id"].split("__")[1], str(row["address"]), inventory)
        feat_rows.append(base)
    pending_feat = pd.DataFrame(feat_rows)[FEATURES]
    pending["p_link"] = model.predict_proba(pending_feat.to_numpy())[:, 1]

    report = {
        "cv_auc": round(float(np.mean(aucs)), 3),
        "bands": {str(t): {"rows": int((pending["p_link"] >= t).sum()),
                           "schemes": int(pending[pending["p_link"] >= t]["scheme_id"].nunique())}
                  for t in (0.95, 0.9, 0.8)},
        "band_55pct_pack21": {"confirmed": 33, "rejected": 27},
    }
    pending.to_csv(settings.SILVER_DIR / "pending_rows_scored_v3.csv", index=False)
    out = settings.SILVER_DIR / "pull_classifier_v3_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
