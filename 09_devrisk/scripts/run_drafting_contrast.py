"""Drafting contrast per refusal theme.

For each refusal theme of version A (refused) in refusal->revised pairs:
  - v2 grant rate by description length ratio (trim <0.9 / similar / expand >1.1)
  - Wilson CIs, era split (version-A year <2022 vs >=2022)
  - per-family language additions (access, drainage, etc.) vs v2 grant rate
Overall trimmed-vs-expanded contrast (the 91.5 vs 66.9 line) recomputed.

Outputs: silver/optimiser/drafting_contrast.json + drafting_contrast.csv
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SILVER = ROOT / "09_devrisk" / "data" / "silver"
PAIRS = SILVER / "sprint2" / "refusal_grant_pairs.csv"
OUT = SILVER / "optimiser"

FAMILIES = ["fam_access_roads_added", "fam_parking_added", "fam_height_storeys_added",
            "fam_open_space_amenity_added", "fam_drainage_uisce_added", "fam_flood_added",
            "fam_ecology_added", "fam_archaeology_added", "fam_design_material_added",
            "fam_phasing_added", "fam_density_scale_added", "fam_social_housing_added"]
FAM_LABEL = {f: f.replace("fam_", "").replace("_added", "") for f in FAMILIES}


def wilson(k: float, n: int, z: float = 1.96):
    if n == 0:
        return None, 0.0, 1.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, max(centre - half, 0.0), min(centre + half, 1.0)


def rate(g: pd.DataFrame, col: str = "granted") -> dict:
    n = len(g)
    if n == 0:
        return {"n": 0, "rate": None, "ci_lo": None, "ci_hi": None}
    k = int(g[col].sum())
    p, lo, hi = wilson(k, n)
    return {"n": n, "rate": round(float(p), 3), "ci_lo": round(float(lo), 3), "ci_hi": round(float(hi), 3)}


def main() -> None:
    d = pd.read_csv(PAIRS, low_memory=False)
    d["granted"] = (d["decision_2"].astype(str).str.lower() == "grant").astype(int)
    d["theme"] = d["theme"].fillna("unknown").astype(str)
    d["ratio"] = pd.to_numeric(d["desc_len_ratio"], errors="coerce")
    d["year_1"] = pd.to_numeric(d["year_1"], errors="coerce")
    d["bucket"] = pd.cut(d["ratio"], [-np.inf, 0.9, 1.1, np.inf], labels=["trim", "similar", "expand"])
    for f in FAMILIES:
        d[f] = pd.to_numeric(d[f], errors="coerce").fillna(0).astype(int)

    report = {"n_pairs": int(len(d)), "n_with_theme": int(d["theme"].ne("unknown").sum())}
    # overall contrast
    report["overall"] = {}
    for bucket in ("trim", "similar", "expand"):
        report["overall"][bucket] = rate(d[d["bucket"] == bucket])
    report["overall"]["trim_vs_not"] = {"trim": rate(d[d["bucket"] == "trim"]),
                                        "other": rate(d[d["bucket"] != "trim"])}
    report["overall"]["expand_vs_not"] = {"expand": rate(d[d["bucket"] == "expand"]),
                                          "other": rate(d[d["bucket"] != "expand"])}
    for era_name, era in (("pre2022", d["year_1"] < 2022), ("2022plus", d["year_1"] >= 2022)):
        sub = d[era]
        report["overall"][f"era_{era_name}"] = {
            "trim": rate(sub[sub["bucket"] == "trim"]),
            "similar": rate(sub[sub["bucket"] == "similar"]),
            "expand": rate(sub[sub["bucket"] == "expand"]),
        }
    # per-theme
    themes = sorted(t for t in d["theme"].unique() if t != "unknown")
    per_theme = {}
    rows = []
    for t in themes:
        td = d[d["theme"] == t]
        entry = {"n": int(len(td)), "n_granted": int(td["granted"].sum())}
        for bucket in ("trim", "similar", "expand"):
            entry[bucket] = rate(td[td["bucket"] == bucket])
        entry["eras"] = {
            "pre2022": {"trim": rate(td[(td["year_1"] < 2022) & (td["bucket"] == "trim")]),
                        "expand": rate(td[(td["year_1"] < 2022) & (td["bucket"] == "expand")])},
            "2022plus": {"trim": rate(td[(td["year_1"] >= 2022) & (td["bucket"] == "trim")]),
                         "expand": rate(td[(td["year_1"] >= 2022) & (td["bucket"] == "expand")])},
        }
        # family additions vs grant rate
        fams = {}
        for f in FAMILIES:
            added = td[td[f] == 1]
            not_added = td[td[f] == 0]
            if len(added) >= 5:
                fams[FAM_LABEL[f]] = {"added": rate(added), "not_added": rate(not_added)}
        entry["family_additions"] = fams
        per_theme[t] = entry
        for bucket in ("trim", "similar", "expand"):
            b = entry[bucket]
            rows.append({"theme": t, "bucket": bucket, **b})
    report["per_theme"] = per_theme
    (OUT / "drafting_contrast.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    pd.DataFrame(rows).to_csv(OUT / "drafting_contrast.csv", index=False)
    print(json.dumps({"n_pairs": report["n_pairs"], "n_with_theme": report["n_with_theme"]}))
    print(json.dumps(report["overall"], indent=1))
    for t, e in per_theme.items():
        if e["n"] >= 30:
            print(json.dumps({"theme": t, **{k: e[k] for k in ("n", "trim", "similar", "expand")}}))
    print("saved ->", OUT)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
