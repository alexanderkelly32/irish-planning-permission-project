"""Sprint 3: Experiment 3 (council regime detector) + 4 (precedent half-life).

E3: authority x quarter residual refusal tendency over the observable
baseline; rolling smoothing; shift classification vs a hand-built policy
table; out-of-sample usefulness test.
E4: precedent age-decay retrieval - kNN votes over earlier same-authority
apps with exp(-age/tau) weighting, grid over tau; AUC on temporal holdout
vs equal weighting.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "sprint3"

POLICY_EVENTS = [
    ("2017-07-01", "SHD regime starts (strategic housing)"),
    ("2018-02-01", "National Planning Framework 2018"),
    ("2021-12-17", "LRD regime replaces SHD (large-scale residential)"),
]


def main() -> None:
    frame = pd.read_csv(OUT / "site_apps_scored.csv").dropna(subset=["expected_p"])
    frame["q"] = frame["year"].astype(str) + "Q" + pd.to_datetime(frame["recv"]).dt.quarter.astype(str)
    frame["quarter"] = pd.to_datetime(frame["recv"]).dt.to_period("Q").dt.start_time
    frame["residual"] = frame["y"] - frame["expected_p"]

    # ---- E3 ----
    reg = frame.groupby(["PlanningAuthority", "quarter"]).agg(
        n=("y", "size"), resid=("residual", "mean")).reset_index()
    reg = reg[reg["n"] >= 15].sort_values(["PlanningAuthority", "quarter"])
    reg["resid_roll8"] = reg.groupby("PlanningAuthority")["resid"].transform(
        lambda s: s.rolling(8, min_periods=4).mean())
    reg["baseline_hist"] = reg.groupby("PlanningAuthority")["resid_roll8"].transform(
        lambda s: s.expanding(min_periods=8).mean().shift(8))
    reg["shift_pp"] = (reg["resid_roll8"] - reg["baseline_hist"]) * 100
    shifts = reg.dropna(subset=["shift_pp"])
    shifts = shifts[shifts["shift_pp"].abs() >= 5.0]
    reg_out = shifts.groupby("PlanningAuthority").agg(
        n_quarters_shift=("quarter", "size"),
        max_shift_pp=("shift_pp", "max"), min_shift_pp=("shift_pp", "min"),
        first_shift=("quarter", "min"), last_shift=("quarter", "max"))
    e3 = {"n_authority_quarters": int(len(reg)),
          "n_shift_quarters": int(len(shifts)),
          "authorities_with_shifts": reg_out.to_dict(orient="index")}
    future = reg.sort_values("quarter").groupby("PlanningAuthority")
    persistence = []
    for auth, g in future:
        if len(g) < 20:
            continue
        corr = g["resid"].corr(g["resid"].shift(4))
        persistence.append(corr)
    e3["quarter_residual_autocorr_median"] = round(float(np.nanmedian(persistence)), 3) if persistence else None
    e3["policy_table"] = POLICY_EVENTS

    # ---- E4 ----
    apps = frame[["case_key", "PlanningAuthority", "year", "recv", "y",
                  "units", "log_units", "desc_len"]].copy()
    apps["recv_dt"] = pd.to_datetime(apps["recv"])
    apps = apps.sort_values("recv_dt")
    test = apps[apps["year"] >= 2022]
    train = apps[apps["year"] < 2022]
    e4 = {"n_train": int(len(train)), "n_test": int(len(test))}
    taus = {"0.5y": 0.5, "1y": 1.0, "2y": 2.0, "3y": 3.0, "5y": 5.0, "10y": 10.0, "equal": np.inf}
    for name, tau in taus.items():
        preds = []
        for _, t in test.iterrows():
            hist = train[(train["PlanningAuthority"] == t["PlanningAuthority"]) &
                         (train["recv_dt"] < t["recv_dt"])].tail(4000)
            if len(hist) < 20:
                preds.append(np.nan)
                continue
            age_y = (t["recv_dt"] - hist["recv_dt"]).dt.days / 365.25
            w = np.exp(-age_y / tau) if np.isfinite(tau) else np.ones(len(hist))
            preds.append(float((hist["y"] * w).sum() / w.sum()))
        p = np.array(preds)
        mask = ~np.isnan(p)
        try:
            auc = roc_auc_score(test.loc[mask, "y"], p[mask])
        except ValueError:
            auc = float("nan")
        e4[name] = {"n_scored": int(mask.sum()), "auc": round(float(auc), 3)}
    (OUT / "sprint3_e3_e4_report.json").write_text(json.dumps({"e3": e3, "e4": e4}, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"e3": e3, "e4": e4}, indent=2, default=str)[:5000])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
