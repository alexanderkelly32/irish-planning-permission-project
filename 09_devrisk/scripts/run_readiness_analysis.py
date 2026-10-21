"""Readiness analysis: clocks, time-safe developer mobilisation score,
day-zero model (temporal holdout), live landmark tests.

Analysis only - no production model changes.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402
from run_readiness_events import extract_date, classify, parse_date  # noqa: E402

DOCS = settings.SILVER_DIR / "idocs" / "docs"
SNAP = pd.Timestamp("2026-10-01")


def concordance(y_true: np.ndarray, y_pred: np.ndarray, event: np.ndarray) -> float:
    pairs = 0
    concordant = 0
    for i in range(len(y_true)):
        for j in range(i + 1, len(y_true)):
            if event[i] and event[j]:
                if y_true[i] == y_true[j]:
                    continue
                pairs += 1
                if (y_true[i] < y_true[j]) == (y_pred[i] < y_pred[j]):
                    concordant += 1
    return concordant / pairs if pairs else float("nan")


def main() -> None:
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                               columns=["case_key", "PlanningAuthority", "NumResidentialUnits",
                                        "DevelopmentDescription", "GrantDate"])
    register["grant_dt"] = pd.to_datetime(register["GrantDate"], utc=True, errors="coerce").dt.tz_localize(None)
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    labels["activation"] = pd.to_numeric(labels["activation_days"], errors="coerce")
    linked = labels[labels["activation_linked"].astype(str).str.lower() == "true"]
    entities = pd.read_csv(settings.SILVER_DIR / "developer_groups.csv", dtype=str)
    entities = entities[["case_key", "group_id"]].drop_duplicates("case_key")

    events_rows = []
    old_dated = 0
    new_dated = 0
    n_ok_docs = 0
    for scheme_dir in sorted(DOCS.glob("*/readiness")):
        ck = scheme_dir.parent.name
        for doc_json in sorted(scheme_dir.glob("*.json")):
            try:
                d = json.loads(doc_json.read_text(encoding="utf-8"))
            except Exception:
                continue
            if d.get("status") != "ok" or not d.get("text"):
                continue
            n_ok_docs += 1
            text = d["text"]
            comment = d.get("comment", "")
            dt, source = extract_date(text, comment)
            if dt is not None:
                new_dated += 1
            old_dt = parse_date(text[:500]) or parse_date(comment or "")
            if old_dt is not None:
                old_dated += 1
            categories, status, cond_no = classify(text, comment, d.get("type", ""))
            events_rows.append({"ck": ck, "docid": d.get("docid"), "doc_type": d.get("type", ""),
                                "comment": comment, "text_head": text[:200],
                                "event_date": dt, "date_source": source, "event_status": status,
                                "condition_no": cond_no})
    events = pd.DataFrame(events_rows)

    ck_map = {}
    for src_csv in [settings.SILVER_DIR / "idocs" / "validation_cohort.csv"]:
        if src_csv.exists():
            for ck in pd.read_csv(src_csv, dtype=str)["case_key"]:
                ck_map[ck[:80]] = ck
                ck_map[ck.replace(" ", "_")[:80]] = ck
    with zipfile.ZipFile(settings.SILVER_DIR / "audit_packs" / "PACK_24_residual_forensics.zip") as z:
        fz = pd.read_csv(z.open("residual_forensics_cohort.csv"))
        for ck in fz["case_key"]:
            ck_map[ck[:80]] = ck
            ck_map[ck.replace(" ", "_")[:80]] = ck

    events["ck"] = events["ck"].map(lambda k: ck_map.get(k) or ck_map.get(k.replace(" ", "_")))
    events = events[events["ck"].notna()]

    reliable = events[events["date_source"].isin(["date_label", "header", "comment"])]
    by_source = events.groupby("date_source").size().to_dict()
    by_council = events.assign(council=events["ck"].str.split("_").str[0]).groupby("council")["event_date"].apply(
        lambda s: round(s.notna().mean(), 3)).to_dict()
    by_type = events.assign(t=events["doc_type"].str.lower()).groupby("t")["event_date"].apply(
        lambda s: round(s.notna().mean(), 3)).sort_values(ascending=False).head(12).to_dict()
    coverage_extra = {
        "by_source": by_source,
        "by_council_dated_share": by_council,
        "by_type_dated_share": by_type,
        "n_schemes_with_reliable_dated_event": int(reliable["ck"].nunique()),
    }
    if len(events):
        audit = events.sample(min(50, len(events)), random_state=7)[["ck", "doc_type", "comment", "text_head", "event_date", "date_source"]]
        audit.to_csv(settings.SILVER_DIR / "idocs" / "date_audit_sample.csv", index=False)

    meta = {}
    for scheme_dir in sorted(DOCS.glob("*/readiness")):
        name = scheme_dir.parent.name
        resolved = ck_map.get(name) or ck_map.get(name.replace(" ", "_"))
        if resolved:
            meta[resolved] = len(list(scheme_dir.glob("*.json")))

    clocks = []
    for ck, group in events.groupby("ck"):
        real_key = ck
        reg_row = register[register["case_key"] == real_key]
        lab_row = linked[linked["case_key"] == real_key]
        if reg_row.empty or lab_row.empty:
            continue
        grant_dt = reg_row["grant_dt"].iloc[0]
        activation = lab_row["activation"].iloc[0]
        entry = {"ck": ck, "n_docs": meta.get(ck, 0), "n_events": len(group)}
        dated = group.dropna(subset=["event_date"]).sort_values("event_date")
        dated = dated[(dated["event_date"] >= grant_dt - pd.Timedelta(days=30)) &
                      (dated["event_date"] <= SNAP)]
        entry["n_dated"] = len(dated)
        entry["frac_dated"] = len(dated) / max(entry["n_docs"], 1)
        if pd.isna(grant_dt):
            clocks.append(entry)
            continue
        if len(dated):
            first = dated["event_date"].iloc[0]
            entry["grant_to_first_activity"] = (first - grant_dt).days
            accepted = dated[dated["event_status"].isin(["accepted", "all_clear"])]
            if len(accepted):
                entry["grant_to_first_accepted"] = (accepted["event_date"].iloc[0] - grant_dt).days
                entry["first_activity_to_first_accepted"] = (accepted["event_date"].iloc[0] - first).days
        if pd.notna(activation):
            commenced = grant_dt + pd.Timedelta(days=float(activation))
            if len(dated):
                entry["first_activity_before_commencement"] = int(dated["event_date"].iloc[0] <= commenced)
                acc = dated[dated["event_status"].isin(["accepted", "all_clear"])]
                entry["first_acceptance_before_commencement"] = int(len(acc) > 0 and acc["event_date"].iloc[0] <= commenced)
                pre_acc = acc[acc["event_date"] <= commenced]
                if len(pre_acc):
                    last_pre = pre_acc["event_date"].iloc[-1]
                    entry["grant_to_last_precomm_clearance"] = (last_pre - grant_dt).days
                    entry["last_precomm_clearance_to_commencement"] = activation - (last_pre - grant_dt).days
            entry["commencement_days"] = activation
            entry["n_events_pre_commencement"] = int(len(dated[dated["event_date"] <= commenced]))
            entry["n_rejections_pre_commencement"] = int(len(dated[(dated["event_date"] <= commenced) & (dated["event_status"] == "rejected")]))
        entry["n_rejections"] = int((group["event_status"] == "rejected").sum())
        entry["n_accepted"] = int(group["event_status"].isin(["accepted", "all_clear"]).sum())
        entry["has_all_clear"] = int((group["event_status"] == "all_clear").sum() > 0)
        cond_iter = group.dropna(subset=["condition_no"]).groupby("condition_no")["event_status"].apply(list)
        entry["n_iterated_conditions"] = int(sum(
            1 for v in cond_iter if "rejected" in v and any(s in ("accepted", "all_clear") for s in v)))
        clocks.append(entry)
    clocks_df = pd.DataFrame(clocks)
    clocks_df = clocks_df.sort_values("n_events").drop_duplicates("ck", keep="last")
    clocks_df.to_csv(settings.SILVER_DIR / "idocs" / "readiness_clocks_full.csv", index=False)

    cohort = pd.read_csv(settings.SILVER_DIR / "idocs" / "validation_cohort.csv", dtype=str)
    merged = cohort.merge(clocks_df.rename(columns={"ck": "case_key"}), on="case_key", how="inner")
    merged["activation"] = pd.to_numeric(merged["activation_days"], errors="coerce")
    merged["grant_dt"] = pd.to_datetime(merged["grant_dt"], utc=True, errors="coerce").dt.tz_localize(None)
    merged["tercile"] = merged["tercile"].astype(str)
    report = {"n_schemes_with_clocks": int(len(merged)),
              "date_coverage": {
                  "n_ok_docs": n_ok_docs,
                  "before_old_method": round(old_dated / max(n_ok_docs, 1), 3),
                  "after_new_method": round(new_dated / max(n_ok_docs, 1), 3),
              }}
    report["date_coverage"].update(coverage_extra)
    med = {}
    for metric in ["grant_to_first_activity", "grant_to_first_accepted",
                   "first_activity_to_first_accepted", "grant_to_last_precomm_clearance",
                   "last_precomm_clearance_to_commencement"]:
        if metric in merged.columns:
            by_tercile = merged.groupby("tercile")[metric].median()
            med[metric] = {k: (round(float(v), 1) if pd.notna(v) else None) for k, v in by_tercile.items()}
    report["median_by_tercile"] = med
    report["frac_dated_median"] = round(float(merged["frac_dated"].median()), 3)

    full = pd.concat([
        merged[["case_key", "tercile", "grant_dt", "activation", "group_id"]].reset_index(drop=True),
        clocks_df.set_index("ck").loc[merged["case_key"].values].reset_index(drop=True),
    ], axis=1)
    full = full.merge(register[["case_key", "PlanningAuthority", "NumResidentialUnits", "DevelopmentDescription"]],
                      on="case_key", how="left")
    full = full.merge(entities, on="case_key", how="left", suffixes=("", "_ent"))
    full["group_id"] = full["group_id"].fillna(full["group_id_ent"])
    full = full.sort_values("grant_dt")

    mob_rows = []
    full_sorted = full.sort_values("grant_dt")
    for idx, row in full_sorted.iterrows():
        gid = row["group_id"]
        prior = full_sorted[(full_sorted["grant_dt"] < row["grant_dt"])]
        if pd.notna(gid):
            prior = prior[prior["group_id"] == gid]
        entry = {"case_key": row["case_key"], "n_prior": int(len(prior))}
        for metric in ["grant_to_first_activity", "grant_to_first_accepted",
                       "first_activity_to_first_accepted", "last_precomm_clearance_to_commencement"]:
            if metric in prior.columns:
                entry[f"prior_{metric}"] = prior[metric].median()
        if "grant_to_first_activity" in prior.columns:
            entry["prior_pct_active_90d"] = (prior["grant_to_first_activity"] <= 90).mean()
        mob_rows.append(entry)
    mob = pd.DataFrame(mob_rows)
    mob.to_csv(settings.SILVER_DIR / "idocs" / "developer_mobilisation_scores.csv", index=False)
    report["mobilisation_score_coverage"] = {
        "n_schemes_with_prior": int(mob["n_prior"].gt(0).sum()),
        "n_schemes_total": int(len(mob)),
    }

    model_data = full.merge(mob[["case_key", "n_prior", "prior_grant_to_first_activity",
                                 "prior_grant_to_first_accepted", "prior_pct_active_90d"]],
                            on="case_key", how="left")
    model_data = model_data.dropna(subset=["grant_to_first_accepted"])
    model_data = model_data.dropna(subset=["grant_dt"])
    model_data["log_units"] = np.log1p(pd.to_numeric(model_data["NumResidentialUnits"], errors="coerce").fillna(0))
    model_data["type_apartment"] = model_data["DevelopmentDescription"].fillna("").str.contains(
        "apartment|duplex", case=False, regex=True).astype(int)
    model_data["grant_year"] = model_data["grant_dt"].dt.year
    model_data["y"] = np.log1p(model_data["grant_to_first_accepted"].astype(float))
    council_dummies = pd.get_dummies(model_data["PlanningAuthority"], prefix="council")
    base_feats = ["log_units", "type_apartment", "grant_year"]
    mob_feats = ["prior_grant_to_first_activity", "prior_pct_active_90d", "n_prior"]
    train = model_data[model_data["grant_year"] <= 2021].dropna(subset=["y"])
    test = model_data[model_data["grant_year"] >= 2022].dropna(subset=["y"])

    from sklearn.ensemble import GradientBoostingRegressor
    dayzero = {}
    if len(train) >= 25 and len(test) >= 10:
        for name, feats in [("base", base_feats), ("base_mob", base_feats + mob_feats)]:
            X_tr = pd.concat([train[feats].fillna(0.0), council_dummies.loc[train.index].fillna(0).astype(int)], axis=1)
            X_te = pd.concat([test[feats].fillna(0.0), council_dummies.loc[test.index].fillna(0).astype(int)], axis=1)
            model = GradientBoostingRegressor(n_estimators=300, max_depth=3, learning_rate=0.05,
                                              min_samples_leaf=5, random_state=7)
            model.fit(X_tr, train["y"])
            pred = model.predict(X_te)
            y_true = np.expm1(test["y"].to_numpy())
            y_pred = np.expm1(pred)
            c_idx = concordance(y_true, y_pred, np.ones(len(y_true)))
            dayzero[name] = {
                "n_train": int(len(train)), "n_test": int(len(test)),
                "mae_days": round(float(np.mean(np.abs(y_true - y_pred))), 1),
                "median_abs_days": round(float(np.median(np.abs(y_true - y_pred))), 1),
                "c_index": round(float(c_idx), 3),
            }
    report["dayzero_model"] = dayzero

    landmarks = [30, 60, 90, 180]
    live = {}
    for t in landmarks:
        rows = []
        for _, row in model_data.iterrows():
            act = row.get("commencement_days")
            if pd.isna(act) or act <= t:
                continue
            grant_dt = row["grant_dt"]
            cutoff = grant_dt + pd.Timedelta(days=t)
            ev = reliable[reliable["ck"] == row["case_key"]]
            if len(ev) == 0:
                group = "unknown"
            else:
                acc_by_t = any((pd.notna(d) and d <= cutoff and s in ("accepted", "all_clear"))
                               for d, s in zip(ev["event_date"], ev["event_status"]))
                act_by_t = any((pd.notna(d) and d <= cutoff) for d in ev["event_date"])
                group = "accepted_by_t" if acc_by_t else ("activity_only" if act_by_t else "no_activity")
            rows.append({"group": group, "remaining": act - t})
        sub = pd.DataFrame(rows)
        for g, gsub in sub.groupby("group"):
            live[f"t{t}_{g}"] = {
                "n": int(len(gsub)),
                "median_remaining_days": round(float(gsub["remaining"].median()), 1),
                "pct_commenced_next_90": round(float((gsub["remaining"] <= 90).mean() * 100), 1),
                "pct_commenced_next_180": round(float((gsub["remaining"] <= 180).mean() * 100), 1),
                "pct_commenced_next_365": round(float((gsub["remaining"] <= 365).mean() * 100), 1),
            }
    report["live_landmark"] = live

    out = settings.SILVER_DIR / "idocs" / "readiness_analysis_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
