"""Runner: kitchen-sink BCMS candidate generation for all unlinked schemes.

For every mature scheme without a confirmed BCMS link, generate candidates
from: spatial proximity (<=800m), name-token overlap (address/project),
unit compatibility and chronology. Score with the trained classifier and
export the top-ranked for review. Also regenerate for schemes whose earlier
candidates were all rejected.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingClassifier  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.entity_resolution.scoring import address_tokens, token_similarity  # noqa: E402

RNG = 7


def build_labelled() -> pd.DataFrame:
    rows = []
    full = pd.read_excel(settings.SILVER_DIR / "audit_bcms_name_links_FULL_COMPLETED.xlsx")
    early = pd.read_csv(settings.SILVER_DIR / "audit_bcms_name_links_COMPLETED.csv")
    for frame in (full, early):
        if "verdict" not in frame.columns:
            continue
        filled = frame[frame["verdict"].fillna("").astype(str).str.strip().str.lower().isin(["confirmed", "rejected"])].copy()
        filled["scheme_units"] = pd.to_numeric(filled.get("scheme_units"), errors="coerce")
        filled["bcms_units"] = pd.to_numeric(filled.get("bcms_units"), errors="coerce")
        filled["unit_abs_diff"] = (filled["scheme_units"] - filled["bcms_units"]).abs()
        for _, row in filled.iterrows():
            rows.append({
                "distance_metres": float(row["distance_metres"]) if pd.notna(row.get("distance_metres")) else np.nan,
                "uncommon_token_overlap": float(row.get("uncommon_token_overlap") or 0),
                "name_token_overlap": float(row.get("name_token_overlap") or 0),
                "unit_abs_diff": float(row["unit_abs_diff"]) if pd.notna(row.get("unit_abs_diff")) else np.nan,
                "label": 1 if str(row["verdict"]).strip().lower() == "confirmed" else 0,
            })
    frame = pd.DataFrame(rows)
    for column in ("distance_metres", "uncommon_token_overlap", "name_token_overlap", "unit_abs_diff"):
        frame[column] = frame[column].fillna(frame[column].median())
    return frame


if __name__ == "__main__":
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    mature = cohort[cohort["grant_year"].between(2016, 2022)].copy()
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    overlay = pd.read_csv(settings.SILVER_DIR / "audit" / "bcms_verdict_overlay.csv")
    base_links = pd.read_csv(settings.SILVER_DIR / "bcms_links_all_granted.csv")
    confirmed_schemes = (
        set(overlay[overlay["confidence_band"] == "confirmed"]["scheme_id"])
        | set(base_links[base_links["confidence_band"] == "confirmed"]["scheme_id"])
    )

    targets = mature[~mature["case_key"].astype(str).isin(confirmed_schemes)]
    print(f"unlinked mature schemes: {len(targets)}", flush=True)

    labelled = build_labelled()
    FEATURES = ["distance_metres", "uncommon_token_overlap", "name_token_overlap", "unit_abs_diff"]
    model = GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=RNG)
    model.fit(labelled[FEATURES], labelled["label"])

    rows = []
    for _, scheme in targets.iterrows():
        scheme_id = str(scheme["case_key"])
        s_east = pd.to_numeric(pd.Series([scheme.get("ITMEasting")]), errors="coerce").iloc[0]
        s_north = pd.to_numeric(pd.Series([scheme.get("ITMNorthing")]), errors="coerce").iloc[0]
        scheme_address = str(scheme.get("DevelopmentAddress") or "")
        scheme_tokens = address_tokens(scheme_address)
        units = pd.to_numeric(pd.Series([scheme.get("NumResidentialUnits")]), errors="coerce").iloc[0]

        candidates = bcms.copy()
        if not pd.isna(s_east):
            distance = np.hypot(pd.to_numeric(candidates["itm_easting"], errors="coerce") - s_east,
                                pd.to_numeric(candidates["itm_northing"], errors="coerce") - s_north)
            candidates["distance_metres"] = distance.round(0)
            candidates = candidates[distance <= 800].copy()
        else:
            candidates = candidates.iloc[0:0].copy()
        if candidates.empty:
            continue
        candidates["uncommon_token_overlap"] = candidates["address_full"].fillna("").map(
            lambda text: len(address_tokens(text) & scheme_tokens)
        )
        candidates["name_token_overlap"] = candidates["project_name"].fillna("").map(
            lambda text: len(address_tokens(text) & scheme_tokens)
        )
        candidates["unit_abs_diff"] = (pd.to_numeric(candidates["dwellings_total"], errors="coerce") - units).abs()
        for column in FEATURES:
            candidates[column] = pd.to_numeric(candidates[column], errors="coerce").fillna(labelled[column].median())
        candidates["p_link"] = model.predict_proba(candidates[FEATURES])[:, 1]
        top = candidates.sort_values("p_link", ascending=False).head(5)
        for _, candidate in top.iterrows():
            rows.append({
                "scheme_id": scheme_id,
                "scheme_address": scheme_address[:80],
                "scheme_units": units if not pd.isna(units) else None,
                "bcms_event_id": candidate["bcms_event_id"],
                "bcms_address": str(candidate["address_full"])[:80],
                "bcms_project_name": str(candidate["project_name"])[:50],
                "bcms_ref": str(candidate["planning_reference"]),
                "bcms_units": candidate["dwellings_total"],
                "bcms_commencement": str(candidate["commencement_date_dt"])[:10],
                "distance_metres": round(float(candidate["distance_metres"]), 0),
                "uncommon_token_overlap": int(candidate["uncommon_token_overlap"]),
                "name_token_overlap": int(candidate["name_token_overlap"]),
                "unit_abs_diff": round(float(candidate["unit_abs_diff"]), 0),
                "p_link": round(float(candidate["p_link"]), 3),
                "verdict": "",
                "verdict_note": "",
            })

    queue = pd.DataFrame(rows).drop_duplicates(subset=["scheme_id", "bcms_event_id"]).sort_values("p_link", ascending=False)
    queue.to_csv(settings.SILVER_DIR / "audit" / "bcms_kitchen_sink_candidates.csv", index=False)
    summary = {
        "unlinked_schemes": int(len(targets)),
        "candidate_rows": int(len(queue)),
        "schemes_with_candidates": int(queue["scheme_id"].nunique()),
        "top_band_p80": int((queue["p_link"] >= 0.8).sum()),
    }
    (settings.SILVER_DIR / "bcms_kitchen_sink_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
