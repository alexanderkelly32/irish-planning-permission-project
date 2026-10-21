"""Runner: ten-scheme vertical slice export (brief section 26.8).

Takes the first 10 pilot schemes with BCMS candidates, joins the confirmed/
probable link candidates and activation labels, and exports a provenance-rich
timeline workbook for human adjudication. Identity adjudication is a human
step; this export supplies the evidence.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

if __name__ == "__main__":
    pilot = pd.read_parquet(settings.SILVER_DIR / "pilot_candidates_100.parquet")
    links = pd.read_csv(settings.SILVER_DIR / "bcms_link_candidates_pilot.csv")
    labels = pd.read_csv(settings.SILVER_DIR / "activation_labels_pilot.csv")

    scheme_ids = links[links["confidence_band"].isin(["confirmed", "probable"])]["scheme_id"].unique()[:10]
    slice_rows = []
    for scheme_id in scheme_ids:
        scheme = pilot[pilot["case_key"] == scheme_id].iloc[0]
        candidates = links[(links["scheme_id"] == scheme_id) & links["confidence_band"].isin(["confirmed", "probable"])].head(3)
        label = labels[labels["scheme_id"] == scheme_id].iloc[0]
        for _, candidate in candidates.iterrows():
            slice_rows.append({
                "scheme_id": scheme_id,
                "authority": scheme["PlanningAuthority"],
                "application_number": scheme["ApplicationNumber"],
                "address": scheme["DevelopmentAddress"],
                "units": scheme["NumResidentialUnits"],
                "grant_date": scheme["GrantDate"],
                "candidate_band": candidate["confidence_band"],
                "candidate_reasons": candidate["reasons"],
                "bcms_address": candidate["bcms_address"],
                "distance_metres": candidate["distance_metres"],
                "unit_abs_diff": candidate["unit_abs_diff"],
                "bcms_planning_reference": candidate["planning_reference"],
                "commencement_date": candidate["commencement_date"],
                "label_event_observed": label["event_observed"],
                "label_duration_days": label["duration_days"],
                "label_corroboration_tier": label["corroboration_tier"],
                "reviewer": "",
                "review_decision": "",
                "review_note": "",
            })
    frame = pd.DataFrame(slice_rows)
    out = settings.SILVER_DIR / "vertical_slice_10_review.csv"
    frame.to_csv(out, index=False)
    print(f"vertical slice -> {out} ({len(frame)} candidate rows across {len(scheme_ids)} schemes)")
