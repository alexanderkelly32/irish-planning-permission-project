"""Prototype underwriting report generator aligned to the product brief
(docs/Initial_Development_Risk_Report_Product_Brief.md).

Assembles the canonical modules (6.1-6.15) for one scheme from the frozen
planning model (read-only) and the devrisk pipeline. Every module carries an
availability state; unsupported modules abstain cleanly. All statements are
classified (observed fact / model estimate / analytical inference / unknown);
probabilities carry event, horizon, clock origin, snapshot, uncertainty,
model version and coverage. RESEARCH PROTOTYPE - not for decisions.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .. import settings
from ..models.planning_adapter import proposal_from_application, score_planning
from .condition_families import FAMILIES
from .report_spec import MODULES, Statement, module_availability, probability_statement

CENSOR_DATE = "2026-09-27"

COMPARABLE_COLUMNS = [
    "case_key", "PlanningAuthority", "DevelopmentDescription", "NumResidentialUnits",
    "ReceivedDate", "DecisionDate", "GrantDate", "ITMEasting", "ITMNorthing", "Decision",
]


def _county_name(authority: str) -> str:
    text = str(authority or "").lower()
    for county in ("carlow", "cavan", "clare", "cork", "donegal", "dublin", "galway", "kerry",
                   "kildare", "kilkenny", "laois", "leitrim", "limerick", "longford", "louth",
                   "mayo", "meath", "monaghan", "offaly", "roscommon", "sligo", "tipperary",
                   "waterford", "westmeath", "wexford", "wicklow"):
        if county in text:
            return county
    return ""


def _load_layers() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    timing = pd.read_csv(settings.SILVER_DIR / "permission_timing_predictions.csv")
    return register, labels, exit_labels, timing


def _timing_payload(t: pd.Series) -> dict[str, object]:
    return {
        "P20_days": round(float(t["strata_q20"]), 0),
        "P50_days": round(float(t["strata_q50"]), 0),
        "P80_days": round(float(t["strata_q80"]), 0),
        "clock_origin": "submission (ReceivedDate)",
        "event": "local-authority decision",
        "baseline": "authority-year-type strata quantiles (pinball-loss validated)",
    }


def _strata_quantiles_for(register: pd.DataFrame, row: pd.Series) -> dict[str, object] | None:
    """Recompute the timing model's strata quantiles for one scheme (train definition)."""
    pool = register.copy()
    pool["received_date_dt"] = pd.to_datetime(pool["ReceivedDate"], utc=True, errors="coerce")
    pool["decision_date_dt"] = pd.to_datetime(pool["DecisionDate"], utc=True, errors="coerce")
    pool["received_year"] = pool["received_date_dt"].dt.year
    pool = pool[pool["received_date_dt"].notna() & pool["decision_date_dt"].notna()]
    pool["planning_duration_days"] = (pool["decision_date_dt"] - pool["received_date_dt"]).dt.days.clip(lower=0)
    train = pool[pool["received_year"] < 2020].copy()
    description = train["DevelopmentDescription"].fillna("")
    train["type_house"] = description.str.contains(r"\b(?:house|houses|dwelling|dwellings)\b", case=False, regex=True) & ~description.str.contains("apartment", case=False)
    train["type_apartment"] = description.str.contains(r"\b(?:apartment|apartments|duplex)\b", case=False, regex=True)
    train["scheme_type"] = np.where(
        train["type_apartment"] & train["type_house"], "mixed",
        np.where(train["type_apartment"], "apartments", np.where(train["type_house"], "houses", "other")),
    )
    subject_type = train["scheme_type"].iloc[0] if not train.empty else "other"
    year = int(pd.Timestamp(row["ReceivedDate"]).year)
    strata = train.groupby(["PlanningAuthority", "received_year", "scheme_type"])["planning_duration_days"].quantile([0.2, 0.5, 0.8]).unstack()
    if strata.empty:
        return None
    strata.columns = ["q20", "q50", "q80"]
    values = None
    try:
        values = strata.loc[(row["PlanningAuthority"], year, subject_type)]
    except KeyError:
        try:
            values = strata.loc[(row["PlanningAuthority"], year)]
        except KeyError:
            return None
    overall = train["planning_duration_days"]
    return {
        "P20_days": round(float(values["q20"] if pd.notna(values["q20"]) else overall.quantile(0.2)), 0),
        "P50_days": round(float(values["q50"] if pd.notna(values["q50"]) else overall.quantile(0.5)), 0),
        "P80_days": round(float(values["q80"] if pd.notna(values["q80"]) else overall.quantile(0.8)), 0),
        "clock_origin": "submission (ReceivedDate)",
        "event": "local-authority decision",
        "baseline": "authority-year-type strata quantiles (pinball-loss validated)",
    }


def _comparable_candidates(register: pd.DataFrame, case_key: str, *, top_k: int = 10) -> pd.DataFrame:
    subject = register[register["case_key"] == case_key]
    if subject.empty:
        return pd.DataFrame()
    subject = subject.iloc[0]
    units = pd.to_numeric(pd.Series([subject["NumResidentialUnits"]]), errors="coerce").iloc[0]
    pool = register[
        (register["PlanningAuthority"] == subject["PlanningAuthority"])
        & (register["case_key"] != case_key)
    ].copy()
    pool["units"] = pd.to_numeric(pool["NumResidentialUnits"], errors="coerce")
    if not pd.isna(units):
        pool = pool[pool["units"].between(max(5, units * 0.5), units * 2)]
    pool = pool[pool["Decision"].notna()]
    received = pd.to_datetime(pool["ReceivedDate"], utc=True, errors="coerce")
    pool = pool[received.notna()]
    pool["received_year"] = received.dt.year
    subject_year = pd.Timestamp(subject["ReceivedDate"]).year
    pool = pool[pool["received_year"].between(subject_year - 3, subject_year + 1)]
    pool = pool.sort_values("received_year", ascending=False).head(top_k)

    # Longitudinal milestones for each comparable (BCMS/PPR-linked).
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    milestones = labels[
        ["case_key", "fi_requested", "appeal_submitted", "planning_duration_days",
         "activation_days", "completion_days", "level"]
    ].rename(columns={"level": "pain_level"})
    exit_milestones = exit_labels[
        ["case_key", "first_sale_date", "time_to_first_sale_from_grant_days",
         "time_to_first_sale_from_commencement_days", "sales_linked", "median_price"]
    ]
    pool = pool.merge(milestones, on="case_key", how="left")
    pool = pool.merge(exit_milestones, on="case_key", how="left")
    return pool[COMPARABLE_COLUMNS + [
        "fi_requested", "appeal_submitted", "planning_duration_days", "activation_days",
        "completion_days", "pain_level", "first_sale_date", "time_to_first_sale_from_grant_days",
        "sales_linked", "median_price",
    ]]


def _unknowns(scheme: dict[str, Any], label: pd.Series | None, exit_row: pd.Series | None) -> list[dict[str, Any]]:
    unknowns = []
    if label is None:
        return [{"unknown": "scheme not in research cohort", "forecast_affected": "all", "status": "absent"}]
    if not label.get("activation_linked"):
        unknowns.append({"unknown": "no confirmed BCMS commencement link", "forecast_affected": "activation/completion timing",
                         "status": "absent", "resolving_evidence": "BCMS notice with matching planning reference"})
    if not label.get("completion_linked"):
        unknowns.append({"unknown": "no completion certificate record", "forecast_affected": "completion timing",
                         "status": "absent", "resolving_evidence": "BCMS completion certificate"})
    if exit_row is None or exit_row.empty or not bool(exit_row.iloc[0].get("sales_linked")):
        unknowns.append({"unknown": "no confirmed PPR sales links", "forecast_affected": "exit timing and price benchmark",
                         "status": "absent", "resolving_evidence": "PPR transactions with estate/eircode match"})
    if pd.isna(label.get("planning_duration_days")):
        unknowns.append({"unknown": "planning duration", "forecast_affected": "permission timing", "status": "absent"})
    return unknowns


def build_report(case_key: str) -> dict[str, object]:
    register, labels, exit_labels, timing = _load_layers()
    subject = register[register["case_key"] == case_key]
    if subject.empty:
        raise KeyError(f"case not in register: {case_key}")
    row = subject.iloc[0]
    label = labels[labels["case_key"] == case_key]
    label_row = label.iloc[0] if not label.empty else None
    exit_row = exit_labels[exit_labels["case_key"] == case_key]
    timing_row = timing[timing["case_key"] == case_key]

    statements: list[dict[str, object]] = []
    probabilities: list[dict[str, object]] = []
    payload: dict[str, object] = {
        "as_of": CENSOR_DATE,
        "scheme_id": case_key,
        "authority": str(row["PlanningAuthority"]),
        "application_reference": str(row["ApplicationNumber"]),
    }

    # --- 6.1 identity snapshot (observed facts) ---
    statements.append(Statement(f"Application {row['ApplicationNumber']} to {row['PlanningAuthority']}.", "observed_fact", evidence="NPAD register").to_dict())
    statements.append(Statement(f"Proposed units: {row['NumResidentialUnits']}; received {row['ReceivedDate']}; granted {row['GrantDate']}.", "observed_fact", evidence="NPAD register").to_dict())
    statements.append(Statement(f"Description: {row['DevelopmentDescription']}", "observed_fact", evidence="NPAD register").to_dict())
    identity_confirmed = bool(label_row is not None and label_row.get("activation_linked"))
    payload["identity"] = {"confirmed": identity_confirmed, "bcms_linked": bool(label_row.get("activation_linked") if label_row is not None else False)}

    # --- 6.5 planning outcome (frozen model, read-only) ---
    proposal = proposal_from_application(
        authority=str(row["PlanningAuthority"]),
        description=str(row["DevelopmentDescription"] or ""),
        units=float(row["NumResidentialUnits"]) if pd.notna(row["NumResidentialUnits"]) else None,
        site_area_sqm=float(row["AreaofSite"]) if pd.notna(row.get("AreaofSite")) else None,
        floor_area_sqm=float(row["FloorArea"]) if pd.notna(row.get("FloorArea")) else None,
        itm_easting=float(row["ITMEasting"]) if pd.notna(row.get("ITMEasting")) else None,
        itm_northing=float(row["ITMNorthing"]) if pd.notna(row.get("ITMNorthing")) else None,
        submission_year=int(pd.Timestamp(row["ReceivedDate"]).year),
    )
    from .driver_explanation import explain as explain_v4

    v4_score = None
    v4_drivers = None
    try:
        v4_score = score_planning(proposal)
        v4_drivers = explain_v4(proposal)
        probabilities.append(probability_statement(
            "ultimate refusal", "not applicable", "submission", v4_score["refusal_probability"],
            snapshot="immediately before submission (frozen model interface)", uncertainty="calibration band per frozen artifact",
            model_version=str(v4_score["model_version"]), coverage="national residential; time-safe query",
        ))
        payload["planning_outcome"] = v4_score
        payload["drivers"] = v4_drivers
    except Exception as error:  # noqa: BLE001
        statements.append(Statement(f"Planning outcome unavailable: {type(error).__name__}", "unknown", evidence=None).to_dict())

    # --- 6.6 refusal reasons (conditional families + scheme transfer) ---
    try:
        from .refusal_reason_engine import refusal_reason_payload

        payload["refusal_reasons"] = refusal_reason_payload(
            description=str(row["DevelopmentDescription"] or ""),
            authority=str(row["PlanningAuthority"]),
            units=float(row["NumResidentialUnits"]) if pd.notna(row["NumResidentialUnits"]) else None,
        )
    except Exception as error:  # noqa: BLE001
        payload["refusal_reasons"] = {"note": f"refusal-reason engine unavailable: {type(error).__name__}"}

    # --- 6.8 friction: FI probability from persisted model ---
    payload["friction"] = {}
    try:
        import joblib

        from devrisk.models.pain_features import load_cohort
        from scripts.run_pain_components import add_history_features, build_matrix

        artifact = joblib.load(settings.GOLD_DIR / "fi_model_v1.joblib")
        cohort = add_history_features(load_cohort())
        matrix, _, cols = build_matrix(cohort, artifact["tfidf"])
        idx = cohort.index[cohort["case_key"] == case_key]
        if len(idx):
            scaled = artifact["scaler"].transform(matrix[idx[0]])
            raw = artifact["clf"].predict_proba(scaled)[0, 1]
            calibrated = float(np.clip(artifact["iso"].predict(np.array([raw]))[0], 1e-6, 1 - 1e-6))
            probabilities.append(probability_statement(
                "at least one formal FI request", "before decision", "submission", calibrated,
                snapshot="immediately before submission", uncertainty="holdout AUC 0.69 (0.62-0.76); 2022 drift documented",
                model_version="fi_requested_submission_time_v1", coverage="10+ unit granted schemes 2016-2022",
            ))
            payload["friction"]["fi_probability"] = calibrated
    except Exception as error:  # noqa: BLE001
        payload["friction"]["note"] = f"FI model unavailable: {type(error).__name__}"

    friction_observed = []
    if label_row is not None:
        if bool(label_row.get("fi_requested")):
            friction_observed.append("FI observed")
        if bool(label_row.get("appeal_submitted")):
            friction_observed.append("appeal observed")
        if pd.notna(label_row.get("planning_duration_days")):
            friction_observed.append(f"decision took {int(label_row['planning_duration_days'])} days")
        if pd.notna(label_row.get("fi_item_count")):
            friction_observed.append(f"{int(label_row['fi_item_count'])} FI items extracted (04_fi corpus)")
    jr_path = settings.SILVER_DIR / "jr_events.csv"
    if jr_path.exists():
        jr = pd.read_csv(jr_path)
        jr_rows = jr[jr["case_key"] == case_key]
        if len(jr_rows):
            refs = jr_rows["jr_reference"].dropna().astype(str).unique()[:2]
            conclusions = jr_rows["jr_conclusion"].dropna().astype(str).unique()[:1]
            friction_observed.append(f"JR positive evidence: {', '.join(refs)}"
                                     + (f" (conclusion: {conclusions[0]})" if len(conclusions) else ""))
    tic_path = settings.SILVER_DIR / "scheme_tic_verified.csv"
    if tic_path.exists():
        tic = pd.read_csv(tic_path)
        tic_row = tic[tic["scheme_id"] == case_key]
        if len(tic_row):
            friction_observed.append(f"taken in charge (verified): {tic_row.iloc[0]['tic_estate_name']}")
    payload["friction_observed"] = friction_observed

    # --- 6.9 milestones: GBM permission timing + activation/completion baselines ---
    payload["permission_timing"] = {}
    try:
        from .timing_engine import explain_timing, score_timing

        received_ts = pd.Timestamp(row["ReceivedDate"])
        if received_ts.tzinfo is None:
            received_ts = received_ts.tz_localize("UTC")
        timing_score = score_timing(
            authority=str(row["PlanningAuthority"]),
            units=float(row["NumResidentialUnits"]) if pd.notna(row["NumResidentialUnits"]) else None,
            description=str(row["DevelopmentDescription"] or ""),
            received_date=received_ts,
        )
        payload["permission_timing"] = timing_score
        payload["timing_drivers"] = explain_timing(
            authority=str(row["PlanningAuthority"]),
            units=float(row["NumResidentialUnits"]) if pd.notna(row["NumResidentialUnits"]) else None,
            description=str(row["DevelopmentDescription"] or ""),
            received_date=received_ts,
        )
    except Exception as error:  # noqa: BLE001
        strata_t = _strata_quantiles_for(register, row)
        if strata_t:
            payload["permission_timing"] = strata_t
        payload["timing_drivers"] = []
        payload["permission_timing"]["note"] = f"GBM unavailable ({type(error).__name__}); strata fallback used"
    milestones_note = (
        "Activation/completion forecasts are cohort baselines only (hazard model did not beat KM strata). "
        "Commencement baseline now era-adaptive: rolling 24-month median of prior grants (MAE ~360d, at the "
        "intrinsic floor; shrunk authority variant ~347d). Completion median ~477 days once commenced."
    )
    statements.append(Statement(milestones_note, "model_estimate", evidence="activation_survival_report.json").to_dict())

    # --- 6.7 grant conditions: family prior frequencies ---
    cond_path = settings.SILVER_DIR / "condition_family_labels_corpus.csv"
    if cond_path.exists():
        cond = pd.read_csv(cond_path)
        payload["grant_conditions"] = {
            "family_frequencies": {
                family: float(cond[f"condition_{family}"].mean()) for family in FAMILIES if f"condition_{family}" in cond.columns
            },
            "evidence": f"regex labels on {len(cond)} granted planner reports (local corpus)",
        }
    else:
        cond_path = settings.SILVER_DIR / "condition_family_labels_starter.csv"
        if cond_path.exists():
            cond = pd.read_csv(cond_path)
            payload["grant_conditions"] = {
                "family_frequencies": {
                    family: float(cond[f"condition_{family}"].mean()) for family in FAMILIES if f"condition_{family}" in cond.columns
                },
                "evidence": "starter regex labels on 17 verified planner reports; audited corpus pending",
            }
        else:
            payload["grant_conditions"] = None

    # --- 6.11 comparables ---
    comparables = _comparable_candidates(register, case_key)
    payload["comparables"] = comparables.to_dict(orient="records")

    # --- 6.12/6.13 unknowns and next-best evidence ---
    unknowns = _unknowns(payload, label_row, exit_row)
    payload["unknowns"] = unknowns
    payload["next_best_evidence"] = [
        {"unknown": item["unknown"], "forecast_affected": item["forecast_affected"],
         "resolving_evidence": item.get("resolving_evidence", ""),
         "public_or_customer": "public" if "BCMS" in str(item.get("resolving_evidence", "")) or "PPR" in str(item.get("resolving_evidence", "")) else "unknown"}
        for item in unknowns
    ]

    # --- 6.10 risk register rows from observed components ---
    register_rows = []
    if label_row is not None:
        if bool(label_row.get("appeal_submitted")):
            register_rows.append({"risk": "Applicant appeal observed", "category": "Planning",
                                  "evidence_class": "observed_fact", "status": "present",
                                  "evidence": "register appeal fields"})
        if bool(label_row.get("fi_requested")):
            register_rows.append({"risk": "FI requested", "category": "Planning",
                                  "evidence_class": "observed_fact", "status": "present",
                                  "evidence": "register FI dates"})
        if bool(label_row.get("slow_activation_24m")):
            register_rows.append({"risk": "Slow activation (>=24m)", "category": "Delivery",
                                  "evidence_class": "observed_fact", "status": "present",
                                  "evidence": "BCMS commencement date"})
        if bool(label_row.get("slow_completion_36m")):
            register_rows.append({"risk": "Slow completion (>=36m)", "category": "Delivery",
                                  "evidence_class": "observed_fact", "status": "present",
                                  "evidence": "BCMS completion certificate"})
    payload["risk_register"] = register_rows

    # --- 6.15 cost pressure indicators (description-derived, inference class) ---
    cost_flags = []
    description_lower = str(row["DevelopmentDescription"] or "").lower()
    for phrase, flag in (
        ("basement", "basement_works"), ("demolition", "demolition"),
        ("protected structure", "protected_structure"), ("flood", "flood_measures"),
        ("wastewater", "wastewater_dependency"), ("archaeolog", "archaeology"),
    ):
        if phrase in description_lower:
            cost_flags.append(flag)
    payload["cost_pressure"] = {"indicators": cost_flags, "note": "description-derived indicators only; extraction pipeline pending"}

    # --- market context: TimesFM-2.5 county forecasts (model estimates) ---
    try:
        macro_path = settings.SILVER_DIR / "macro_forecasts.parquet"
        if macro_path.exists():
            macro = pd.read_parquet(macro_path)
            county = _county_name(str(row["PlanningAuthority"]))
            context = macro[macro["county"] == county].copy()
            if context.empty:
                context = macro[macro["county"] == "dublin"].copy()
            volume = context[context["target"] == "ppr_volume"].sort_values("horizon_months")
            price = context[context["target"] == "ppr_median_price"].sort_values("horizon_months")
            payload["market_context"] = {
                "county": county,
                "ppr_volume_next_12m_mean": round(float(volume["forecast"].mean()), 1) if len(volume) else None,
                "ppr_volume_next_12m_forecast": volume["forecast"].round(0).tolist() if len(volume) else [],
                "ppr_price_next_12m_mean": round(float(price["forecast"].mean()), 0) if len(price) else None,
                "model_version": "timesfm-2.5-200m",
                "licence": "Apache-2.0",
                "backtest": "county volumes MAE 29.5 vs 34.8 seasonal; prices EUR 19.2k vs 28.4k (12-month holdout)",
                "note": "market-context forecasts; not scheme-specific",
            }
    except Exception as error:  # noqa: BLE001
        payload["market_context"] = {"note": f"unavailable: {type(error).__name__}"}

    # --- 6.14 scenarios: supported-variable re-scores (labelled sensitivity) ---
    scenarios = []
    try:
        if v4_score is not None:
            base_units = float(row["NumResidentialUnits"]) if pd.notna(row["NumResidentialUnits"]) else None
            base_area = float(row["AreaofSite"]) if pd.notna(row.get("AreaofSite")) else None
            variants = []
            if base_units:
                variants.append((f"units {int(base_units)} -> {int(round(base_units * 0.8))}", {"units": round(base_units * 0.8)}))
                variants.append((f"units {int(base_units)} -> {int(round(base_units * 1.25))}", {"units": round(base_units * 1.25)}))
            if base_area:
                variants.append((f"site area -20%", {"site_area_sqm": round(base_area * 0.8)}))
                variants.append((f"site area +25%", {"site_area_sqm": round(base_area * 1.25)}))
            for label, changes in variants:
                variant = dict(proposal)
                variant.update(changes)
                variant_score = score_planning(variant)
                scenarios.append({
                    "label": label,
                    "changes": changes,
                    "refusal_probability": variant_score["refusal_probability"],
                    "delta_pp": round((variant_score["refusal_probability"] - v4_score["refusal_probability"]) * 100, 1),
                    "sensitivity_label": "one-at-a-time sensitivity; not a causal claim",
                })
        payload["scenarios"] = {
            "supported_variables": ["units", "site_area_sqm", "floor_area_sqm", "description wording"],
            "runs": scenarios,
            "note": "report-level base-case re-scores of the frozen planning model; timing variants follow",
        }
    except Exception as error:  # noqa: BLE001
        payload["scenarios"] = {"supported_variables": [], "runs": [], "note": f"scenarios unavailable: {type(error).__name__}"}

    payload["statements"] = statements
    payload["probabilities"] = probabilities
    payload["modules"] = module_availability(payload, {"identity_confirmed": identity_confirmed})
    payload["module_names"] = MODULES

    structure_errors = __import__("devrisk.reporting.report_spec", fromlist=["validate_report_structure"]).validate_report_structure(
        {**payload, "modules": payload["modules"]}
    )
    payload["qa_errors"] = structure_errors
    return payload


def render_markdown(payload: dict[str, object]) -> str:
    lines = [f"# Initial Development Risk Report - {payload['scheme_id']}", ""]
    lines.append("> **RESEARCH PROTOTYPE - NOT FOR LENDING, INVESTMENT OR PLANNING DECISIONS.** "
                 f"as_of {payload['as_of']}. Unsupported modules abstain.")
    lines.append("")
    lines.append("## 6.1 Scheme identity and analysis snapshot")
    for statement in payload["statements"]:
        if statement["classification"] == "observed_fact":
            lines.append(f"- {statement['text']}")
    lines.append("")
    lines.append("## 6.3 Analytical summary")
    for prob in payload["probabilities"]:
        pct = float(prob["estimate"]) * 100
        lines.append(f"- P({prob['event']} | {prob['clock_origin']}, horizon {prob['horizon']}): **{pct:.1f}%** "
                     f"(model {prob['model_version']}; {prob['uncertainty']})")
    lines.append("")
    lines.append("## 6.4 Where did this number come from?")
    if payload.get("drivers"):
        drivers = payload["drivers"]
        lines.append(f"- Native logit {drivers['native_logit']}, raw ranking {drivers['raw_ranking_score']}, "
                     f"calibrated {drivers['calibrated_probability'] * 100:.1f}% (isotonic).")
        lines.append("- Group contributions (log-odds):")
        for group, info in sorted(drivers["group_contributions"].items(), key=lambda kv: -kv[1]["net_contribution_log_odds"]):
            lines.append(f"  - {info['label']}: {info['net_contribution_log_odds']:+.4f} ({info['n_features']} features)")
        lines.append("- Top raising text features:")
        for entry in [r for r in drivers["top_raising"] if r["group"] == "description_text"][:5]:
            lines.append(f"  - '{entry['token']}': {entry['contribution_log_odds']:+.4f}")
        lines.append("- Top lowering text features:")
        for entry in [r for r in drivers["top_lowering"] if r["group"] == "description_text"][:5]:
            lines.append(f"  - '{entry['token']}': {entry['contribution_log_odds']:+.4f}")
        lines.append("- Counterfactuals (one-at-a-time, labelled sensitivity):")
        for cf in drivers["counterfactuals"][:8]:
            lines.append(f"  - without {cf['label']}: raw score moves {cf['raw_score_delta_pp']:+.1f}pp")
    else:
        lines.append("- Unavailable for this scheme.")
    if payload.get("timing_drivers"):
        lines.append("- Timing model (GBM P50) top drivers:")
        for driver in payload["timing_drivers"][:6]:
            lines.append(f"  - {driver['feature']}: importance {driver['importance']}, subject {driver['subject_value']}")
    lines.append("")
    lines.append("## 6.6 Likely refusal reasons (conditional on refusal)")
    if payload.get("refusal_reasons"):
        rr = payload["refusal_reasons"]
        priors = rr.get("family_priors", {})
        lines.append(f"- Refused GE10 cohort: {priors.get('n_refused')} cases, {priors.get('n_tagged')} tagged "
                     f"(coverage {priors.get('tag_coverage', 0) * 100:.0f}%).")
        lines.append("- Conditional family frequencies (marginal, not exclusive):")
        for family, freq in sorted(priors.get("frequencies", {}).items(), key=lambda kv: -kv[1])[:8]:
            lines.append(f"  - {priors.get('labels', {}).get(family, family)}: {freq * 100:.0f}%")
        lines.append(f"- {priors.get('overlap_warning', '')}")
        transfer = rr.get("scheme_transfer", {})
        if transfer.get("themes"):
            lines.append(f"- Scheme-specific transfer ({transfer['matched_n']} token-matching refused comparables):")
            for theme in transfer["themes"]:
                lines.append(f"  - {theme['label']}: share {theme['share'] * 100:.0f}%")
            lines.append(f"- {transfer.get('transfer_accuracy_note', '')}")
    else:
        lines.append("- Unavailable.")
    lines.append("")
    lines.append("## 6.7 Likely grant conditions (starter priors)")
    if payload.get("grant_conditions"):
        freqs = payload["grant_conditions"]["family_frequencies"]
        for family, freq in sorted(freqs.items(), key=lambda kv: -kv[1]):
            lines.append(f"- {family}: {freq * 100:.0f}% of starter-labelled granted reports")
        lines.append(f"- ({payload['grant_conditions']['evidence']})")
    else:
        lines.append("- Unavailable: audited condition corpus pending.")
    lines.append("")
    lines.append("## 6.8 Planning friction")
    if payload.get("friction", {}).get("fi_probability") is not None:
        lines.append(f"- P(FI): **{payload['friction']['fi_probability'] * 100:.0f}%** (fi_requested_submission_time_v1)")
    else:
        lines.append("- FI probability unavailable.")
    if payload.get("friction_observed"):
        lines.append(f"- Observed: {'; '.join(payload['friction_observed'])}")
    lines.append("")
    lines.append("## 6.9 Milestone forecast")
    if payload.get("permission_timing"):
        t = payload["permission_timing"]
        if "P20_days" in t:
            lines.append(f"- Decision timing from {t.get('clock_origin', 'submission')}: "
                         f"P20 {t['P20_days']:.0f} / P50 {t['P50_days']:.0f} / P80 {t['P80_days']:.0f} days "
                         f"(model {t.get('model_version', 'timing_strata_v1')}).")
        if t.get("horizon_probabilities"):
            lines.append(f"- P(decision > 6m): **{t['horizon_probabilities'].get('183', 0) * 100:.0f}%** · "
                         f"P(decision > 12m): **{t['horizon_probabilities'].get('365', 0) * 100:.0f}%** "
                         "(logistic horizon models; holdout AUC 0.75 / 0.72).")
    lines.append("- Activation/completion: cohort baselines only (research).")
    lines.append("")
    lines.append("## 6.14 Scenario comparison (labelled sensitivity)")
    runs = payload.get("scenarios", {}).get("runs", [])
    for run in runs:
        lines.append(f"- {run['label']}: refusal {run['refusal_probability'] * 100:.1f}% "
                     f"({run['delta_pp']:+.1f}pp vs base) - {run['sensitivity_label']}")
    if not runs:
        lines.append("- No scenario runs for this scheme.")
    lines.append("")
    lines.append("## 6.10 Risk register")
    for row in payload["risk_register"]:
        lines.append(f"- [{row['evidence_class']}] {row['risk']} ({row['category']}) - {row['evidence']}")
    if not payload["risk_register"]:
        lines.append("- No observed severe components.")
    lines.append("")
    lines.append("## 6.11 Comparables (top 10, longitudinal milestones)")
    for comp in payload["comparables"][:10]:
        lines.append(f"- {comp['case_key']}: {str(comp['DevelopmentDescription'])[:80]} | {comp['NumResidentialUnits']}u | {comp['Decision']}")
        extra = []
        if pd.notna(comp.get("planning_duration_days")):
            extra.append(f"decision {int(comp['planning_duration_days'])}d")
        if pd.notna(comp.get("activation_days")):
            extra.append(f"commencement {int(comp['activation_days'])}d")
        if pd.notna(comp.get("completion_days")):
            extra.append(f"completion {int(comp['completion_days'])}d")
        if pd.notna(comp.get("first_sale_date")):
            extra.append(f"first sale {str(comp['first_sale_date'])[:10]}")
        if extra:
            lines.append(f"    milestones: {'; '.join(extra)}")
    lines.append("")
    lines.append("## 6.12 Material unknowns / 6.13 Next-best evidence")
    for item in payload["unknowns"]:
        lines.append(f"- Unknown: {item['unknown']} (affects {item['forecast_affected']}) "
                     f"[resolving: {item.get('resolving_evidence') or 'n/a'}]")
    lines.append("")
    lines.append("## 6.15 Cost-pressure indicators")
    lines.append(f"- Description-derived: {payload['cost_pressure']['indicators'] or 'none'} "
                 f"({payload['cost_pressure']['note']})")
    lines.append("")
    if payload.get("market_context"):
        mc = payload["market_context"]
        if mc.get("ppr_volume_next_12m_mean"):
            lines.append("## Market context (TimesFM-2.5 forecasts, Apache-2.0)")
            lines.append(f"- {mc['county']}: next-12-month PPR sales volume mean {mc['ppr_volume_next_12m_mean']:.0f}/month; "
                         f"median price {mc['ppr_price_next_12m_mean']:.0f} EUR.")
            lines.append(f"- Backtest context: {mc['backtest']}. {mc['note']}.")
            lines.append("")
    lines.append("## Module availability")
    for key, state in payload["modules"].items():
        lines.append(f"- {key}: {state}")
    lines.append("")
    lines.append(f"QA errors: {payload['qa_errors'] or 'none'}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    case_key = sys.argv[1] if len(sys.argv) > 1 else "Carlow County Council__19263"
    print(render_markdown(build_report(case_key)))
