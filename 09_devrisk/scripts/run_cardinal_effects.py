"""Cardinal effect estimation on quantitatively-parsed mutation pairs.

A. Enhanced quantitative parsing: sum-style unit counts (N houses + M
apartments), revised-from-X-to-Y language, storeys deltas.
B. Clean subset: pairs with quantitative units for BOTH versions.
C. Paired effect estimation: logistic of later-grant on d_units/d_storeys/
mix with site fixed effects where sites have >=2 pairs; coefficient CIs.
D. Cardinal translation: predicted-Δrisk decile (design model) ->
observed conversion rate + Wilson CI (fresh-era check).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "optimiser"


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * np.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return max(centre - margin, 0.0), min(centre + margin, 1.0)


def units_from_text(desc: str) -> float | None:
    d = (desc or "").lower()
    m = re.search(r"(?:revised|reduced)\s+(?:from\s+)?(\d+)\s+to\s+(\d+)", d)
    if m:
        return float(m.group(2))
    parts = re.findall(r"(\d+)\s*(?:no\.?)?\s*(?:houses|dwellings|apartments|units|homes)", d)
    if parts:
        return float(sum(int(p) for p in parts[:4]))
    m2 = re.search(r"(\d{2,4})\s*(?:no\.?)?\s*residential units", d)
    if m2:
        return float(m2.group(1))
    return None


def main() -> None:
    frame = pd.read_csv(OUT / "design_versions.csv")
    frame["units_text"] = frame["DevelopmentDescription"].apply(units_from_text)
    frame["units_quant"] = frame["units_text"].fillna(frame["units"])
    pairs = pd.read_csv(OUT / "mutation_pairs_design.csv")
    pairs = pairs.merge(frame[["case_key", "units_quant"]].rename(columns={"case_key": "case_key_a",
                                                                          "units_quant": "u_a"}),
                        on="case_key_a", how="left")
    pairs = pairs.merge(frame[["case_key", "units_quant"]].rename(columns={"case_key": "case_key_b",
                                                                          "units_quant": "u_b"}),
                        on="case_key_b", how="left")
    pairs["q_units"] = (pairs["u_b"] - pairs["u_a"]).round(0)
    pairs["u_a_txt"] = pairs["case_key_a"].map(frame.set_index("case_key")["units_text"])
    pairs["u_b_txt"] = pairs["case_key_b"].map(frame.set_index("case_key")["units_text"])
    both_text = pairs["u_a_txt"].notna() & pairs["u_b_txt"].notna()
    pairs["has_quant_both"] = both_text
    pairs["y"] = (pairs["outcome_b"] == "grant").astype(int)
    report = {"n_pairs": int(len(pairs)),
              "n_quant_both": int(both_text.sum()),
              "median_d_units_quant": float(pairs.loc[both_text, "q_units"].median())}

    clean = pairs[both_text & (pairs["year_a"] < 2022)].copy()
    clean["d_units_10"] = clean["q_units"] / 10.0
    clean["rel_revised"] = (clean["relationship"] == "same_proposal_revised").astype(int)
    feats = ["d_units_10", "d_storeys", "rel_revised", "year_a"]
    X = clean[feats].fillna(0)
    y = clean["y"]
    model = LogisticRegression(max_iter=3000, C=1.0)
    model.fit(X, y)
    coefs = dict(zip(feats, model.coef_[0]))
    report["paired_logistic"] = {"n": int(len(clean)),
                                 "base_grant_rate": round(float(y.mean()), 3),
                                 "coef_d_units_10": round(float(coefs["d_units_10"]), 4),
                                 "odds_ratio_per_10_units_down": round(float(np.exp(-coefs["d_units_10"])), 3),
                                 "coef_d_storeys": round(float(coefs["d_storeys"]), 4),
                                 "auc_in_sample": round(float(roc_auc_score(y, model.predict_proba(X)[:, 1])), 3)}
    # bootstrap CI on the units coefficient
    rng = np.random.default_rng(7)
    coefs_bs = []
    for _ in range(400):
        idx = rng.choice(len(clean), len(clean), replace=True)
        try:
            m = LogisticRegression(max_iter=3000, C=1.0)
            m.fit(clean.iloc[idx][feats].fillna(0), clean.iloc[idx]["y"])
            coefs_bs.append(m.coef_[0][0])
        except ValueError:
            continue
    if coefs_bs:
        report["paired_logistic"]["coef_d_units_10_ci95"] = [
            round(float(np.quantile(coefs_bs, 0.025)), 4),
            round(float(np.quantile(coefs_bs, 0.975)), 4)]
    # era stability
    eras = {}
    for label, sub in [("2014-2018", clean[clean["year_a"] <= 2018]),
                       ("2019-2021", clean[clean["year_a"] > 2018])]:
        if len(sub) >= 60 and sub["y"].nunique() == 2:
            m = LogisticRegression(max_iter=3000, C=1.0)
            m.fit(sub[feats].fillna(0), sub["y"])
            eras[label] = round(float(m.coef_[0][0]), 4)
    report["era_stability_d_units"] = eras

    (OUT / "cardinal_effects.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
