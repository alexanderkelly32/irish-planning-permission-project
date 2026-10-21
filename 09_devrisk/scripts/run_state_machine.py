"""Build the canonical state machine for every scheme.

States (only entered with evidence; dormant is inferred-absence, flagged):
submitted, fi_requested, fi_received, decision_issued, appeal_active,
final_grant, dormant_granted, notice_filed, commenced, first_ccc,
partial_ccc, final_ccc, first_sale, active_sales, complete.

Outputs:
- silver/state_machine/states.csv: one row per scheme-state (entered date,
  source, source_reference, observed_or_inferred, confidence)
- silver/state_machine/current_state.csv: as-of-snapshot current state per
  scheme with days_in_state, last_observed_event, next_possible_states
- silver/state_machine/transitions.csv: empirical transition distributions
  (n, median, quartiles, KM 50/80/90% intervals, 3/6/12m horizon probs)
- silver/state_machine/uncertainty_reduction.json: remaining-time width at
  each landmark (first-class product metric)
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
OUT = SILVER / "state_machine"
OUT.mkdir(parents=True, exist_ok=True)
SNAP = pd.Timestamp("2026-10-01")

STATE_ORDER = ["submitted", "fi_requested", "fi_received", "decision_issued",
               "appeal_active", "final_grant", "dormant_granted", "notice_filed",
               "commenced", "first_ccc", "pct25", "pct50", "pct75", "partial_ccc",
               "final_ccc", "first_sale", "active_sales", "complete"]


def km_intervals(durations: pd.Series, widths=(0.5, 0.8, 0.9)) -> dict:
    s = durations.dropna().sort_values().to_numpy()
    out = {}
    for w in widths:
        if len(s):
            out[f"pct{int(w * 100)}_lower"] = float(np.percentile(s, (1 - w) / 2 * 100))
            out[f"pct{int(w * 100)}_upper"] = float(np.percentile(s, (1 + w) / 2 * 100))
        else:
            out[f"pct{int(w * 100)}_lower"] = None
            out[f"pct{int(w * 100)}_upper"] = None
    return out


def transition_stats(src: str, dst: str, frame: pd.DataFrame) -> dict:
    srcs = frame[frame["state"] == src][["case_key", "entered"]].rename(columns={"entered": "src_dt"})
    dsts = frame[frame["state"] == dst][["case_key", "entered"]].rename(columns={"entered": "dst_dt"})
    m = srcs.merge(dsts, on="case_key", how="inner")
    m = m[m["dst_dt"] >= m["src_dt"]]
    if m.empty:
        return {"n": 0}
    m["dur"] = (m["dst_dt"] - m["src_dt"]).dt.days
    m = m[(m["dur"] >= 0) & (m["dur"] <= 4000)]
    entry = {"n": int(len(m)), "median_days": round(float(m["dur"].median()), 1),
             "q25": round(float(m["dur"].quantile(0.25)), 1),
             "q75": round(float(m["dur"].quantile(0.75)), 1)}
    entry.update(km_intervals(m["dur"]))
    for k in (3, 6, 12):
        entry[f"within_{k}m"] = round(float((m["dur"] <= k * 30.44).mean() * 100), 1)
    return entry


def main() -> None:
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                               columns=["case_key", "ReceivedDate", "FIRequestDate", "FIRecDate",
                                        "DecisionDate", "GrantDate", "AppealSubmittedDate",
                                        "AppealDecisionDate", "AppealStatus", "WithdrawnDate"])
    date_cols = ["ReceivedDate", "FIRequestDate", "FIRecDate", "DecisionDate", "GrantDate",
                 "AppealSubmittedDate", "AppealDecisionDate", "WithdrawnDate"]
    for c in date_cols:
        register[c] = pd.to_datetime(register[c], utc=True, errors="coerce").dt.tz_localize(None)

    bcms = pd.read_parquet(SILVER / "bcms_events_silver.parquet",
                           columns=["bcms_event_id", "received_date_dt", "commencement_date_dt",
                                    "completion_certificate_date_dt", "completion_units",
                                    "valid_completion_certificate"])
    for c in ("received_date_dt", "commencement_date_dt", "completion_certificate_date_dt"):
        bcms[c] = pd.to_datetime(bcms[c], utc=True, errors="coerce").dt.tz_localize(None)
    links = pd.read_csv(SILVER / "bcms_links_all_granted.csv", dtype=str)
    links = links.merge(bcms, on="bcms_event_id", how="inner")

    ccc = pd.read_csv(SILVER / "ccc_blocks.csv", dtype=str)
    ccc["first_ccc"] = pd.to_datetime(ccc["first_ccc"], utc=True, errors="coerce").dt.tz_localize(None)
    ccc["last_ccc"] = pd.to_datetime(ccc["last_ccc"], utc=True, errors="coerce").dt.tz_localize(None)
    ccc["ccc_events"] = pd.to_numeric(ccc["ccc_events"], errors="coerce")

    sales = pd.read_csv(SILVER / "scheme_sales_bcms_notice_auto.csv", dtype=str)
    sales["sale_date"] = pd.to_datetime(sales["sale_date"], utc=True, errors="coerce").dt.tz_localize(None)

    labels = pd.read_csv(SILVER / "pain_labels_pool.csv")
    pool_keys = set(labels["scheme_id"].astype(str))
    register = register[register["case_key"].isin(pool_keys)]
    labels_comm = labels[labels["activation_linked"].astype(str).str.lower() == "true"].copy()
    labels_comm["comm_dt"] = register.set_index("case_key")["GrantDate"].map(
        lambda d: None) if False else None
    grant_map = register.dropna(subset=["GrantDate"]).set_index("case_key")["GrantDate"]
    labels_comm["comm_dt"] = labels_comm["scheme_id"].map(grant_map) + pd.to_timedelta(
        pd.to_numeric(labels_comm["activation_days"], errors="coerce"), unit="D")
    comm_by_key = labels_comm.dropna(subset=["comm_dt"]).set_index("scheme_id")["comm_dt"].to_dict()

    links_by_scheme = {k: g for k, g in links.groupby("scheme_id")}
    ccc_by_scheme = {k: g for k, g in ccc.groupby("scheme_id")}
    sales_by_scheme = {k: g for k, g in sales.groupby("scheme_id")}

    rows = []
    for _, r in register.iterrows():
        key = r["case_key"]
        ev = []
        grant_dt = r["GrantDate"] if pd.notna(r["GrantDate"]) else None
        if pd.notna(r["ReceivedDate"]):
            ev.append(("submitted", r["ReceivedDate"], "register", "ReceivedDate", "observed", "high"))
        if pd.notna(r["FIRequestDate"]):
            ev.append(("fi_requested", r["FIRequestDate"], "register", "FIRequestDate", "observed", "high"))
        if pd.notna(r["FIRecDate"]):
            ev.append(("fi_received", r["FIRecDate"], "register", "FIRecDate", "observed", "high"))
        if pd.notna(r["DecisionDate"]):
            ev.append(("decision_issued", r["DecisionDate"], "register", "DecisionDate", "observed", "high"))
        if pd.notna(r["AppealSubmittedDate"]) and pd.isna(r["AppealDecisionDate"]):
            ev.append(("appeal_active", r["AppealSubmittedDate"], "register", "AppealSubmittedDate", "observed", "high"))
        if grant_dt is not None:
            ev.append(("final_grant", grant_dt, "register", "GrantDate", "observed", "high"))
        guard = grant_dt - pd.Timedelta(days=30) if grant_dt is not None else None
        lnk = links_by_scheme.get(key)
        if lnk is not None and len(lnk):
            first_notice = lnk["received_date_dt"].dropna().min()
            if pd.notna(first_notice) and (guard is None or first_notice >= guard):
                ev.append(("notice_filed", first_notice, "bcms", "received_date_dt", "observed", "high"))
            first_comm = lnk["commencement_date_dt"].dropna().min()
            if pd.notna(first_comm) and (guard is None or first_comm >= guard):
                ev.append(("commenced", first_comm, "bcms", "commencement_date_dt", "observed", "high"))
            cccs = lnk["completion_certificate_date_dt"].dropna()
            cccs = cccs[cccs >= (guard if guard is not None else cccs.min())]
            if len(cccs):
                first_cc = cccs.min()
                last_cc = cccs.max()
                ev.append(("first_ccc", first_cc, "bcms", "completion_certificate_date_dt", "observed", "high"))
                if last_cc > first_cc:
                    ev.append(("partial_ccc", last_cc, "bcms", "completion_certificate_date_dt", "observed", "high"))
                ev.append(("final_ccc", last_cc, "bcms", "completion_certificate_date_dt", "observed", "high"))
        comm_lab = comm_by_key.get(key)
        if comm_lab is not None and pd.notna(comm_lab):
            ev.append(("commenced", comm_lab, "labels", "activation_linked", "observed", "high"))
        blk = ccc_by_scheme.get(key)
        if blk is not None and len(blk):
            fb = blk["first_ccc"].dropna().min()
            if fb <= SNAP and (guard is None or fb >= guard):
                ev.append(("first_ccc", fb, "ccc_blocks", "first_ccc", "observed", "high"))
            if blk["ccc_events"].sum() > 1:
                ev.append(("partial_ccc", blk["last_ccc"].dropna().max(), "ccc_blocks", "last_ccc", "observed", "medium"))
        sl = sales_by_scheme.get(key)
        if sl is not None and len(sl):
            fs = sl["sale_date"].dropna().min()
            if fs <= SNAP and (guard is None or fs >= guard):
                ev.append(("first_sale", fs, "ppr_bcms", "sale_date", "observed", "high"))
        if grant_dt is None and not ev:
            continue
        granted = any(e[0] == "final_grant" for e in ev)
        commenced = any(e[0] == "commenced" for e in ev)
        final_ccc = any(e[0] == "final_ccc" for e in ev)
        if granted and not commenced and len(ev):
            ev.append(("dormant_granted", SNAP, "engine", "absence_of_commencement", "inferred", "medium"))
        if final_ccc and any(e[0] == "first_sale" for e in ev):
            ev.append(("active_sales", max(e[1] for e in ev if e[0] in ("first_sale", "final_ccc")),
                       "engine", "derived", "inferred", "medium"))
        seen = set()
        for state, dt, src, ref, oi, conf in ev:
            tok = (state, dt)
            if tok in seen:
                continue
            seen.add(tok)
            rows.append({"case_key": key, "state": state, "entered": dt,
                         "source": src, "source_reference": ref,
                         "observed_or_inferred": oi, "confidence": conf})

    prog_path = SILVER / "construction_progress" / "construction_progress_events_phase_clean.csv"
    if not prog_path.exists():
        prog_path = SILVER / "construction_progress" / "construction_progress_events.csv"
    if prog_path.exists():
        prog = pd.read_csv(prog_path, dtype=str)
        prog["ccc_dt"] = pd.to_datetime(prog["ccc_dt"], errors="coerce")
        prog["units_certified"] = pd.to_numeric(prog["units_certified"], errors="coerce")
        prog["units"] = pd.to_numeric(prog["units"], errors="coerce")
        prog = prog.dropna(subset=["ccc_dt", "units_certified", "units"])
        prog = prog[prog["units"] > 0]
        prog["cum_units"] = prog.groupby("case_key")["units_certified"].cumsum()
        prog["cum_pct"] = prog["cum_units"] / prog["units"] * 100
        for threshold, state_name in [(25, "pct25"), (50, "pct50"), (75, "pct75")]:
            cross = prog[prog["cum_pct"] >= threshold].groupby("case_key")["ccc_dt"].min()
            for key, dt in cross.items():
                rows.append({"case_key": key, "state": state_name, "entered": dt,
                             "source": "bcms_ccc_units", "source_reference": f"cum_pct>={threshold}",
                             "observed_or_inferred": "observed", "confidence": "high"})
    frame = pd.DataFrame(rows)
    frame = frame[frame["entered"] <= SNAP]
    frame.to_csv(OUT / "states.csv", index=False)

    current = []
    for key, g in frame.sort_values("entered").groupby("case_key"):
        last = g.iloc[-1]
        days_in = (SNAP - last["entered"]).days
        order_idx = STATE_ORDER.index(last["state"]) if last["state"] in STATE_ORDER else 0
        current.append({
            "case_key": key, "current_state": last["state"], "state_entered_date": last["entered"],
            "days_in_state": days_in, "last_observed_event": last["state"],
            "last_observed_event_date": last["entered"], "source": last["source"],
            "source_reference": last["source_reference"],
            "observed_or_inferred": last["observed_or_inferred"], "confidence": last["confidence"],
            "next_possible_states": "|".join(STATE_ORDER[order_idx + 1:order_idx + 5]),
        })
    cur = pd.DataFrame(current)
    cur.to_csv(OUT / "current_state.csv", index=False)

    transitions = {}
    for src, dst in [("final_grant", "notice_filed"), ("final_grant", "commenced"),
                     ("notice_filed", "commenced"), ("commenced", "first_ccc"),
                     ("commenced", "pct25"), ("first_ccc", "pct25"), ("pct25", "pct50"),
                     ("pct50", "pct75"), ("pct75", "final_ccc"),
                     ("first_ccc", "partial_ccc"), ("partial_ccc", "final_ccc"),
                     ("first_ccc", "final_ccc"), ("final_ccc", "first_sale"),
                     ("commenced", "final_ccc"), ("partial_ccc", "first_sale"),
                     ("pct25", "final_ccc"), ("pct50", "final_ccc"), ("pct75", "first_sale")]:
        transitions[f"{src}->{dst}"] = transition_stats(src, dst, frame)
    (OUT / "transitions.json").write_text(json.dumps(transitions, indent=2), encoding="utf-8")

    reg = register.merge(cur[["case_key", "current_state", "state_entered_date"]], on="case_key", how="left")
    uncertainty = {}
    for label, col in [("grant", "GrantDate"), ("notice", None), ("commenced", None),
                       ("first_ccc", None), ("final_ccc", None)]:
        durations = []
        if col:
            if label == "grant":
                sub = frame[frame["state"] == "commenced"][["case_key", "entered"]].rename(
                    columns={"entered": "comm_dt"}).merge(
                    reg[["case_key", "GrantDate"]].rename(columns={"GrantDate": "grant_dt"}), on="case_key")
                durations = (sub["comm_dt"] - sub["grant_dt"]).dt.days.dropna().clip(lower=0, upper=4000)
        else:
            if label == "notice":
                a = frame[frame["state"] == "notice_filed"][["case_key", "entered"]].rename(columns={"entered": "a"})
                b = frame[frame["state"] == "commenced"][["case_key", "entered"]].rename(columns={"entered": "b"})
                durations = (a.merge(b, on="case_key")["b"] - a.merge(b, on="case_key")["a"]).dt.days.dropna().clip(lower=0, upper=4000)
            elif label == "commenced":
                a = frame[frame["state"] == "commenced"][["case_key", "entered"]].rename(columns={"entered": "a"})
                b = frame[frame["state"] == "first_ccc"][["case_key", "entered"]].rename(columns={"entered": "b"})
                durations = (a.merge(b, on="case_key")["b"] - a.merge(b, on="case_key")["a"]).dt.days.dropna().clip(lower=0, upper=4000)
            elif label == "first_ccc":
                a = frame[frame["state"] == "first_ccc"][["case_key", "entered"]].rename(columns={"entered": "a"})
                b = frame[frame["state"] == "final_ccc"][["case_key", "entered"]].rename(columns={"entered": "b"})
                durations = (a.merge(b, on="case_key")["b"] - a.merge(b, on="case_key")["a"]).dt.days.dropna().clip(lower=0, upper=4000)
            elif label == "final_ccc":
                a = frame[frame["state"] == "final_ccc"][["case_key", "entered"]].rename(columns={"entered": "a"})
                b = frame[frame["state"] == "first_sale"][["case_key", "entered"]].rename(columns={"entered": "b"})
                durations = (a.merge(b, on="case_key")["b"] - a.merge(b, on="case_key")["a"]).dt.days.dropna().clip(lower=0, upper=4000)
        entry = {"n": int(len(durations))}
        if len(durations):
            entry.update({"median_remaining": round(float(durations.median()), 1)})
            entry.update(km_intervals(durations))
            entry["interval_width_80pct"] = round(float(durations.quantile(0.9) - durations.quantile(0.1)), 1)
        uncertainty[label] = entry
    (OUT / "uncertainty_reduction.json").write_text(json.dumps(uncertainty, indent=2), encoding="utf-8")

    print(json.dumps({
        "n_states_rows": int(len(frame)),
        "n_schemes_in_state_machine": int(frame["case_key"].nunique()),
        "current_state_counts": cur["current_state"].value_counts().head(8).to_dict(),
        "transitions": {k: v.get("n") for k, v in transitions.items()},
        "uncertainty": uncertainty,
    }, indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
