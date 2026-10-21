"""Canonical data model (brief section 9).

Plain dataclasses with dict round-trips; no ORM. Names map to the brief's
concepts: scheme, planning_application, scheme_application_link,
planning_event, document, document_extraction, bcms_event, scheme_bcms_link,
ppr_transaction, scheme_ppr_link, entity/scheme_party, market_context,
label_snapshot, feature_snapshot. Only the concepts needed for the pilot are
materialised now; the rest are recorded as schema stubs so nothing collapses.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


def new_uuid() -> str:
    return str(uuid.uuid4())


@dataclass
class Scheme:
    scheme_id: str
    canonical_name: str
    local_authority: str
    expected_units: int | None
    scheme_type: str  # houses/apartments/mixed/other
    tenure_or_exit_type: str = "unknown"  # build_to_sell/build_to_rent/social/mixed/unknown
    parent_scheme_id: str | None = None
    phase_label: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    itm_easting: float | None = None
    itm_northing: float | None = None
    address_components: dict[str, Any] = field(default_factory=dict)
    identity_status: str = "proposed"  # proposed/confirmed/probable/ambiguous/rejected
    manual_review_status: str = "pending"
    created_at: str = ""
    updated_at: str = ""


@dataclass
class PlanningApplication:
    application_id: str
    scheme_id: str | None
    authority: str
    application_reference: str
    case_key: str
    application_type: str = ""
    description_raw: str = ""
    description_normalized: str = ""
    proposed_units: int | None = None
    granted_units: int | None = None
    submission_date: str = ""
    decision_date: str = ""
    final_grant_date: str = ""
    decision: str = ""
    itm_easting: float | None = None
    itm_northing: float | None = None
    address: str = ""
    applicant_raw: str = ""
    source_row_ref: str = ""
    available_at: str = ""


@dataclass
class SchemeApplicationLink:
    link_id: str
    scheme_id: str
    application_id: str
    relation_type: str  # base/phase/amendment/extension/substitute/appeal/enabling_works/uncertain
    match_method: str
    match_score: float | None
    confidence_band: str  # confirmed/probable/ambiguous/rejected
    evidence: dict[str, Any] = field(default_factory=dict)
    reviewer: str = ""
    reviewed_at: str = ""


@dataclass
class PlanningEvent:
    event_id: str
    scheme_id: str | None
    application_id: str | None
    event_type: str
    event_date: str = ""
    event_date_end: str = ""
    values: dict[str, Any] = field(default_factory=dict)  # e.g. units before/after
    evidence: dict[str, Any] = field(default_factory=dict)
    extraction_method: str = ""
    confidence: float | None = None
    available_at: str = ""


@dataclass
class BcmsEvent:
    bcms_event_id: str
    source_row_id: str
    event_type: str  # commencement/seven_day_notice/completion/other
    authority: str = ""
    address: str = ""
    dwellings: int | None = None
    units: int | None = None
    received_date: str = ""
    commencement_date: str = ""
    submission_date: str = ""
    description_raw: str = ""
    source_snapshot: str = ""
    available_at: str = ""


@dataclass
class SchemeBcmsLink:
    link_id: str
    scheme_id: str
    bcms_event_id: str
    match_score: float | None
    confidence_band: str  # confirmed/probable/ambiguous/rejected
    relation_phase: str = ""
    features: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    reviewer: str = ""
    reviewed_at: str = ""


@dataclass
class PprTransaction:
    ppr_transaction_id: str
    source_row_id: str
    sale_date: str = ""
    address_raw: str = ""
    address_normalized: str = ""
    price: float | None = None
    not_full_market_price: bool = False
    vat_exclusive: bool = False
    property_description: str = ""
    available_at: str = ""


@dataclass
class SchemePprLink:
    link_id: str
    scheme_id: str
    ppr_transaction_id: str
    match_score: float | None
    confidence_band: str
    phase: str = ""
    exclusion_reason: str = ""  # bulk/ambiguous/outside_window/tenure_ineligible
    reviewer: str = ""
    reviewed_at: str = ""


@dataclass
class LabelSnapshot:
    scheme_id: str
    label_name: str
    value: Any
    origin_milestone: str
    observation_window_end: str
    censored: bool
    censor_reason: str = ""
    eligible: bool = True
    label_confidence: float | None = None
    label_rule_version: str = ""
    provenance_bundle: dict[str, Any] = field(default_factory=dict)


@dataclass
class FeatureSnapshot:
    scheme_id: str
    snapshot_type: str  # submission/pre_decision/final_grant/commencement
    snapshot_at: str
    feature_version: str
    values: dict[str, Any] = field(default_factory=dict)
    availability_audit: dict[str, Any] = field(default_factory=dict)
    coverage_indicators: dict[str, Any] = field(default_factory=dict)


def to_dict(instance: Any) -> dict[str, Any]:
    return asdict(instance)
