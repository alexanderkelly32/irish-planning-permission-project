"""Runner: fold unfurled data into models (background batch 3).

1. BCMS phase features -> sale re-forecast v2 (post-commencement): adds
   planned_duration_days, phase_count, ccc_type to the CCC->first-sale model.
2. 4Dublin activity columns -> completion corroboration labels for Dublin
   schemes (Activity_On_Site / Units_Completed), merged into exit labels as
   additional evidence.
3. PPR negatives -> overlap classifier retrain (precision check).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

if __name__ == "__main__":
    report: dict = {}

    # ---- 1. sale re-forecast v2 with BCMS phase features ----
    cohort = pd.read_parquet(settings.SILVER_DIR / "all_granted_ge10_cohort.parquet")
    exit_labels = pd.read_csv(settings.SILVER_DIR / "exit_labels_pool.csv")
    bcms = pd.read_parquet(settings.SILVER_DIR / "bcms_events_silver.parquet")
    links = pd.read_csv(settings.SILVER_DIR / "bcms_links_all_granted.csv")
    overlay = settings.SILVER_DIR / "audit" / "bcms_verdict_overlay.csv"
    if overlay.exists():
        links = pd.concat([links, pd.read_csv(overlay).reindex(columns=links.columns)], ignore_index=True)
    confirmed = links[links["confidence_band"] == "confirmed"]
    events = confirmed.merge(bcms, on="bcms_event_id", how="inner")

    sold = exit_labels[exit_labels["sales_linked"] > 0].copy()
    sold["first_sale_dt"] = pd.to_datetime(sold["first_sale_date"], utc=True, errors="coerce")
    sold = sold.dropna(subset=["first_sale_dt"])

    rows = []
    for scheme_id, group in events.groupby("scheme_id"):
        scheme = sold[sold["scheme_id"] == str(scheme_id)]
        if scheme.empty:
            continue
        first_sale = scheme.iloc[0]["first_sale_dt"]
        ccc_dates = pd.to_datetime(group["completion_certificate_date_dt"], utc=True, errors="coerce").dropna()
        if ccc_dates.empty:
            continue
        ccc = ccc_dates.min()
        planned = pd.to_numeric(group["planned_duration_days"], errors="coerce").dropna()
        phases = pd.to_numeric(group["phase_number"], errors="coerce").dropna()
        rows.append({
            "scheme_id": str(scheme_id),
            "tfs_from_ccc": int((first_sale - ccc).days),
            "planned_duration_days": float(planned.median()) if len(planned) else np.nan,
            "n_phases": int(phases.nunique()) if len(phases) else np.nan,
            "max_phase": float(phases.max()) if len(phases) else np.nan,
            "has_full_ccc": int(bool(group["ccc_type"].astype(str).str.contains("full", case=False, na=False).any())),
        })
    frame = pd.DataFrame(rows)
    frame = frame[frame["tfs_from_ccc"].between(-180, 3000)]
    frame.to_csv(settings.SILVER_DIR / "sale_reforecast_v2_frame.csv", index=False)
    lo, hi = np.quantile(frame["tfs_from_ccc"], [0.1, 0.9])
    base = {"n": int(len(frame)), "median_days": round(float(frame["tfs_from_ccc"].median()), 0),
            "width80": round(float(hi - lo), 0), "coverage": round(float(np.mean(frame["tfs_from_ccc"].between(lo, hi))), 3)}
    valid = frame.dropna(subset=["planned_duration_days"])
    corr = float(np.corrcoef(valid["planned_duration_days"], valid["tfs_from_ccc"])[0, 1]) if len(valid) >= 30 else None
    report["sale_reforecast_v2"] = {"base": base, "corr_planned_duration_vs_tfs": round(corr, 3) if corr is not None else None,
                                    "planned_duration_n": int(len(valid))}
    print(json.dumps(report["sale_reforecast_v2"], indent=2), flush=True)

    # ---- 2. 4Dublin completion corroboration ----
    pipeline = pd.read_csv(settings.SILVER_DIR / "4dublin" / "pipeline_all.csv", low_memory=False)
    pipeline = pipeline[pipeline["Planning_Authority"].isin(
        {"Dublin City Council", "Dun Laoghaire Rathdown County Council", "Fingal County Council", "South Dublin County Council"})]
    pipeline["app_norm"] = pipeline["Planning_Reference"].astype(str).str.upper().str.replace(r"\s+", "", regex=True)
    latest = pipeline.sort_values("Year_Quarter").groupby("app_norm").tail(1)
    activity = latest[["app_norm", "Activity_On_Site", "Units_Completed_or_Completed_an", "Units_Under_Construction"]]
    activity = activity[activity["Units_Completed_or_Completed_an"].notna() | activity["Activity_On_Site"].notna()]
    cohort["app_norm"] = cohort["ApplicationNumber"].astype(str).str.upper().str.replace(r"\s+", "", regex=True)
    merged = cohort.merge(activity, on="app_norm", how="inner")
    report["4dublin_completion"] = {
        "dublin_schemes_with_activity": int(len(merged)),
        "with_units_completed": int(merged["Units_Completed_or_Completed_an"].notna().sum()),
        "completed_units_total": int(pd.to_numeric(merged["Units_Completed_or_Completed_an"], errors="coerce").fillna(0).sum()),
    }
    merged[["case_key", "Activity_On_Site", "Units_Completed_or_Completed_an", "Units_Under_Construction"]].to_csv(
        settings.SILVER_DIR / "dublin_activity_corroboration.csv", index=False)
    print(json.dumps(report["4dublin_completion"], indent=2), flush=True)

    # ---- 3. PPR overlap classifier retrain with accumulated negatives ----
    negatives = pd.read_csv(settings.SILVER_DIR / "audit" / "ppr_negatives_accumulated.csv")
    positives = pd.read_csv(settings.SILVER_DIR / "scheme_sales_verified.csv")
    report["overlap_classifier"] = {
        "negatives_available": int(len(negatives)),
        "positives_available": int(len(positives)),
        "note": "retrain queued: classifier needs scheme-address context columns from the scoring table before refit",
    }
    print(json.dumps(report["overlap_classifier"], indent=2), flush=True)

    out = settings.SILVER_DIR / "fold_unfurled_batch3.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
