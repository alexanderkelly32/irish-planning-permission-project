"""Cardinal push 2: theme-conditional effects + variance profiling.

If the aggregate unit effect is zero, the signal may be theme-conditional
(density-refused schemes respond to unit cuts; design-refused respond to
storeys). Also profile the treatment variance: how many revisions actually
change units/storeys, and by how much.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "optimiser"

THEMES = {
    "density_scale": r"density|scale|overdevelop|height|storey|units|number of|massing",
    "design": r"design|visual|amenity|character|appearance|material|finish|layout",
    "access_roads": r"access|road|traffic|junction|parking|turning",
    "water_flood": r"flood|drainage|water|sewer|attenuation",
    "ecology_heritage": r"ecolog|habitat|tree|natura|archaeolog|heritage|protected",
    "other": r".*",
}


def theme_of(d):
    for name, pat in THEMES.items():
        if name == "other":
            continue
        if re.search(pat, d or "", re.I):
            return name
    return "other"


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
    pairs = pd.read_csv(OUT / "mutation_pairs_design.csv")
    pairs = pairs.merge(frame[["case_key", "units_text"]].rename(columns={"case_key": "case_key_a",
                                                                          "units_text": "u_a_txt"}),
                        on="case_key_a", how="left")
    pairs = pairs.merge(frame[["case_key", "units_text"]].rename(columns={"case_key": "case_key_b",
                                                                          "units_text": "u_b_txt"}),
                        on="case_key_b", how="left")
    pairs = pairs.merge(frame[["case_key", "DevelopmentDescription"]].rename(
        columns={"case_key": "case_key_a", "DevelopmentDescription": "desc_a"}), on="case_key_a", how="left")
    both = pairs[pairs["u_a_txt"].notna() & pairs["u_b_txt"].notna()].copy()
    both["d_units"] = (both["u_b_txt"] - both["u_a_txt"])
    both["y"] = (both["outcome_b"] == "grant").astype(int)
    both["theme_a"] = both["desc_a"].apply(theme_of)
    report = {"n_quant_pairs": int(len(both)),
              "delta_units_distribution": {
                  "pct_nonzero": round(float((both["d_units"] != 0).mean() * 100), 1),
                  "pct_abs_ge5": round(float((both["d_units"].abs() >= 5).mean() * 100), 1),
                  "p10": float(both["d_units"].quantile(0.1)),
                  "p25": float(both["d_units"].quantile(0.25)),
                  "p75": float(both["d_units"].quantile(0.75)),
                  "p90": float(both["d_units"].quantile(0.90)),
                  "pct_units_up": round(float((both["d_units"] > 0).mean() * 100), 1),
                  "pct_units_down": round(float((both["d_units"] < 0).mean() * 100), 1),
                  "pct_unchanged": round(float((both["d_units"] == 0).mean() * 100), 1)},
              "theme_conditional": {}}
    both = both[both["year_a"] < 2022]
    for theme, sub in both.groupby("theme_a"):
        if len(sub) < 50 or sub["y"].nunique() < 2:
            continue
        sub = sub.copy()
        sub["d_units_10"] = sub["d_units"] / 10.0
        m = LogisticRegression(max_iter=3000, C=1.0)
        m.fit(sub[["d_units_10", "d_storeys"]].fillna(0), sub["y"])
        report["theme_conditional"][theme] = {
            "n": int(len(sub)),
            "base_grant": round(float(sub["y"].mean()), 3),
            "coef_d_units_10": round(float(m.coef_[0][0]), 4),
            "odds_ratio_10units_down": round(float(np.exp(-m.coef_[0][0])), 3),
            "coef_d_storeys": round(float(m.coef_[0][1]), 4),
            "pct_units_changed": round(float((sub["d_units"] != 0).mean() * 100), 1),
        }
    (OUT / "cardinal_theme_effects.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
