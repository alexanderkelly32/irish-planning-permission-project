"""Stage 1 feasibility: expand cohort to 100 sites (41 existing + 59 new).

Stratified: type x size x speed, greenfield/brownfield (area-per-unit),
urban/rural (authority), stalls oversampled, county spread capped.
Output: silver/imagery/feasibility_100.csv
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
OUT = SILVER / "imagery"
URBAN = {"Dublin City Council", "Dun Laoghaire-Rathdown County Council",
         "South Dublin County Council", "Fingal County Council",
         "Cork City Council", "Galway City Council", "Waterford City and County Council"}


def main() -> None:
    geo = json.loads((SILVER / "site_polygons.geojson").read_text(encoding="utf-8"))
    poly_ids = {f["properties"]["development_id"] for f in geo["features"]}
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "PlanningAuthority", "DevelopmentDescription",
                                   "NumResidentialUnits", "AreaofSite", "GrantDate"])
    reg = reg.drop_duplicates("case_key")
    reg["units"] = pd.to_numeric(reg["NumResidentialUnits"], errors="coerce")
    reg["area"] = pd.to_numeric(reg["AreaofSite"], errors="coerce")
    reg["grant_dt"] = pd.to_datetime(reg["GrantDate"], utc=True, errors="coerce").dt.tz_localize(None)
    labels = pd.read_csv(SILVER / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    base = reg.merge(labels, on="case_key", how="inner")
    base = base[base["case_key"].isin(poly_ids)]
    base = base[base["units"].notna() & (base["units"] >= 5)]
    base = base.dropna(subset=["grant_dt"])
    base["activation"] = pd.to_numeric(base["activation_days"], errors="coerce")
    base["completion"] = pd.to_numeric(base["completion_days"], errors="coerce")
    base["type"] = np.where(base["DevelopmentDescription"].fillna("").str.lower()
                            .str.contains("apartment|duplex", regex=True), "apartment", "house")
    base["size"] = pd.cut(base["units"], [0, 20, 60, 500], labels=["small", "medium", "large"])
    base["started"] = base["activation_linked"].astype(str).str.lower() == "true"
    base["speed"] = "not_started"
    base.loc[base["activation"].notna() & (base["activation"] <= 400), "speed"] = "fast"
    base.loc[base["activation"].notna() & (base["activation"] > 400), "speed"] = "slow"
    base["stall_flag"] = ((base["started"]) & (base["completion"].isna() | (base["completion"] > 1200))).astype(int)
    base["greenfield"] = np.where(base["area"] / base["units"] > 500, "greenfield",
                                  np.where(base["area"] / base["units"] < 150, "brownfield", "mixed"))
    base["urban"] = base["PlanningAuthority"].isin(URBAN)
    base["county"] = base["PlanningAuthority"].str.replace(" County Council", "").str.replace(" City Council", "")

    existing = pd.read_csv(OUT / "feasibility_50.csv", dtype=str)
    existing_ids = set(existing["case_key"])
    base["already"] = base["case_key"].isin(existing_ids)
    rng = np.random.default_rng(7)
    picked = list(existing_ids)
    # stratified new picks, cap per county to spread
    county_count = base[base["case_key"].isin(picked)]["county"].value_counts().to_dict()
    pool = base[~base["case_key"].isin(picked)].copy()
    for _, g in pool.groupby(["type", "size", "speed", "greenfield", "urban"], observed=True):
        if len(picked) >= 100:
            break
        g = g[~g["county"].map(lambda c: county_count.get(c, 0) >= 3)]
        if len(g) == 0:
            continue
        n = 1 if len(picked) >= 70 else 2
        for _, row in g.sample(min(n, len(g)), random_state=rng).iterrows():
            if len(picked) >= 100:
                break
            picked.append(row["case_key"])
            county_count[row["county"]] = county_count.get(row["county"], 0) + 1
    stalls = pool[pool["stall_flag"] == 1]
    for _, row in stalls.sample(min(10, len(stalls)), random_state=rng).iterrows():
        if len(picked) >= 100:
            break
        if row["case_key"] not in picked:
            picked.append(row["case_key"])
            county_count[row["county"]] = county_count.get(row["county"], 0) + 1
    # top-up with recent grants (2023-2025) for prospective monitoring
    recent_reg = reg[reg["grant_dt"].dt.year >= 2023]
    recent_reg["type"] = np.where(recent_reg["DevelopmentDescription"].fillna("").str.lower()
                                  .str.contains("apartment|duplex", regex=True), "apartment", "house")
    recent_reg["size"] = pd.cut(recent_reg["units"], [0, 20, 60, 500], labels=["small", "medium", "large"])
    recent_reg["speed"] = "not_started"
    recent_reg["stall_flag"] = 0
    recent_reg["greenfield"] = np.where(recent_reg["area"] / recent_reg["units"] > 500, "greenfield",
                                        np.where(recent_reg["area"] / recent_reg["units"] < 150, "brownfield", "mixed"))
    recent_reg["urban"] = recent_reg["PlanningAuthority"].isin(URBAN)
    recent_reg["county"] = recent_reg["PlanningAuthority"].str.replace(" County Council", "").str.replace(" City Council", "")
    recent_reg["started"] = False
    recent_reg["already"] = False
    recent = recent_reg[~recent_reg["case_key"].isin(picked)]
    for _, row in recent.sample(min(40, len(recent)), random_state=rng).iterrows():
        if len(picked) >= 100:
            break
        if row["case_key"] not in picked:
            picked.append(row["case_key"])
            county_count[row["county"]] = county_count.get(row["county"], 0) + 1
    cohort = pd.concat([base[base["case_key"].isin(picked)],
                        recent_reg[recent_reg["case_key"].isin(picked)]], ignore_index=True)
    cohort = cohort.sort_values("grant_dt")
    # attach commencement (BCMS links) and first CCC labels
    links = pd.read_csv(SILVER / "bcms_links_all_granted.csv", dtype=str)
    links["comm"] = pd.to_datetime(links["commencement_date"], utc=True, errors="coerce").dt.tz_localize(None)
    comm = (links.dropna(subset=["comm"]).groupby("scheme_id")["comm"].min()
            .rename("comm_dt").reset_index().rename(columns={"scheme_id": "case_key"}))
    ccc = pd.read_csv(SILVER / "ccc_blocks.csv", dtype=str)
    ccc["first_ccc"] = pd.to_datetime(ccc["first_ccc"], utc=True, errors="coerce").dt.tz_localize(None)
    ccc1 = (ccc.dropna(subset=["first_ccc"]).groupby("scheme_id")["first_ccc"].min()
            .reset_index().rename(columns={"scheme_id": "case_key"}))
    cohort = cohort.merge(comm, on="case_key", how="left").merge(ccc1, on="case_key", how="left")
    cohort.to_csv(OUT / "feasibility_100.csv", index=False)
    print(json.dumps({"n": int(len(cohort)),
                      "n_new": int((~cohort["already"]).sum()),
                      "types": cohort["type"].value_counts().to_dict(),
                      "sizes": cohort["size"].value_counts().to_dict(),
                      "speeds": cohort["speed"].value_counts().to_dict(),
                      "stalls": int(cohort["stall_flag"].sum()),
                      "greenfield": cohort["greenfield"].value_counts().to_dict(),
                      "urban": cohort["urban"].value_counts().to_dict(),
                      "counties": int(cohort["county"].nunique()),
                      "n_with_comm": int(cohort["comm_dt"].notna().sum()),
                      "n_with_ccc": int(cohort["first_ccc"].notna().sum()),
                      "years": [int(y) for y in sorted(cohort["grant_dt"].dt.year.unique())]},
                     indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
