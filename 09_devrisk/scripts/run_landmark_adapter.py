"""Generic external-landmark adapter (minimal).

Ingest: case_key (or address/eircode) | event_type | event_date | source |
units | confidence. Runs: linkage coverage, temporal sanity, before/after
transition distributions, uncertainty reduction. Optional predictive test
only if n >= 100 dated events. No FOI-specific architecture.
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
SNAP = pd.Timestamp("2026-10-01")


def load_states() -> pd.DataFrame:
    states = pd.read_csv(SILVER / "state_machine" / "states.csv")
    states["entered"] = pd.to_datetime(states["entered"], errors="coerce")
    return states[states["entered"] <= SNAP]


def transition_table(states: pd.DataFrame, src: str, dst: str) -> dict | None:
    a = states[states["state"] == src][["case_key", "entered"]].rename(columns={"entered": "a"})
    b = states[states["state"] == dst][["case_key", "entered"]].rename(columns={"entered": "b"})
    m = a.merge(b, on="case_key", how="inner")
    m = m[(m["b"] >= m["a"]) & (m["b"] - m["a"] <= pd.Timedelta(days=4000))]
    d = (m["b"] - m["a"]).dt.days.to_numpy()
    if len(d) < 20:
        return None
    d = np.sort(d)
    return {"n": int(len(d)), "median_days": round(float(np.median(d)), 1),
            "q25": round(float(np.quantile(d, 0.25)), 1),
            "q75": round(float(np.quantile(d, 0.75)), 1),
            "pct10": round(float(np.quantile(d, 0.1)), 1),
            "pct90": round(float(np.quantile(d, 0.9)), 1),
            "within_3m": round(float((d <= 91).mean() * 100), 1),
            "within_6m": round(float((d <= 183).mean() * 100), 1),
            "within_12m": round(float((d <= 365).mean() * 100), 1)}


def ingest(path: str, event_type_col: str = "event_type",
           date_col: str = "event_date", key_col: str = "case_key",
           address_cols: tuple[str, ...] = ("address",),
           eircode_col: str = "eircode") -> dict:
    frame = pd.read_csv(path, dtype=str)
    frame[date_col] = pd.to_datetime(frame[date_col], errors="coerce")
    frame = frame[frame[date_col] <= SNAP]
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                               columns=["case_key", "DevelopmentAddress",
                                        "DevelopmentPostcode", "GrantDate"])
    register["grant_dt"] = pd.to_datetime(register["GrantDate"], utc=True,
                                          errors="coerce").dt.tz_localize(None)
    register = register.drop_duplicates("case_key")
    states = load_states()

    linked = 0
    via_address = 0
    unlinked = 0
    events = []
    for _, r in frame.iterrows():
        key = r.get(key_col)
        if pd.isna(key) or key not in set(register["case_key"]):
            match = None
            if eircode_col in frame.columns and pd.notna(r.get(eircode_col)):
                cand = register[register["DevelopmentPostcode"].fillna("") == str(r[eircode_col]).strip()]
                if len(cand) == 1:
                    match = cand["case_key"].iloc[0]
            if match is None and address_cols:
                blob = " ".join(str(r.get(c)) for c in address_cols if pd.notna(r.get(c))).lower()
                if blob:
                    cand = register[register["DevelopmentAddress"].fillna("").str.lower() == blob]
                    if len(cand) == 1:
                        match = cand["case_key"].iloc[0]
            if match is None:
                unlinked += 1
                continue
            key = match
            via_address += 1
        else:
            linked += 1
        events.append({"case_key": key, "event_type": r.get(event_type_col),
                       "event_date": r[date_col], "source": r.get("source", "external"),
                       "units": pd.to_numeric(r.get("units"), errors="coerce")})

    sanity = {"n_in": int(len(frame)), "n_linked_direct": linked,
              "n_linked_via_address": via_address, "n_unlinked": unlinked,
              "coverage_pct": round((linked + via_address) / max(len(frame), 1) * 100, 1)}
    if not events:
        return {"sanity": sanity}
    ev = pd.DataFrame(events)
    ev = ev.merge(register[["case_key", "grant_dt"]], on="case_key", how="left")
    ev["before_grant_30"] = ev["event_date"] < (ev["grant_dt"] - pd.Timedelta(days=30))
    ev["duplicate"] = ev.duplicated(subset=["case_key", "event_type", "event_date"])
    sanity.update({
        "n_linked": int(len(ev)),
        "events_before_grant_30d": int(ev["before_grant_30"].sum()),
        "duplicate_events": int(ev["duplicate"].sum()),
        "date_range": [str(ev["event_date"].min().date()), str(ev["event_date"].max().date())],
    })

    before_after = {}
    uncertainty = {}
    ev = ev[~ev["before_grant_30"]].copy()
    for _, r in ev.iterrows():
        s = states[states["case_key"] == r["case_key"]].sort_values("entered")
        prior = s[s["entered"] <= r["event_date"]]
        if prior.empty:
            continue
        cur_state = prior.iloc[-1]["state"]
        future = s[s["entered"] > r["event_date"]]
        nxt = future.iloc[0]["state"] if len(future) else None
        before = transition_table(states, cur_state, r["event_type"])
        after = transition_table(states, r["event_type"], nxt) if nxt else None
        key = f"{cur_state}->{r['event_type']}"
        if key not in before_after and before is not None:
            before_after[key] = before
        if after is not None:
            key2 = f"{r['event_type']}->{nxt}"
            if key2 not in before_after:
                before_after[key2] = after
    for etype, g in ev.groupby("event_type"):
        prior_state_durs = []
        post_state_durs = []
        for _, r in g.iterrows():
            s = states[states["case_key"] == r["case_key"]].sort_values("entered")
            prior = s[s["entered"] <= r["event_date"]]
            future = s[s["entered"] > r["event_date"]]
            if prior.empty or future.empty:
                continue
            prior_state_durs.append((r["event_date"] - prior.iloc[-1]["entered"]).days)
            post_state_durs.append((future.iloc[0]["entered"] - r["event_date"]).days)
        entry = {"n": int(len(prior_state_durs))}
        if len(prior_state_durs) >= 10:
            entry["median_since_prior_state_days"] = round(float(np.median(prior_state_durs)), 1)
            entry["median_to_next_state_days"] = round(float(np.median(post_state_durs)), 1)
            w_pre = float(np.quantile(prior_state_durs, 0.9) - np.quantile(prior_state_durs, 0.1))
            w_post = float(np.quantile(post_state_durs, 0.9) - np.quantile(post_state_durs, 0.1))
            entry["width80_before"] = round(w_pre, 1)
            entry["width80_after"] = round(w_post, 1)
            entry["uncertainty_reduction_pct"] = round((1 - w_post / max(w_pre, 1)) * 100, 1)
            entry["predictive_test"] = "insufficient_n" if entry["n"] < 100 else "eligible"
        uncertainty[etype] = entry

    return {"sanity": sanity, "before_after_transitions": before_after,
            "uncertainty_reduction": uncertainty}


def main() -> None:
    import sys
    if len(sys.argv) < 2:
        print(json.dumps({"usage": "run_landmark_adapter.py <events.csv>"}, indent=2))
        return
    out = ingest(sys.argv[1])
    out_path = SILVER / "landmarks" / "adapter_output.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
