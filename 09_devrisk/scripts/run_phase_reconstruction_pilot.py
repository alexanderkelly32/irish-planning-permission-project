"""Runner: phase reconstruction pilot for the 25 wrong-phase schemes.

For each scheme flagged wrong_phase in PACK_23: reconstruct per-phase
milestones from BCMS notices (commencement, CCC, units per phase) and
compare against the scheme-level labels that drove the residuals. Outputs
a reconstruction table showing whether phase-level CCC explains the
residual (i.e., first sale belongs to an early phase whose CCC is not
the scheme-level minimum used by the label).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

if __name__ == "__main__":
    schemes = pd.read_csv(settings.SILVER_DIR / "audit" / "wrong_phase_schemes.csv")
    scheme_keys = set(schemes["case_key"].astype(str))
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    links = pd.read_csv(settings.SILVER_DIR / "bcms_links_all_granted.csv")
    overlay = settings.SILVER_DIR / "audit" / "bcms_verdict_overlay.csv"
    if overlay.exists():
        links = pd.concat([links, pd.read_csv(overlay).reindex(columns=links.columns)], ignore_index=True)
    confirmed = links[links["confidence_band"] == "confirmed"]
    events = confirmed.merge(bcms, on="bcms_event_id", how="inner")

    rows = []
    for scheme_id in sorted(scheme_keys):
        group = events[events["scheme_id"].astype(str) == scheme_id]
        if group.empty:
            rows.append({"scheme_id": scheme_id, "reconstruction": "no_bcms_events"})
            continue
        comm = pd.to_datetime(group["commencement_date_dt"], utc=True, errors="coerce")
        ccc = pd.to_datetime(group["completion_certificate_date_dt"], utc=True, errors="coerce")
        phases = pd.to_numeric(group["phase_number"], errors="coerce")
        units = pd.to_numeric(group["dwellings_phase"], errors="coerce")
        phase_rows = []
        for phase in sorted(phases.dropna().unique()):
            mask = phases == phase
            phase_rows.append({
                "phase": int(phase),
                "units": float(units[mask].sum()),
                "commencement": str(comm[mask].min().date()) if comm[mask].notna().any() else None,
                "first_ccc": str(ccc[mask].min().date()) if ccc[mask].notna().any() else None,
                "ccc_count": int(ccc[mask].notna().sum()),
            })
        first_comm = comm.min()
        first_ccc = ccc.min()
        span = (first_ccc - first_comm).days if pd.notna(first_comm) and pd.notna(first_ccc) else None
        rows.append({
            "scheme_id": scheme_id,
            "reconstruction": "ok",
            "n_phases": int(phases.nunique()),
            "first_commencement": str(first_comm.date()) if pd.notna(first_comm) else None,
            "first_ccc": str(first_ccc.date()) if pd.notna(first_ccc) else None,
            "scheme_level_span_days": span,
            "phase_table": json.dumps(phase_rows),
        })

    out = pd.DataFrame(rows)
    out.to_csv(settings.SILVER_DIR / "phase_reconstruction_pilot.csv", index=False)
    summary = {
        "schemes": int(len(out)),
        "with_bcms_events": int((out["reconstruction"] == "ok").sum()),
        "median_phases": float(out["n_phases"].median()) if out["n_phases"].notna().any() else None,
        "median_scheme_span_days": float(out["scheme_level_span_days"].median()) if out["scheme_level_span_days"].notna().any() else None,
        "out": str(settings.SILVER_DIR / "phase_reconstruction_pilot.csv"),
    }
    (settings.SILVER_DIR / "phase_reconstruction_pilot_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
