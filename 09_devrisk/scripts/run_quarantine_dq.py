"""Label-integrity quarantine queues + data-quality report.

Every impossible/suspicious record lands in a quarantine table with rule,
severity, evidence and status. Downstream models consume only the clean
view (labels minus quarantined). Produces silver/dq/quarantine.csv,
silver/dq/data_quality_report.json, silver/dq/labels_clean.csv.

Rules:
R1 impossible label ordering (completion < activation, negative durations)
R2 sale before commencement beyond tolerance (>365d)
R3 suspicious pre-grant sale (< grant + 90d)
R4 duplicate PPR attribution (same PPR row in >1 scheme)
R5 same-name estate contamination (shared bcms_name across schemes)
R6 low-confidence BCMS link only (no confirmed match method)
R7 phase inconsistencies (ccc block events > units*2 or units missing)
R8 CCC sequencing anomalies (first_ccc > last_ccc; CCC < grant-30d)
R9 pending/unverified rows present in label pool
R10 impossible dates (grant in future, activation > 4,000d)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
DQ = SILVER / "dq"
DQ.mkdir(parents=True, exist_ok=True)
SNAP = pd.Timestamp("2026-10-01")

BLOCKING = {"R1", "R2", "R3", "R8", "R10"}


def add(rows, case_key, rule, severity, description, evidence):
    rows.append({"case_key": case_key, "rule": rule, "severity": severity,
                 "description": description, "evidence": str(evidence)[:200],
                 "status": "open"})


def main() -> None:
    labels = pd.read_csv(SILVER / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                               columns=["case_key", "GrantDate"])
    register["grant_dt"] = pd.to_datetime(register["GrantDate"], utc=True, errors="coerce").dt.tz_localize(None)
    register = register.drop_duplicates("case_key")
    bcms_links = pd.read_csv(SILVER / "bcms_links_all_granted.csv", dtype=str)
    ccc = pd.read_csv(SILVER / "ccc_blocks.csv", dtype=str)
    sales = pd.read_csv(SILVER / "scheme_sales_bcms_notice_auto.csv", dtype=str)
    sales["sale_date"] = pd.to_datetime(sales["sale_date"], utc=True, errors="coerce").dt.tz_localize(None)

    rows = []
    labels_comm = labels[labels["activation_linked"].astype(str).str.lower() == "true"].copy()
    grant_map = register.dropna(subset=["grant_dt"]).set_index("case_key")["grant_dt"]
    labels_comm["grant_dt"] = labels_comm["case_key"].map(grant_map)
    labels_comm["comm_dt"] = labels_comm["grant_dt"] + pd.to_timedelta(
        pd.to_numeric(labels_comm["activation_days"], errors="coerce"), unit="D")

    for _, r in labels.iterrows():
        key = r["case_key"]
        pd_val = pd.to_numeric(r["planning_duration_days"], errors="coerce")
        if pd.notna(pd_val) and pd_val < 0:
            add(rows, key, "R1", "block", "negative planning duration", pd_val)
        a = pd.to_numeric(r["activation_days"], errors="coerce")
        c = pd.to_numeric(r["completion_days"], errors="coerce")
        if pd.notna(a) and pd.notna(c) and c < a:
            add(rows, key, "R1", "block", "completion before commencement", f"{c} < {a}")
        if pd.notna(a) and a > 4000:
            add(rows, key, "R10", "block", "activation > 4000d", a)
        if pd.notna(a) and a < 0:
            add(rows, key, "R1", "block", "negative activation", a)

    for _, r in labels_comm.iterrows():
        key = r["case_key"]
        if pd.isna(r["comm_dt"]):
            add(rows, key, "R10", "block", "commencement date missing (grant absent)", r["grant_dt"])
    for _, r in register.iterrows():
        if pd.notna(r["grant_dt"]) and r["grant_dt"] > SNAP:
            add(rows, r["case_key"], "R10", "warn", "grant in future", r["grant_dt"])

    comm_map = labels_comm.set_index("case_key")["comm_dt"]
    grant_map_all = register.set_index("case_key")["grant_dt"]
    for _, r in sales.iterrows():
        key = r["scheme_id"]
        if pd.isna(r["sale_date"]):
            continue
        comm = comm_map.get(key)
        grant = grant_map_all.get(key)
        if comm is not None and pd.notna(comm) and r["sale_date"] < comm - pd.Timedelta(days=365):
            add(rows, key, "R2", "block", "sale >365d before commencement",
                f"sale {r['sale_date'].date()} vs comm {comm.date()}")
        if grant is not None and pd.notna(grant) and r["sale_date"] < grant + pd.Timedelta(days=90):
            add(rows, key, "R3", "block", "sale before grant+90d",
                f"sale {r['sale_date'].date()} vs grant {grant.date()}")

    ppr_counts = sales["ppr_source_row_id"].value_counts()
    dup_ppr = set(ppr_counts[ppr_counts > 1].index)
    for _, r in sales[sales["ppr_source_row_id"].isin(dup_ppr)].iterrows():
        add(rows, r["scheme_id"], "R4", "block", "duplicate PPR attribution", r["ppr_source_row_id"])

    name_counts = sales.groupby("bcms_name")["scheme_id"].nunique()
    multi = set(name_counts[name_counts > 1].index) - {None}
    for name in multi:
        affected = sales[sales["bcms_name"] == name]["scheme_id"].unique()
        for key in affected:
            add(rows, key, "R5", "warn", "same-name estate shared across schemes", name)

    if "confidence_band" in bcms_links.columns and "match_method" in bcms_links.columns:
        confirmed_methods = {"planning_reference_variant", "planning_reference_exact"}
        per_scheme = bcms_links.groupby("scheme_id").agg(
            any_confirmed=("match_method", lambda s: s.isin(confirmed_methods).any()),
            min_band=("confidence_band", "min"))
        for key, r in per_scheme.iterrows():
            if not r["any_confirmed"]:
                add(rows, key, "R6", "warn", "BCMS links low-confidence only", r["min_band"])

    for _, r in ccc.iterrows():
        key = r["scheme_id"]
        units = pd.to_numeric(r["units"], errors="coerce")
        events = pd.to_numeric(r["ccc_events"], errors="coerce")
        if pd.isna(units) or units <= 0:
            add(rows, key, "R7", "warn", "CCC block missing units", r["units"])
        if pd.notna(units) and pd.notna(events) and events > max(units * 2, 4):
            add(rows, key, "R7", "warn", "CCC events far exceed units", f"{events} vs {units}")
        fc = pd.Timestamp(r["first_ccc"]).tz_localize(None) if pd.notna(r["first_ccc"]) else pd.NaT
        lc = pd.Timestamp(r["last_ccc"]).tz_localize(None) if pd.notna(r["last_ccc"]) else pd.NaT
        if pd.notna(fc) and pd.notna(lc) and fc > lc:
            add(rows, key, "R8", "block", "first_ccc after last_ccc", f"{fc} > {lc}")
        grant = grant_map_all.get(key)
        if pd.notna(fc) and grant is not None and pd.notna(grant) and fc < grant - pd.Timedelta(days=30):
            add(rows, key, "R8", "block", "CCC before grant-30d", f"{fc.date()} vs {grant.date()}")

    pending = labels[labels["activation_linked"].astype(str).str.lower() != "true"]
    for key in pending["case_key"]:
        add(rows, key, "R9", "warn", "pending/unverified row present in pool", "activation_linked != true")

    phase_path = SILVER / "phase_pilot" / "phase_denominators.csv"
    if phase_path.exists():
        phase = pd.read_csv(phase_path, dtype=str)
        for _, r in phase.iterrows():
            if str(r.get("resolved", "")).lower() != "true":
                add(rows, r["scheme_id"], "R11", "warn",
                    "phase units deviate >30% from register units (progress denominators exclude; other labels unaffected)",
                    f"phase_units_sum={r.get('phase_units_sum')} reg_units={r.get('reg_units')}")

    quar = pd.DataFrame(rows).drop_duplicates(subset=["case_key", "rule", "evidence"])
    quar.to_csv(DQ / "quarantine.csv", index=False)

    blocked = set(quar[quar["severity"] == "block"]["case_key"])
    pending_mask = labels["activation_linked"].astype(str).str.lower() != "true"
    clean = labels[(~labels["case_key"].isin(blocked)) & (~pending_mask)]
    clean.to_csv(DQ / "labels_clean.csv", index=False)

    exclusions = quar.groupby("rule").agg(n_rows=("case_key", "size"),
                                          n_schemes=("case_key", "nunique")).to_dict()
    report = {
        "snapshot": str(SNAP.date()),
        "label_pool_schemes": int(labels["case_key"].nunique()),
        "clean_schemes": int(clean["case_key"].nunique()),
        "blocked_schemes": int(len(blocked)),
        "quarantine_rows": int(len(quar)),
        "exclusions_by_rule": exclusions,
        "verified_coverage": {
            "activation_linked": int((labels["activation_linked"].astype(str).str.lower() == "true").sum()),
            "sales_linked": int((pd.to_numeric(labels["sales_linked"], errors="coerce").fillna(0) > 0).sum()),
            "completion_linked": int((labels["completion_linked"].astype(str).str.lower() == "true").sum()),
        },
        "source_failure_rates": {
            "bcms_links_by_method": bcms_links["match_method"].value_counts().to_dict() if "match_method" in bcms_links.columns else {},
            "sales_by_method": sales["match_method"].value_counts().to_dict() if "match_method" in sales.columns else {},
        },
        "downstream_models_excluded": {
            "frozen_v4_refusal": 0,
            "commencement_benchmark": int(len(blocked)),
            "sale_models": int(len(blocked)),
        },
    }
    (DQ / "data_quality_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str)[:4000])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
