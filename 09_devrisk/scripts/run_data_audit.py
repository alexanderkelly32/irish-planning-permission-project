"""Runner: data-coverage and engine-readiness audit.

Measures, from the actual data layers:
  - register coverage (national, 10+ unit, grants, dates, FI/appeal fields)
  - BCMS silver coverage (geo, planning refs, completions)
  - PPR silver coverage (dates, prices, county)
  - linkage coverage (BCMS confirmed, PPR confirmed)
  - refusal-theme label coverage
  - FI-corpus (04_fi) coverage on the pool
  - per-engine readiness: rows available for training/evaluation per engine
Outputs: data/silver/data_coverage_audit.json + console summary.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

CENSOR = "2026-09-27"


def _pct(numerator: int, denominator: int) -> float:
    return round(numerator / max(1, denominator) * 100, 1)


def audit() -> dict:
    report: dict = {"as_of": CENSOR}

    # --- register ---
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    received = pd.to_datetime(register["ReceivedDate"], utc=True, errors="coerce")
    decided = pd.to_datetime(register["DecisionDate"], utc=True, errors="coerce")
    granted = pd.to_datetime(register["GrantDate"], utc=True, errors="coerce")
    units = pd.to_numeric(register["NumResidentialUnits"], errors="coerce")
    ge10 = units.ge(10)
    report["register"] = {
        "total_rows": int(len(register)),
        "date_range": f"{received.min():%Y-%m-%d} .. {received.max():%Y-%m-%d}",
        "authorities": int(register["PlanningAuthority"].nunique()),
        "residential_10plus_rows": int(ge10.sum()),
        "ge10_with_decision_date": int((ge10 & decided.notna()).sum()),
        "ge10_with_grant_date": int((ge10 & granted.notna()).sum()),
        "ge10_fi_date_coverage_pct": _pct(int((ge10 & register["FIRequestDate"].notna()).sum()), int(ge10.sum())),
        "ge10_appeal_date_coverage_pct": _pct(int((ge10 & register["AppealSubmittedDate"].notna()).sum()), int(ge10.sum())),
        "ge10_eplanning_link_coverage_pct": _pct(
            int((ge10 & register["LinkAppDetails"].fillna("").astype(str).str.contains("eplanning|AppFileRefDetails", case=False, regex=True)).sum()),
            int(ge10.sum()),
        ),
    }

    # --- BCMS ---
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    report["bcms"] = {
        "total_rows": int(len(bcms)),
        "with_geo_pct": _pct(int(bcms["itm_easting"].notna().sum()), len(bcms)),
        "with_planning_reference_pct": _pct(int(bcms["planning_reference"].fillna("").astype(str).str.strip().ne("").sum()), len(bcms)),
        "with_completion_record_pct": _pct(int(bcms["completion_certificate_date_dt"].notna().sum()), len(bcms)),
        "with_eircode_pct": _pct(int(bcms["eircode"].fillna("").astype(str).str.strip().ne("").sum()), len(bcms)),
        "date_range": f"{bcms['commencement_date_dt'].min():%Y-%m-%d} .. {bcms['commencement_date_dt'].max():%Y-%m-%d}",
    }

    # --- PPR ---
    ppr = pd.read_parquet(settings.SILVER_DIR / "ppr_transactions_silver.parquet")
    report["ppr"] = {
        "total_rows": int(len(ppr)),
        "with_date_pct": _pct(int(ppr["sale_date_dt"].notna().sum()), len(ppr)),
        "with_price_pct": _pct(int(ppr["price_num"].notna().sum()), len(ppr)),
        "with_eircode_pct": _pct(int(ppr["eircode"].fillna("").astype(str).str.strip().ne("").sum()), len(ppr)),
        "not_full_market_price_pct": _pct(int(ppr["not_full_market_price_flag"].sum()), len(ppr)),
        "date_range": f"{ppr['sale_date_dt'].min():%Y-%m-%d} .. {ppr['sale_date_dt'].max():%Y-%m-%d}",
    }

    # --- cohort + linkage (extended mature cohort) ---
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv")
    bcms_links = pd.read_csv(settings.SILVER_DIR / "bcms_links_all_granted.csv")
    overlay_path = settings.SILVER_DIR / "audit" / "bcms_verdict_overlay.csv"
    if overlay_path.exists():
        overlay = pd.read_csv(overlay_path)
        if len(overlay):
            bcms_links = pd.concat([bcms_links, overlay.reindex(columns=bcms_links.columns)], ignore_index=True)
    ppr_links = pd.read_csv(settings.SILVER_DIR / "ppr_links_all_granted.csv")
    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv")
    n_pool = int(len(labels))
    cohort_mature = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    n_all_granted = int(len(cohort_mature))
    n_mature = int((cohort_mature["grant_year"].between(2016, 2022)).sum())
    bcms_confirmed = bcms_links[bcms_links["confidence_band"] == "confirmed"]
    ppr_confirmed = ppr_links[ppr_links["confidence_band"] == "confirmed"]
    mature_keys = set(cohort_mature[cohort_mature["grant_year"].between(2016, 2022)]["case_key"].astype(str))
    bcms_mature = len(set(bcms_confirmed["scheme_id"]) & mature_keys)
    report["cohort"] = {
        "all_granted_ge10": n_all_granted,
        "mature_granted_10plus_labels": n_pool,
        "bcms_confirmed_link_schemes": int(bcms_confirmed["scheme_id"].nunique()),
        "bcms_linkage_pct_all_granted": _pct(int(bcms_confirmed["scheme_id"].nunique()), n_all_granted),
        "bcms_linkage_pct_mature": _pct(bcms_mature, n_mature),
        "ppr_confirmed_link_schemes": int(ppr_confirmed["scheme_id"].nunique()),
        "ppr_linkage_pct_all_granted": _pct(int(ppr_confirmed["scheme_id"].nunique()), n_all_granted),
        "sales_eligible_pct": _pct(int(exit_labels["sales_eligible"].sum()), len(exit_labels)),
        "sales_linked_schemes": int((exit_labels["sales_linked"] > 0).sum()),
    }

    # --- refusal themes ---
    themes_path = settings.ROOT / "03_refusal" / "current" / "refusal_reasons_cases_master.csv"
    if themes_path.exists():
        themes = pd.read_csv(themes_path, low_memory=False)
        refused = themes[themes["decision"].fillna("").astype(str).str.contains("^REFUSE", case=False, regex=True)]
        tagged = refused[refused["case_top_primary_tag"].notna()]
        report["refusal_themes"] = {
            "total_rows": int(len(themes)),
            "refused_rows": int(len(refused)),
            "tagged_pct": _pct(int(len(tagged)), len(refused)),
        }

    # --- FI corpus (04_fi) ---
    fi_labels = labels["fi_item_count"].notna().sum() if "fi_item_count" in labels.columns else 0
    report["fi_corpus_04"] = {
        "pool_schemes_with_fi_items": int(fi_labels),
        "coverage_pct": _pct(int(fi_labels), n_pool),
        "note": "existing 04_fi extraction; quality remediation needed (ePlan boilerplate)",
    }

    # --- condition labels ---
    cond_path = settings.SILVER_DIR / "condition_family_labels_starter.csv"
    if cond_path.exists():
        cond = pd.read_csv(cond_path)
        report["grant_conditions"] = {"labelled_reports": int(len(cond)), "note": "starter regex set; corpus crawl pending retry"}
    else:
        report["grant_conditions"] = {"labelled_reports": 0}

    # --- engine readiness summary ---
    report["engine_readiness"] = {
        "a_planning_outcome": {"data": "register national (183k train, 35.7k holdout)", "coverage": "complete", "ready": True},
        "b_refusal_reasons": {"data": f"refused theme master ({report['refusal_themes']['refused_rows']} refused, {report['refusal_themes']['tagged_pct']}% tagged)", "coverage": "high", "ready": True},
        "c_grant_conditions": {"data": f"{report['grant_conditions']['labelled_reports']} starter + 166-scheme corpus runner (crawl pending)", "coverage": "low", "ready": False},
        "d_friction_fi": {"data": "1,095 pain labels; FI model holdout n=276 AUC 0.69", "coverage": "medium", "ready": True},
        "d_friction_appeal": {"data": "observed only (9.2% of pool); not modelled", "coverage": "low", "ready": False},
        "e_permission_timing": {"data": "3,186 10+ schemes with durations; GBM beats baselines", "coverage": "good", "ready": True},
        "f_activation": {"data": f"BCMS linkage mature {report['cohort']['bcms_linkage_pct_mature']}%; hazard did not beat KM; baselines only", "coverage": "medium", "ready": "baseline_only"},
        "f_exit": {"data": f"PPR linkage all-granted {report['cohort']['ppr_linkage_pct_all_granted']}%; labels where linked", "coverage": "low-medium", "ready": "baseline_only"},
        "g_cost_pressure": {"data": "description indicators + price benchmark; macro series NOT imported", "coverage": "partial", "ready": "evidence_only"},
        "h_comparables": {"data": "full register; longitudinal milestones on linked subset", "coverage": "good", "ready": True},
        "i_explanation": {"data": "v4 native contributions + GBM importances", "coverage": "complete", "ready": True},
        "j_facts_evidence": {"data": "register+BCMS+PPR structured; document corpus at scale MISSING", "coverage": "partial", "ready": "partial"},
        "k_unknowns": {"data": "generated from linkage/coverage flags", "coverage": "complete", "ready": True},
        "l_scenarios": {"data": "v4 re-scores; timing variants pending", "coverage": "good", "ready": True},
        "m_risk_register": {"data": "observed components", "coverage": "complete", "ready": True},
        "n_report": {"data": "markdown+PDF+overrides", "coverage": "complete", "ready": "prototype"},
    }
    return report


if __name__ == "__main__":
    stats = audit()
    out = settings.SILVER_DIR / "data_coverage_audit.json"
    out.write_text(json.dumps(stats, indent=2, default=str), encoding="utf-8")
    print(json.dumps(stats, indent=2, default=str))
