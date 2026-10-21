"""Landmark tests: SPV incorporation + post-grant amendment activity.

Strict landmark protocol: coverage, timing vs grant/commencement,
remaining-time distribution before vs after, 80% width reduction,
P(commence within 3/6/12m), elapsed-time-matched controls, temporal
split where n supports. Pre-registered gate: >=20% width reduction OR
>=15pp horizon-probability shift. Else falsified.
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
OUT = SILVER / "landmarks"
SNAP = pd.Timestamp("2026-10-01")

GATE_WIDTH = 20.0
GATE_HORIZON_PP = 15.0


def remaining_width(vals):
    return float(np.quantile(vals, 0.9) - np.quantile(vals, 0.1))


def main() -> None:
    clean = pd.read_csv(SILVER / "dq" / "labels_clean.csv", dtype=str)
    clean_keys = set(clean["case_key"])
    labels = pd.read_csv(SILVER / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    labels = labels[labels["activation_linked"].astype(str).str.lower() == "true"]
    labels["activation"] = pd.to_numeric(labels["activation_days"], errors="coerce")
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                               columns=["case_key", "GrantDate", "ReceivedDate",
                                        "ITMEasting", "ITMNorthing"])
    register["grant_dt"] = pd.to_datetime(register["GrantDate"], utc=True, errors="coerce").dt.tz_localize(None)
    register["recv_dt"] = pd.to_datetime(register["ReceivedDate"], utc=True, errors="coerce").dt.tz_localize(None)
    register = register.drop_duplicates("case_key")
    base = labels.merge(register, on="case_key", how="inner")
    base = base[base["case_key"].isin(clean_keys)]
    base = base.dropna(subset=["grant_dt", "activation"])
    base["comm_dt"] = base["grant_dt"] + pd.to_timedelta(base["activation"], unit="D")
    base = base[base["comm_dt"] <= SNAP]
    base["grant_year"] = base["grant_dt"].dt.year
    base = base[base["grant_year"] >= 2016]

    report = {}

    # ---- SPV incorporation ----
    dev = pd.read_csv(SILVER / "developer_groups.csv", dtype=str)
    dev = dev.dropna(subset=["company_number", "group_id"])
    comps = pd.read_csv(settings.RAW_DIR / "companies.csv.zip", dtype=str,
                        usecols=["company_num", "company_reg_date"], compression="zip")
    comps["reg_dt"] = pd.to_datetime(comps["company_reg_date"], errors="coerce")
    comps = comps.drop_duplicates("company_num")
    reg_by_num = comps.dropna(subset=["reg_dt"]).set_index("company_num")["reg_dt"]
    dev["reg_dt"] = dev["company_number"].map(reg_by_num)
    dev = dev.dropna(subset=["reg_dt"])
    grp_companies = dev.groupby("group_id")["company_number"].nunique()
    grp_clean_schemes = dev[dev["case_key"].isin(clean_keys)].groupby("group_id")["case_key"].nunique()

    spv_events = []
    for _, r in base.iterrows():
        g = dev[dev["case_key"] == r["case_key"]]
        if g.empty:
            continue
        gid = g["group_id"].iloc[0]
        group_regs = dev[dev["group_id"] == gid]["reg_dt"]
        post_grant = group_regs[(group_regs >= r["grant_dt"] - pd.Timedelta(days=30)) &
                                (group_regs <= r["comm_dt"])]
        if len(post_grant):
            spv_events.append({"case_key": r["case_key"], "event_dt": post_grant.min(),
                               "grant_dt": r["grant_dt"], "comm_dt": r["comm_dt"],
                               "grant_year": r["grant_year"],
                               "group_clean_schemes": grp_clean_schemes.get(gid, 1)})
    spv = pd.DataFrame(spv_events)
    spv["elapsed"] = (spv["event_dt"] - spv["grant_dt"]).dt.days
    spv["remaining"] = (spv["comm_dt"] - spv["event_dt"]).dt.days

    # elapsed-matched controls
    spv_ctrl = []
    for _, e in spv.iterrows():
        ctrl = base[(base["case_key"] != e["case_key"]) &
                    (base["grant_year"].between(e["grant_year"] - 1, e["grant_year"] + 1))]
        ctrl = ctrl[(ctrl["grant_dt"] + pd.Timedelta(days=e["elapsed"])) < ctrl["comm_dt"]]
        for _, c in ctrl.iterrows():
            spv_ctrl.append({"case_key": c["case_key"], "elapsed": e["elapsed"],
                             "remaining": (c["comm_dt"] - (c["grant_dt"] + pd.Timedelta(days=e["elapsed"]))).days,
                             "grant_year": c["grant_year"]})
    spv_ctrl = pd.DataFrame(spv_ctrl)
    report["spv_incorporation"] = {
        "coverage": {"n_events": int(len(spv)), "n_schemes": int(spv["case_key"].nunique()),
                     "share_of_clean": round(spv["case_key"].nunique() / len(base) * 100, 1),
                     "precision_share_unambiguous_group": round(
                         float((spv["group_clean_schemes"] == 1).mean() * 100), 1)},
        "timing": {"median_days_from_grant": round(float(spv["elapsed"].median()), 1),
                   "median_days_before_commencement": round(float(spv["remaining"].median()), 1)},
        "before_after": {
            "evented_n": int(len(spv)),
            "evented_width80": round(remaining_width(spv["remaining"]), 1),
            "evented_median_remaining": round(float(spv["remaining"].median()), 1),
            "evented_within_3m": round(float((spv["remaining"] <= 91).mean() * 100), 1),
            "evented_within_6m": round(float((spv["remaining"] <= 183).mean() * 100), 1),
            "evented_within_12m": round(float((spv["remaining"] <= 365).mean() * 100), 1),
            "matched_control_n": int(len(spv_ctrl)),
            "control_width80": round(remaining_width(spv_ctrl["remaining"]), 1),
            "control_median_remaining": round(float(spv_ctrl["remaining"].median()), 1),
            "control_within_3m": round(float((spv_ctrl["remaining"] <= 91).mean() * 100), 1),
            "control_within_6m": round(float((spv_ctrl["remaining"] <= 183).mean() * 100), 1),
            "control_within_12m": round(float((spv_ctrl["remaining"] <= 365).mean() * 100), 1),
            "width_reduction_pct": round((1 - remaining_width(spv["remaining"]) /
                                          remaining_width(spv_ctrl["remaining"])) * 100, 1) if len(spv_ctrl) else None,
            "horizon_12m_delta_pp": round(float((spv["remaining"] <= 365).mean() * 100 -
                                               (spv_ctrl["remaining"] <= 365).mean() * 100), 1) if len(spv_ctrl) else None,
        },
    }
    if len(spv[spv["grant_year"] < 2022]) >= 15 and len(spv[spv["grant_year"] >= 2022]) >= 15:
        report["spv_incorporation"]["temporal_split"] = {
            "pre2022_evented_median_remaining": round(float(spv[spv["grant_year"] < 2022]["remaining"].median()), 1),
            "post2022_evented_median_remaining": round(float(spv[spv["grant_year"] >= 2022]["remaining"].median()), 1),
        }

    # ---- Amendment activity (ITM proximity < 250m) ----
    am_rows = []
    coords = base[["case_key", "grant_dt", "comm_dt", "recv_dt", "ITMEasting", "ITMNorthing",
                   "grant_year"]].dropna(subset=["ITMEasting", "ITMNorthing"]).copy()
    for _, r in base.dropna(subset=["ITMEasting", "ITMNorthing"]).iterrows():
        dist = np.sqrt((coords["ITMEasting"] - r["ITMEasting"]) ** 2 +
                       (coords["ITMNorthing"] - r["ITMNorthing"]) ** 2)
        others = coords[(dist < 250) & (coords["case_key"] != r["case_key"])]
        others = others[(others["recv_dt"] >= r["grant_dt"]) & (others["recv_dt"] <= r["comm_dt"])]
        if len(others):
            am_rows.append({"case_key": r["case_key"], "event_dt": others["recv_dt"].min(),
                            "grant_dt": r["grant_dt"], "comm_dt": r["comm_dt"],
                            "grant_year": r["grant_year"]})
    am = pd.DataFrame(am_rows)
    am["elapsed"] = (am["event_dt"] - am["grant_dt"]).dt.days
    am["remaining"] = (am["comm_dt"] - am["event_dt"]).dt.days
    am_ctrl = []
    for _, e in am.iterrows():
        ctrl = base[(base["case_key"] != e["case_key"]) &
                    (base["grant_year"].between(e["grant_year"] - 1, e["grant_year"] + 1))]
        ctrl = ctrl[(ctrl["grant_dt"] + pd.Timedelta(days=e["elapsed"])) < ctrl["comm_dt"]]
        for _, c in ctrl.iterrows():
            am_ctrl.append({"case_key": c["case_key"], "elapsed": e["elapsed"],
                            "remaining": (c["comm_dt"] - (c["grant_dt"] + pd.Timedelta(days=e["elapsed"]))).days,
                            "grant_year": c["grant_year"]})
    am_ctrl = pd.DataFrame(am_ctrl)
    report["amendment_activity"] = {
        "coverage": {"n_events": int(len(am)), "n_schemes": int(am["case_key"].nunique()),
                     "share_of_clean": round(am["case_key"].nunique() / len(base) * 100, 1)},
        "timing": {"median_days_from_grant": round(float(am["elapsed"].median()), 1),
                   "median_days_before_commencement": round(float(am["remaining"].median()), 1)},
        "before_after": {
            "evented_n": int(len(am)),
            "evented_width80": round(remaining_width(am["remaining"]), 1),
            "evented_median_remaining": round(float(am["remaining"].median()), 1),
            "evented_within_12m": round(float((am["remaining"] <= 365).mean() * 100), 1),
            "matched_control_n": int(len(am_ctrl)),
            "control_width80": round(remaining_width(am_ctrl["remaining"]), 1),
            "control_median_remaining": round(float(am_ctrl["remaining"].median()), 1),
            "control_within_12m": round(float((am_ctrl["remaining"] <= 365).mean() * 100), 1),
            "width_reduction_pct": round((1 - remaining_width(am["remaining"]) /
                                          remaining_width(am_ctrl["remaining"])) * 100, 1) if len(am_ctrl) else None,
            "horizon_12m_delta_pp": round(float((am["remaining"] <= 365).mean() * 100 -
                                               (am_ctrl["remaining"] <= 365).mean() * 100), 1) if len(am_ctrl) else None,
        },
    }

    gates = {}
    for name in ("spv_incorporation", "amendment_activity"):
        ba = report[name]["before_after"]
        w = ba.get("width_reduction_pct")
        h = ba.get("horizon_12m_delta_pp")
        passed = (w is not None and w >= GATE_WIDTH) or (h is not None and abs(h) >= GATE_HORIZON_PP)
        gates[name] = {"width_reduction_pct": w, "horizon_12m_delta_pp": h,
                       "gate": f">={GATE_WIDTH}% width or >= {GATE_HORIZON_PP}pp horizon",
                       "verdict": "keep" if passed else "falsified"}
    report["gates"] = gates
    (OUT / "landmark_tests_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
