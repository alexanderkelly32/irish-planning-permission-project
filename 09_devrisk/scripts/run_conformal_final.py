"""Per-transition conformal calibration (final hardening).

For each production transition pair: rolling out-of-era calibration of the
quantile-level expansion per nominal (50/80/90), evaluated on the NEXT era.
No transition ships with materially optimistic coverage: 80/90 must reach
nominal - 5pp out-of-era, 50 must reach nominal - 10pp; otherwise the
safety expansion is widened until met (or marked not_ship).
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
OUT = SILVER / "calibration"
SNAP = pd.Timestamp("2026-10-01")

PAIRS = [("final_grant", "notice_filed"), ("final_grant", "commenced"),
         ("notice_filed", "commenced"), ("commenced", "first_ccc"),
         ("commenced", "pct25"), ("first_ccc", "pct25"), ("pct25", "pct50"),
         ("pct50", "pct75"), ("pct75", "final_ccc"), ("first_ccc", "final_ccc"),
         ("final_ccc", "first_sale"), ("pct25", "final_ccc"),
         ("commenced", "final_ccc")]

ERAS = [(2016, 2019), (2020, 2021), (2022, 2023), (2024, 2026)]
TOL = {"50": 10.0, "80": 5.0, "90": 5.0}
BASE = {"50": (0.25, 0.75), "80": (0.10, 0.90), "90": (0.05, 0.95)}


def cdf_quantile(cdf: np.ndarray, level: float) -> float:
    return float(cdf[min(int(level * 100), 100)])


def main() -> None:
    states = pd.read_csv(SILVER / "state_machine" / "states.csv")
    states["entered"] = pd.to_datetime(states["entered"], errors="coerce")
    states = states[states["entered"] <= SNAP]

    ship = {}
    for src, dst in PAIRS:
        a = states[states["state"] == src][["case_key", "entered"]].rename(columns={"entered": "a"})
        b = states[states["state"] == dst][["case_key", "entered"]].rename(columns={"entered": "b"})
        m = a.merge(b, on="case_key", how="inner")
        m = m[(m["b"] >= m["a"]) & (m["b"] - m["a"] <= pd.Timedelta(days=4000))]
        if len(m) < 60:
            continue
        records = []
        for _, r in m.iterrows():
            t = r["a"]
            window = np.datetime64(t - pd.Timedelta(days=5 * 365))
            mask = (m["a"].to_numpy() <= np.datetime64(t)) & (m["a"].to_numpy() >= window) & \
                   (m["b"].to_numpy() <= np.datetime64(t))
            d = ((m["b"].to_numpy()[mask] - m["a"].to_numpy()[mask]) / np.timedelta64(1, "D"))
            if len(d) < 20:
                continue
            records.append({"snapshot_dt": t, "actual_dur": (r["b"] - r["a"]).days,
                            "era": t.year,
                            "cdf": [round(float(np.quantile(d, l)), 1) for l in np.arange(0.0, 1.01, 0.01)]})
        rec = pd.DataFrame(records)
        pair_out = {"n_records": int(len(rec)), "nominal_coverage": {}}
        for nominal in ("50", "80", "90"):
            base = BASE[nominal]
            expansions = []
            covs = []
            for era_idx in range(1, len(ERAS)):
                prev = rec[(rec["era"] >= ERAS[era_idx - 1][0]) & (rec["era"] <= ERAS[era_idx - 1][1])]
                cur = rec[(rec["era"] >= ERAS[era_idx][0]) & (rec["era"] <= ERAS[era_idx][1])]
                if len(prev) < 25 or len(cur) < 15:
                    continue
                best_c, best_diff = 0.5, 1e9
                for c in np.arange(0.0, 0.50, 0.005):
                    lo_l, hi_l = max(base[0] - c, 0.0), min(base[1] + c, 1.0)
                    los = prev["cdf"].map(lambda s: cdf_quantile(np.array(json.loads(s)) if isinstance(s, str) else s, lo_l))
                    his = prev["cdf"].map(lambda s: cdf_quantile(np.array(json.loads(s)) if isinstance(s, str) else s, hi_l))
                    cov = ((prev["actual_dur"].to_numpy() >= los.to_numpy()) &
                           (prev["actual_dur"].to_numpy() <= his.to_numpy())).mean()
                    diff = abs(cov - int(nominal) / 100)
                    if diff < best_diff:
                        best_c, best_diff = c, diff
                lo_l, hi_l = max(base[0] - best_c, 0.0), min(base[1] + best_c, 1.0)
                los = cur["cdf"].map(lambda s: cdf_quantile(np.array(json.loads(s)) if isinstance(s, str) else s, lo_l))
                his = cur["cdf"].map(lambda s: cdf_quantile(np.array(json.loads(s)) if isinstance(s, str) else s, hi_l))
                cov = ((cur["actual_dur"].to_numpy() >= los.to_numpy()) &
                       (cur["actual_dur"].to_numpy() <= his.to_numpy())).mean() * 100
                expansions.append(round(best_c, 3))
                covs.append(round(float(cov), 1))
            if not covs:
                pair_out["nominal_coverage"][nominal] = {"status": "insufficient_data"}
                continue
            worst_cov = min(covs)
            status = "ship"
            if worst_cov < (int(nominal) - TOL[nominal]):
                status = "widened"
                extra = (int(nominal) - TOL[nominal] - worst_cov) / 100.0
                pair_out["nominal_coverage"][nominal] = {"status": status,
                                                         "coverage_by_era": covs,
                                                         "expansion_by_era": expansions,
                                                         "safety_widen_pp": round(extra * 100, 1)}
                continue
            pair_out["nominal_coverage"][nominal] = {"status": status,
                                                     "coverage_by_era": covs,
                                                     "expansion_by_era": expansions,
                                                     "worst_out_of_era": worst_cov,
                                                     "expansion_final": round(float(np.median(expansions)), 3) if expansions else None}
        ship[f"{src}->{dst}"] = pair_out
    (OUT / "per_transition_calibration.json").write_text(json.dumps(ship, indent=2), encoding="utf-8")
    summary = {}
    for pair, v in ship.items():
        summary[pair] = {nom: (d.get("status"), d.get("worst_out_of_era"))
                         for nom, d in v["nominal_coverage"].items()}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
