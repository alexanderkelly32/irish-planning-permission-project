"""Progress-based completion states: event histories + quality + snapshots.

Event-level CCC history per clean commenced scheme from BCMS notices linked
to schemes, with quarantine guards. Denominators from the register
(scheme-level); phase allocation flagged, never inferred. Snapshots at 0%,
first CCC, 25/50/75%, and after every CCC event, with observed-only
features and remaining-time targets.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "construction_progress"
OUT.mkdir(parents=True, exist_ok=True)
SNAP = pd.Timestamp("2026-10-01")


def main() -> None:
    clean = pd.read_csv(SILVER / "dq" / "labels_clean.csv", dtype=str)
    clean_keys = set(clean["case_key"])
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                               columns=["case_key", "NumResidentialUnits",
                                        "DevelopmentDescription", "GrantDate"])
    register["grant_dt"] = pd.to_datetime(register["GrantDate"], utc=True, errors="coerce").dt.tz_localize(None)
    register = register.drop_duplicates("case_key")
    labels = pd.read_csv(SILVER / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    labels = labels[labels["activation_linked"].astype(str).str.lower() == "true"]
    labels["activation"] = pd.to_numeric(labels["activation_days"], errors="coerce")

    bcms = pd.read_parquet(SILVER / "bcms_events_silver.parquet",
                           columns=["bcms_event_id", "completion_certificate_date_dt",
                                    "completion_units", "phase_number", "total_phases"])
    bcms["ccc_dt"] = pd.to_datetime(bcms["completion_certificate_date_dt"], utc=True,
                                    errors="coerce").dt.tz_localize(None)
    links = pd.read_csv(SILVER / "bcms_links_all_granted.csv", dtype=str)
    links = links.merge(bcms, on="bcms_event_id", how="inner")
    links = links[links["scheme_id"].isin(clean_keys)]

    meta = register[register["case_key"].isin(clean_keys)].merge(
        labels[["case_key", "activation"]], on="case_key", how="inner")
    meta["units"] = pd.to_numeric(meta["NumResidentialUnits"], errors="coerce")
    meta["comm_dt"] = meta["grant_dt"] + pd.to_timedelta(meta["activation"], unit="D")

    events = []
    for key, group in links.groupby("scheme_id"):
        m = meta[meta["case_key"] == key]
        if m.empty:
            continue
        comm = m["comm_dt"].iloc[0]
        if pd.isna(comm):
            continue
        guard = comm - pd.Timedelta(days=30)
        ev = group.dropna(subset=["ccc_dt"])
        ev = ev[(ev["ccc_dt"] >= guard) & (ev["ccc_dt"] <= SNAP)]
        if ev.empty:
            continue
        for _, r in ev.sort_values("ccc_dt").iterrows():
            events.append({"case_key": key, "ccc_dt": r["ccc_dt"],
                           "units_certified": r["completion_units"],
                           "phase_number": r["phase_number"],
                           "total_phases": r["total_phases"],
                           "bcms_event_id": r["bcms_event_id"]})
    frame = pd.DataFrame(events)
    if frame.empty:
        print(json.dumps({"error": "no events"}), flush=True)
        return
    frame = frame.drop_duplicates(subset=["case_key", "ccc_dt", "bcms_event_id"])
    frame = frame.merge(meta[["case_key", "units", "comm_dt", "grant_dt"]], on="case_key", how="left")
    frame["type_apartment"] = frame["case_key"].map(
        register.set_index("case_key")["DevelopmentDescription"]).fillna("").str.contains(
        "apartment|duplex", case=False, regex=True).astype(int)
    frame = frame.sort_values(["case_key", "ccc_dt"])
    frame["cum_units"] = frame.groupby("case_key")["units_certified"].cumsum()
    frame["cum_pct"] = frame["cum_units"] / frame["units"] * 100
    frame["n_ccc_to_date"] = frame.groupby("case_key").cumcount() + 1
    frame["days_since_last_ccc"] = frame.groupby("case_key")["ccc_dt"].diff().dt.days.fillna(
        (frame["ccc_dt"] - frame["comm_dt"]).dt.days)
    frame["elapsed_days"] = (frame["ccc_dt"] - frame["comm_dt"]).dt.days
    frame.to_csv(OUT / "construction_progress_events.csv", index=False)

    quality = {
        "schemes_with_ccc": int(frame["case_key"].nunique()),
        "events": int(len(frame)),
        "schemes_with_units": int(frame.dropna(subset=["units"]).groupby("case_key")["units"].first().notna().sum()),
        "events_with_unit_counts": int(frame["units_certified"].notna().sum()),
        "pct_events_with_unit_counts": round(float(frame["units_certified"].notna().mean() * 100), 1),
        "final_cum_pct_median": round(float(frame.groupby("case_key")["cum_pct"].last().median()), 1),
        "schemes_over_certified": int((frame.groupby("case_key")["cum_pct"].last() > 110).sum()),
        "schemes_under_certified_final": int((frame.groupby("case_key")["cum_pct"].last() < 90).sum()),
        "duplicate_events": int(frame.duplicated(subset=["case_key", "ccc_dt"]).sum()),
        "non_monotonic_cum": int((frame.groupby("case_key")["cum_pct"].apply(lambda s: (s.diff() < -1).any())).sum()),
        "phase_ambiguous": int((frame.groupby("case_key")["phase_number"].nunique() > 1).sum()),
        "ccc_events_per_scheme": frame.groupby("case_key").size().describe().round(1).to_dict(),
    }
    (OUT / "construction_progress_quality.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")

    snapshots = []
    for key, g in frame.groupby("case_key"):
        m = meta[meta["case_key"] == key]
        units = m["units"].iloc[0]
        comm = m["comm_dt"].iloc[0]
        if pd.isna(units) or units <= 0:
            continue
        g = g.sort_values("ccc_dt")
        g["cum_units"] = g["units_certified"].cumsum()
        g["cum_pct"] = g["cum_units"] / units * 100
        final_dt = g["ccc_dt"].iloc[-1]
        seen = set()
        for i, r in g.iterrows():
            elapsed = r["elapsed_days"]
            cum_pct = r["cum_pct"]
            state = "event"
            if i == 0:
                state = "first_ccc"
            for threshold in (25, 50, 75):
                if cum_pct >= threshold and threshold not in seen:
                    state = f"pct{threshold}"
                    seen.add(threshold)
            seen.add("first_ccc")
            prev = g.iloc[:i] if i > 0 else None
            vel = 0.0
            if prev is not None and len(prev) and len(prev) >= 1:
                window = prev[prev["ccc_dt"] >= r["ccc_dt"] - pd.Timedelta(days=90)]
                if len(window):
                    vel = window["units_certified"].sum() / 90.0
            snapshots.append({
                "case_key": key, "state": state, "snapshot_dt": r["ccc_dt"],
                "elapsed_days": elapsed, "cum_pct": cum_pct,
                "units_certified_total": r["cum_units"], "units_remaining": max(units - r["cum_units"], 0),
                "n_ccc_to_date": r["n_ccc_to_date"], "days_since_last_ccc": r["days_since_last_ccc"],
                "velocity_90d": vel, "scheme_units": units,
                "type_apartment": r["type_apartment"],
                "target_next_ccc_days": (g["ccc_dt"].iloc[i + 1] - r["ccc_dt"]).days if i + 1 < len(g) else None,
                "target_final_ccc_days": (final_dt - r["ccc_dt"]).days,
                "within_3m_final": int((final_dt - r["ccc_dt"]).days <= 91),
                "within_6m_final": int((final_dt - r["ccc_dt"]).days <= 183),
                "within_12m_final": int((final_dt - r["ccc_dt"]).days <= 365),
                "within_18m_final": int((final_dt - r["ccc_dt"]).days <= 548),
            })
        first = g.iloc[0]
        snapshots.append({
            "case_key": key, "state": "commenced", "snapshot_dt": comm,
            "elapsed_days": 0.0, "cum_pct": 0.0,
            "units_certified_total": 0.0, "units_remaining": float(units),
            "n_ccc_to_date": 0, "days_since_last_ccc": None, "velocity_90d": 0.0,
            "scheme_units": float(units), "type_apartment": first["type_apartment"],
            "target_next_ccc_days": (first["ccc_dt"] - comm).days,
            "target_final_ccc_days": (final_dt - comm).days,
            "within_3m_final": int((final_dt - comm).days <= 91),
            "within_6m_final": int((final_dt - comm).days <= 183),
            "within_12m_final": int((final_dt - comm).days <= 365),
            "within_18m_final": int((final_dt - comm).days <= 548),
        })
    snaps = pd.DataFrame(snapshots)
    snaps.to_csv(OUT / "construction_progress_snapshots.csv", index=False)
    print(json.dumps({"quality": quality, "n_snapshots": int(len(snaps)),
                      "snapshot_states": snaps["state"].value_counts().to_dict()}, indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
