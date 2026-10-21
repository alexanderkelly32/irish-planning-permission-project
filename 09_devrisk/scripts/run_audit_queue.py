"""Runner: BCMS link adjudication queue for human review (Gate 2 support).

Exports the probable + nearest ambiguous BCMS link candidates for the pilot
with all match evidence and an empty verdict column. The pain model already
trains on conservative confirmed links (exact planning-reference matches);
this audit measures precision/coverage and checks the confirmed rule.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

if __name__ == "__main__":
    links = pd.read_csv(settings.SILVER_DIR / "bcms_link_candidates_pilot.csv")
    pilot = pd.read_parquet(settings.SILVER_DIR / "pilot_candidates_100.parquet")
    meta = pilot.set_index("case_key")[["PlanningAuthority", "DevelopmentAddress", "NumResidentialUnits"]]

    probable = links[links["confidence_band"] == "probable"].copy()
    ambiguous = links[links["confidence_band"] == "ambiguous"].copy()
    ambiguous = ambiguous.sort_values("distance_metres").head(30)
    queue = pd.concat([probable, ambiguous], ignore_index=True).drop_duplicates(
        subset=["scheme_id", "bcms_source_row_id"]
    )

    queue["scheme_authority"] = queue["scheme_id"].map(meta["PlanningAuthority"])
    queue["scheme_address"] = queue["scheme_id"].map(meta["DevelopmentAddress"])
    queue["scheme_units"] = queue["scheme_id"].map(meta["NumResidentialUnits"])
    queue["verdict"] = ""
    queue["verdict_note"] = ""

    columns = [
        "scheme_id", "scheme_authority", "scheme_address", "scheme_units",
        "bcms_address", "planning_reference", "commencement_date",
        "confidence_band", "distance_metres", "address_token_similarity_full",
        "uncommon_place_agreement", "unit_abs_diff", "reasons",
        "verdict", "verdict_note",
    ]
    out = settings.SILVER_DIR / "audit_queue_bcms_links.csv"
    queue[columns].to_csv(out, index=False)
    print(f"audit queue -> {out} ({len(queue)} rows: {len(probable)} probable + {len(ambiguous)} ambiguous)")
    print("verdict options: confirmed | probable | rejected  (fill 'verdict_note' with evidence for rejects)")

    ppr_links_path = settings.SILVER_DIR / "ppr_links_pool.csv"
    if ppr_links_path.exists():
        ppr_links = pd.read_csv(ppr_links_path)
        ppr_queue = ppr_links[ppr_links["confidence_band"].isin(["confirmed", "probable"])].copy()
        if len(ppr_queue) > 60:
            ppr_queue = ppr_queue.sample(n=60, random_state=7)
        ppr_queue["verdict"] = ""
        ppr_queue["verdict_note"] = ""
        ppr_out = settings.SILVER_DIR / "audit_queue_ppr_links.csv"
        ppr_queue[
            ["scheme_id", "ppr_source_row_id", "confidence_band", "reasons",
             "address_norm", "sale_date", "price", "eircode_match",
             "uncommon_token_overlap", "address_token_similarity",
             "sale_after_commencement", "verdict", "verdict_note"]
        ].to_csv(ppr_out, index=False)
        print(f"ppr audit queue -> {ppr_out} ({len(ppr_queue)} rows sampled from {len(ppr_links)} candidates)")
