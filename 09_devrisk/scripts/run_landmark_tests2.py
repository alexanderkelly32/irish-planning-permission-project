"""Landmark tests: enforcement events + TIC ledger events.

Same protocol and gate as SPV/amendment: coverage/precision, timing vs
prior state, median/80% width before vs after, 3/6/12m next-transition
probabilities, elapsed-since-prior-state + grant-year matched controls,
>=20% width reduction or >=15pp horizon shift. Observed landmarks only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402
from run_readiness_events import extract_date  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "landmarks"
SNAP = pd.Timestamp("2026-10-01")
TIC_RE = re.compile(r"taking in charge|taken in charge|take in charge|\btic\b", re.I)


def width80(v):
    return float(np.quantile(v, 0.9) - np.quantile(v, 0.1))


def landmark_test(events: pd.DataFrame, base: pd.DataFrame, states: pd.DataFrame,
                  name: str) -> dict:
    rows = []
    for _, e in events.iterrows():
        s = states[states["case_key"] == e["case_key"]].sort_values("entered")
        prior = s[s["entered"] <= e["event_dt"]]
        future = s[s["entered"] > e["event_dt"]]
        if prior.empty:
            continue
        rows.append({
            "case_key": e["case_key"], "event_dt": e["event_dt"],
            "prior_state": prior.iloc[-1]["state"],
            "elapsed_since_prior_state": (e["event_dt"] - prior.iloc[-1]["entered"]).days,
            "next_state": future.iloc[0]["state"] if len(future) else None,
            "remaining_to_next": (future.iloc[0]["entered"] - e["event_dt"]).days if len(future) else None,
            "grant_year": base.loc[base["case_key"] == e["case_key"], "grant_year"].iloc[0] if len(base[base["case_key"] == e["case_key"]]) else None,
        })
    ev = pd.DataFrame(rows).dropna(subset=["remaining_to_next", "grant_year"])
    ev = ev[ev["remaining_to_next"] <= 4000]
    if ev.empty:
        return {"coverage": {"n_events": int(len(events)), "n_usable": 0}, "verdict": "insufficient"}
    ctrl_rows = []
    for _, e in ev.iterrows():
        ctrl = base[(base["case_key"] != e["case_key"]) &
                    (base["grant_year"].between(e["grant_year"] - 1, e["grant_year"] + 1))]
        for _, c in ctrl.iterrows():
            cs = states[(states["case_key"] == c["case_key"]) &
                        (states["state"] == e["prior_state"])]
            if cs.empty:
                continue
            anchor = cs["entered"].iloc[-1]
            t0 = anchor + pd.Timedelta(days=e["elapsed_since_prior_state"])
            cf = states[(states["case_key"] == c["case_key"]) & (states["entered"] > t0)]
            if cf.empty:
                continue
            ctrl_rows.append({"case_key": c["case_key"],
                              "remaining_to_next": (cf.iloc[0]["entered"] - t0).days,
                              "grant_year": c["grant_year"]})
    ctrl = pd.DataFrame(ctrl_rows)
    entry = {
        "coverage": {"n_events": int(len(events)), "n_usable": int(len(ev))},
        "timing": {
            "median_elapsed_since_prior_state": round(float(ev["elapsed_since_prior_state"].median()), 1),
            "prior_state_counts": ev["prior_state"].value_counts().to_dict(),
            "next_state_counts": ev["next_state"].value_counts().to_dict(),
        },
        "before_after": {
            "evented_n": int(len(ev)),
            "evented_width80": round(width80(ev["remaining_to_next"]), 1),
            "evented_median_remaining": round(float(ev["remaining_to_next"].median()), 1),
            "evented_within_3m": round(float((ev["remaining_to_next"] <= 91).mean() * 100), 1),
            "evented_within_6m": round(float((ev["remaining_to_next"] <= 183).mean() * 100), 1),
            "evented_within_12m": round(float((ev["remaining_to_next"] <= 365).mean() * 100), 1),
            "matched_control_n": int(len(ctrl)),
        },
    }
    if len(ctrl) >= 10:
        entry["before_after"].update({
            "control_width80": round(width80(ctrl["remaining_to_next"]), 1),
            "control_median_remaining": round(float(ctrl["remaining_to_next"].median()), 1),
            "control_within_12m": round(float((ctrl["remaining_to_next"] <= 365).mean() * 100), 1),
            "width_reduction_pct": round((1 - width80(ev["remaining_to_next"]) /
                                          width80(ctrl["remaining_to_next"])) * 100, 1),
            "horizon_12m_delta_pp": round(float((ev["remaining_to_next"] <= 365).mean() * 100 -
                                               (ctrl["remaining_to_next"] <= 365).mean() * 100), 1),
        })
        w = entry["before_after"]["width_reduction_pct"]
        h = entry["before_after"]["horizon_12m_delta_pp"]
        entry["gate"] = {"width_reduction_pct": w, "horizon_12m_delta_pp": h,
                         "verdict": "keep" if (w >= 20.0 or abs(h) >= 15.0) else "falsified"}
    if len(ev[ev["grant_year"] < 2022]) >= 10 and len(ev[ev["grant_year"] >= 2022]) >= 10:
        entry["temporal_split"] = {
            "pre2022_median_remaining": round(float(ev[ev["grant_year"] < 2022]["remaining_to_next"].median()), 1),
            "post2022_median_remaining": round(float(ev[ev["grant_year"] >= 2022]["remaining_to_next"].median()), 1),
        }
    return entry


def main() -> None:
    clean = pd.read_csv(SILVER / "dq" / "labels_clean.csv", dtype=str)
    clean_keys = set(clean["case_key"])
    labels = pd.read_csv(SILVER / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    labels = labels[labels["activation_linked"].astype(str).str.lower() == "true"]
    labels["activation"] = pd.to_numeric(labels["activation_days"], errors="coerce")
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                               columns=["case_key", "GrantDate"])
    register["grant_dt"] = pd.to_datetime(register["GrantDate"], utc=True, errors="coerce").dt.tz_localize(None)
    register = register.drop_duplicates("case_key")
    base = labels.merge(register, on="case_key", how="inner")
    base = base[base["case_key"].isin(clean_keys)]
    base = base.dropna(subset=["grant_dt", "activation"])
    base["comm_dt"] = base["grant_dt"] + pd.to_timedelta(base["activation"], unit="D")
    base["grant_year"] = base["grant_dt"].dt.year
    states = pd.read_csv(SILVER / "state_machine" / "states.csv")
    states["entered"] = pd.to_datetime(states["entered"], errors="coerce")

    report = {}

    enf = pd.read_csv(SILVER / "scheme_enforcement_matches.csv", dtype=str)
    enf["entry_date"] = pd.to_datetime(enf["entry_date"], errors="coerce")
    report["enforcement_events"] = {
        "coverage": {"n_rows": int(len(enf)), "n_dated": int(enf["entry_date"].notna().sum()),
                     "n_schemes": int(enf["scheme_id"].nunique())},
        "precision": {"token_overlap_distribution": enf["token_overlap"].value_counts().to_dict()},
        "verdict": "blocked - harvest contains navigation-menu scrapes, no dated enforcement notices",
    }

    ck_map = {}
    for ck in clean["case_key"]:
        ck_map[ck[:80]] = ck
        ck_map[ck.replace(" ", "_")[:80]] = ck
    import zipfile
    with zipfile.ZipFile(SILVER / "audit_packs" / "PACK_24_residual_forensics.zip") as z:
        for ck in pd.read_csv(z.open("residual_forensics_cohort.csv"))["case_key"]:
            ck_map[ck[:80]] = ck
            ck_map[ck.replace(" ", "_")[:80]] = ck

    tic_events = []
    for scheme_dir in sorted((SILVER / "idocs" / "docs").glob("*/readiness")):
        name = scheme_dir.parent.name
        key = ck_map.get(name) or ck_map.get(name.replace("_", " "))
        if not key:
            continue
        for dj in scheme_dir.glob("*.json"):
            try:
                d = json.loads(dj.read_text(encoding="utf-8"))
            except Exception:
                continue
            if d.get("status") != "ok" or not d.get("text"):
                continue
            if TIC_RE.search(f"{d.get('type', '')} {d.get('comment', '')}"):
                ts, _ = extract_date(d["text"], d.get("comment", ""))
                if ts is not None and ts <= SNAP:
                    tic_events.append({"case_key": key, "event_dt": ts})
    tic_df = pd.DataFrame(tic_events).drop_duplicates(subset=["case_key", "event_dt"])
    report["tic_events"] = landmark_test(tic_df, base, states, "tic")

    (OUT / "landmark_tests2_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
