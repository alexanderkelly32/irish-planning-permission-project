"""devrisk CLI (brief section 19).

Commands are scriptable and idempotent; raw snapshots are immutable unless
explicitly replaced. This is the pilot CLI: cohort/link/label/report tasks run
locally without cloud infrastructure.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import settings


def _cmd_sources_validate(args: argparse.Namespace) -> int:
    import yaml

    data = yaml.safe_load(settings.SOURCES_YAML.read_text(encoding="utf-8"))
    sources = data.get("sources", {})
    problems = []
    for key in ("npad_register", "bcms", "ppr", "courts"):
        if key not in sources:
            problems.append(f"missing source entry: {key}")
    if problems:
        for problem in problems:
            print(f"ERROR: {problem}", file=sys.stderr)
        return 1
    print(f"sources.yaml valid: {len(sources)} sources")
    for key, entry in sources.items():
        print(f"  {key}: {entry.get('name', entry.get('purpose', '?'))[:60]}")
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    from .ingestion import bcms, npad, ppr

    if args.source == "bcms":
        result = bcms.run(settings.RAW_DIR, settings.BRONZE_DIR, settings.MANIFEST_DIR, force=args.force)
        print(f"bcms: {result['bronze']['rows']} rows -> {result['bronze']['bronze_path']}")
    elif args.source == "npad":
        result = npad.build_bronze(settings.REGISTER_FULL_PARQUET, settings.BRONZE_DIR, settings.MANIFEST_DIR)
        print(f"npad: {result['rows']} rows -> {result['bronze_path']}")
    elif args.source == "ppr":
        if args.csv:
            result = ppr.build_bronze_from_csv(Path(args.csv), settings.BRONZE_DIR, settings.MANIFEST_DIR)
            print(f"ppr: {result['rows']} rows -> {result['bronze_path']}")
        else:
            path = ppr.record_access_notes(settings.MANIFEST_DIR)
            print(f"ppr: no local CSV provided; access notes recorded -> {path}")
    else:
        print(f"unknown source: {args.source}", file=sys.stderr)
        return 1
    return 0


def _cmd_cohort(args: argparse.Namespace) -> int:
    import pandas as pd

    from . import cohort as cohort_mod
    from .cohort import annotate_pool, build_candidate_pool, export_audit_workbook, stratify_pilot

    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    pool = build_candidate_pool(
        register,
        min_units=args.min_units,
        grant_start=args.grant_start,
        grant_end=args.grant_end,
        censor_date=args.censor_date,
        min_followup_months=args.min_followup,
    )
    annotated = annotate_pool(pool)
    annotated.to_parquet(settings.SILVER_DIR / "pilot_candidates_pool.parquet", index=False)
    pilot = stratify_pilot(annotated, target=args.target)
    pilot.to_parquet(settings.SILVER_DIR / "pilot_candidates_100.parquet", index=False)
    export_audit_workbook(pilot, settings.SILVER_DIR / "pilot_100_audit.csv")

    import json

    print(json.dumps(cohort_mod.cohort_summary(annotated), indent=2, default=str))
    print(f"pool -> {settings.SILVER_DIR / 'pilot_candidates_pool.parquet'} ({len(annotated)} rows)")
    print(f"pilot -> {settings.SILVER_DIR / 'pilot_candidates_100.parquet'} ({len(pilot)} rows)")
    print(f"audit workbook -> {settings.SILVER_DIR / 'pilot_100_audit.csv'}")
    return 0


def _cmd_match(args: argparse.Namespace) -> int:
    import pandas as pd

    from .entity_resolution.scoring import (
        confidence_band,
        generate_bcms_candidates,
        score_bcms_candidate,
    )

    pilot = pd.read_parquet(settings.SILVER_DIR / "pilot_candidates_100.parquet")
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    rows = []
    for _, scheme_row in pilot.iterrows():
        scheme = {
            "scheme_id": scheme_row["case_key"],
            "units": scheme_row.get("NumResidentialUnits"),
            "address": scheme_row.get("DevelopmentAddress"),
            "county": _county_from_authority(scheme_row.get("PlanningAuthority")),
            "itm_easting": scheme_row.get("ITMEasting"),
            "itm_northing": scheme_row.get("ITMNorthing"),
            "application_reference": scheme_row.get("ApplicationNumber"),
        }
        candidates = generate_bcms_candidates(scheme, bcms, buffer_metres=args.buffer)
        for _, candidate in candidates.head(args.top_k).iterrows():
            features = score_bcms_candidate(scheme, candidate)
            band, reasons = confidence_band(features)
            rows.append({
                "scheme_id": scheme["scheme_id"],
                "bcms_source_row_id": candidate.get("source_row_id"),
                "bcms_address": candidate.get("address_full"),
                "planning_reference": candidate.get("planning_reference"),
                "commencement_date": candidate.get("commencement_date_dt"),
                "confidence_band": band,
                "reasons": "; ".join(reasons),
                **features,
            })
    links = pd.DataFrame(rows)
    links.to_csv(settings.SILVER_DIR / "bcms_link_candidates_pilot.csv", index=False)
    print(f"bcms candidates -> {settings.SILVER_DIR / 'bcms_link_candidates_pilot.csv'} ({len(links)} rows)")
    return 0


def _county_from_authority(authority: Any) -> str:
    text = str(authority or "").lower()
    for county in ("carlow", "cavan", "clare", "cork", "donegal", "dublin", "galway", "kerry",
                   "kildare", "kilkenny", "laois", "leitrim", "limerick", "longford", "louth",
                   "mayo", "meath", "monaghan", "offaly", "roscommon", "sligo", "tipperary",
                   "waterford", "westmeath", "wexford", "wicklow"):
        if county in text:
            return county
    return ""


def _cmd_labels(args: argparse.Namespace) -> int:
    import pandas as pd

    from .labels.activation import build_activation_labels

    if args.label != "activation":
        print(f"label builder not implemented: {args.label}", file=sys.stderr)
        return 1
    pilot = pd.read_parquet(settings.SILVER_DIR / "pilot_candidates_100.parquet")
    schemes = pd.DataFrame({
        "scheme_id": pilot["case_key"].astype(str),
        "final_grant_date": pilot["GrantDate"],
        "expected_units": pd.to_numeric(pilot["NumResidentialUnits"], errors="coerce"),
    })
    links = pd.read_csv(settings.SILVER_DIR / "bcms_link_candidates_pilot.csv") if (settings.SILVER_DIR / "bcms_link_candidates_pilot.csv").exists() else None
    events = pd.DataFrame(columns=["scheme_id", "commencement_date_dt", "corroboration_tier", "competing_event"])
    if links is not None and not links.empty:
        confirmed = links[links["confidence_band"] == "confirmed"]
        events = pd.DataFrame({
            "scheme_id": confirmed["scheme_id"],
            "bcms_event_id": confirmed["bcms_source_row_id"],
            "commencement_date_dt": confirmed["commencement_date"],
            "corroboration_tier": "A",
            "competing_event": None,
        })
        links = links.rename(columns={"bcms_source_row_id": "bcms_event_id"})
    labels = build_activation_labels(schemes, events, censor_date=args.censor_date, links=links)
    labels.to_csv(settings.SILVER_DIR / "activation_labels_pilot.csv", index=False)
    observed = int(labels["event_observed"].fillna(0).sum())
    print(f"activation labels -> {settings.SILVER_DIR / 'activation_labels_pilot.csv'} "
          f"({len(labels)} schemes, {observed} with confirmed commencement)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="devrisk", description="Irish Residential Development Risk Engine (pilot)")
    sub = parser.add_subparsers(dest="command", required=True)

    sources = sub.add_parser("sources")
    sources.add_argument("action", choices=["validate"])
    sources.set_defaults(func=_cmd_sources_validate)

    ingest = sub.add_parser("ingest")
    ingest.add_argument("source", choices=["npad", "bcms", "ppr"])
    ingest.add_argument("--csv", help="local PPR CSV to ingest (optional)")
    ingest.add_argument("--force", action="store_true", help="replace existing raw snapshot (new version)")
    ingest.set_defaults(func=_cmd_ingest)

    cohort = sub.add_parser("cohort")
    cohort.add_argument("action", choices=["build"])
    cohort.add_argument("--min-units", type=int, default=10)
    cohort.add_argument("--grant-start", default="2016-01-01")
    cohort.add_argument("--grant-end", default="2022-12-31")
    cohort.add_argument("--censor-date", default="2026-09-27")
    cohort.add_argument("--min-followup", type=int, default=36)
    cohort.add_argument("--target", type=int, default=100)
    cohort.set_defaults(func=_cmd_cohort)

    match = sub.add_parser("match")
    match.add_argument("source", choices=["bcms"])
    match.add_argument("--buffer", type=float, default=500.0)
    match.add_argument("--top-k", type=int, default=5)
    match.set_defaults(func=_cmd_match)

    labels = sub.add_parser("labels")
    labels.add_argument("label", choices=["activation", "friction"])
    labels.add_argument("--censor-date", default="2026-09-27")
    labels.set_defaults(func=_cmd_labels)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
