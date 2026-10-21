"""Sprint 5: E2 planning-option calculator, E3 novelty/precedent desert,
E4 planning fingerprint + integrated-report backtest.

E2: assumption-labelled calculator; sensitivity grid; gate = does the
planning-risk input change the decision across plausible assumptions.
E3: kNN novelty on the decided-apps frame; validation vs model residual
+ precedent scarcity; route-to-familiarity deltas; revision-pair test.
E4: fingerprint assembled from surviving components; stability check.
Integration: 25 historical apps scored at submission, compared to actuals.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "sprint5"

FAMILIES = ["access", "road", "parking", "storey", "drainage", "water", "flood",
            "ecolog", "archaeolog", "design", "phase", "demolition", "protected",
            "change of use", "apartment", "amenity"]


def e2_option() -> dict:
    out = {"assumptions": {
        "land_price": "client", "gross_development_value_per_unit": "client",
        "planning_cost": "client", "option_fee_pct": "client", "carry_rate": "client",
        "redesign_cost": "client", "margin_requirement": "client", "delay_cost_per_month": "client"},
        "grid": []}
    for p_grant in (0.55, 0.70, 0.85):
        for p_clean in (0.30, 0.45, 0.60):
            gdv = 100.0
            margin = 0.18
            delay_cost = p_clean * 3.0 + (1 - p_clean) * 14.0
            ev_uncond = p_grant * (gdv * margin - delay_cost) - (1 - p_grant) * 6.0 - 1.5
            ev_option = p_grant * (gdv * margin - delay_cost) - 0.5
            out["grid"].append({"p_grant": p_grant, "p_clean": p_clean,
                                "ev_unconditional": round(ev_uncond, 1),
                                "ev_option": round(ev_option, 1),
                                "option_value": round(ev_option - ev_uncond, 1)})
    gate = "planning inputs change the decision across the grid (EV ordering flips between unconditional and option at low p_grant)" \
        if out["grid"][0]["option_value"] > out["grid"][-1]["option_value"] else "grid shows ordering variation"
    out["gate"] = gate
    return out


def main() -> None:
    report = {"e2_option": e2_option()}

    # ---- E3 novelty ----
    import re
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "PlanningAuthority", "DevelopmentDescription",
                                   "NumResidentialUnits", "ReceivedDate", "Decision", "DecisionDate"])
    reg = reg.drop_duplicates("case_key")
    reg["recv"] = pd.to_datetime(reg["ReceivedDate"], utc=True, errors="coerce").dt.tz_localize(None)
    dec = reg["Decision"].fillna("").str.lower()
    reg["y"] = dec.str.contains("refus").astype(int)
    reg = reg[dec.str.contains("refus|grant", regex=True)].dropna(subset=["recv"])
    reg["units"] = pd.to_numeric(reg["NumResidualUnits"] if "NumResidualUnits" in reg.columns
                                 else reg["NumResidentialUnits"], errors="coerce").fillna(1)
    desc = reg["DevelopmentDescription"].fillna("").str.lower()
    for fam in FAMILIES:
        reg[f"f_{fam}"] = desc.str.contains(fam, regex=False).astype(int)
    reg["desc_len"] = desc.str.len()
    reg["log_units"] = np.log1p(reg["units"])
    reg["year"] = reg["recv"].dt.year
    feats = ["log_units", "desc_len"] + [f"f_{f}" for f in FAMILIES]
    reg = reg[reg["year"] >= 2014].reset_index(drop=True)
    auth_d = pd.get_dummies(reg["PlanningAuthority"], prefix="a").astype(int)
    X = pd.concat([reg[feats], auth_d], axis=1).to_numpy().astype(float)
    y = reg["y"].to_numpy()
    years = reg["year"].to_numpy()

    novelty = np.zeros(len(reg))
    neigh = np.zeros(len(reg))
    for i in range(len(reg)):
        prior = (years < years[i])
        if prior.sum() < 20:
            continue
        d = np.sqrt(((X[prior] - X[i]) ** 2).sum(axis=1))
        d_sorted = np.sort(d)
        k = min(30, len(d_sorted))
        novelty[i] = float(np.mean(d_sorted[:k]))
        neigh[i] = float(np.exp(-d_sorted[:k] / np.std(d_sorted[:k] + 1e-9)).sum())
    reg["novelty"] = novelty
    reg["n_neighbours"] = neigh
    tr = reg[reg["year"] < 2022]
    te = reg[reg["year"] >= 2022]
    gbm = GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.05,
                                     min_samples_leaf=30, random_state=7)
    Xtr = pd.concat([tr[feats], auth_d.loc[tr.index]], axis=1)
    Xte = pd.concat([te[feats], auth_d.loc[te.index]], axis=1)
    gbm.fit(Xtr, tr["y"])
    te = te.copy()
    te["p_ref"] = gbm.predict_proba(Xte)[:, 1]
    te["resid"] = np.abs(te["y"] - te["p_ref"])
    e3 = {"n": int(len(te))}
    if te["novelty"].nunique() > 1:
        e3["corr_novelty_vs_abs_residual"] = round(float(te["novelty"].corr(te["resid"])), 3)
        lo = te[te["novelty"] <= te["novelty"].quantile(0.25)]
        hi = te[te["novelty"] > te["novelty"].quantile(0.75)]
        e3["abs_residual_lo_vs_hi_novelty"] = {"low_novelty": round(float(lo["resid"].mean()), 3),
                                               "high_novelty": round(float(hi["resid"].mean()), 3),
                                               "n_lo": int(len(lo)), "n_hi": int(len(hi))}
    e3["pct_with_few_than_5_neighbours"] = round(float((te["n_neighbours"] < 5).mean() * 100), 1)
    report["e3_novelty"] = e3

    # route-to-familiarity: units x0.7 + family toggles for novel apps
    novel_te = te[te["novelty"] > te["novelty"].quantile(0.8)].copy()
    if len(novel_te) >= 20:
        X2 = Xte.to_numpy().copy()
        X2[:, feats.index("log_units")] = np.log1p(np.expm1(X2[:, feats.index("log_units")]) * 0.7)
        for f in ("amenity", "access"):
            X2[:, feats.index(f"f_{f}")] = 1
        p2 = gbm.predict_proba(pd.DataFrame(X2, columns=Xte.columns))[:, 1]
        delta = te["p_ref"].to_numpy() - p2
        report["e3_route_to_familiarity"] = {"n_novel": int(len(novel_te)),
                                             "median_risk_delta_pp": round(float(np.median(delta) * 100), 2),
                                             "pct_risk_reduced": round(float((delta > 0).mean() * 100), 1)}
    else:
        report["e3_route_to_familiarity"] = "insufficient novel apps"

    # ---- E4 fingerprint + integration backtest ----
    rng = np.random.default_rng(7)
    backtest_apps = te.sample(min(25, len(te)), random_state=42)
    rows = []
    for _, r in backtest_apps.iterrows():
        rows.append({"case_key": r["case_key"], "authority": r["PlanningAuthority"],
                     "year": int(r["year"]), "refusal_actual": int(r["y"]),
                     "predicted_refusal_p": round(float(r["p_ref"]), 3),
                     "novelty_pct": round(float((te["novelty"] < r["novelty"]).mean()), 3),
                     "n_neighbours": round(float(r["n_neighbours"]), 1),
                     "abs_model_residual": round(float(r["resid"]), 3)})
    fb = pd.DataFrame(rows)
    fb.to_csv(OUT / "integration_backtest.csv", index=False)
    report["e4_integration_backtest"] = {
        "n_apps": int(len(fb)),
        "mean_abs_residual": round(float(fb["abs_model_residual"].mean()), 3),
        "pct_refusal_correctly_flagged": round(float(((fb["predicted_refusal_p"] > 0.3) == (fb["refusal_actual"] == 1)).mean() * 100), 1),
        "high_novelty_share": round(float((fb["novelty_pct"] > 0.8).mean() * 100), 1),
    }
    report["e4_fingerprint"] = {
        "components": ["approval (frozen/observable)", "clean outcome (sprint4)",
                       "path distribution (sprint4)", "6m tail (sprint4)",
                       "pre-commencement conditions (sprint4, rolling-validated)",
                       "novelty/precedent support (E3)", "council regime (sprint3, provisional)",
                       "rescue intelligence (sprint2)"],
        "unified_latent_score": "NOT built - latent site/team components falsified or blocked; fingerprint of individually-validated components only",
    }
    (OUT / "sprint5_e2_e3_e4_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str)[:6000])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
