"""Stage 1 feasibility: select 50 representative developments with polygons.

Stratified: greenfield/brownfield, houses/apartments, size, fast/slow,
known stalls (commenced, long CCC gap or no CCC yet). Polygon-joined
only. Output: silver/imagery/feasibility_50.csv.
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
OUT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    geo = json.loads((SILVER / "site_polygons.geojson").read_text(encoding="utf-8"))
    poly_ids = {f["properties"]["development_id"] for f in geo["features"]}
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "PlanningAuthority", "DevelopmentDescription",
                                   "NumResidentialUnits", "AreaofSite", "GrantDate"])
    reg = reg.drop_duplicates("case_key")
    reg["units"] = pd.to_numeric(reg["NumResidentialUnits"], errors="coerce")
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
    rng = np.random.default_rng(7)
    picked = []
    strata = ["type", "size", "speed"]
    for _, g in base.groupby(strata, observed=True):
        n = 2 if len(picked) < 40 else 1
        take = g.sample(min(n, len(g)), random_state=7)
        picked.extend(take.index.tolist())
    stalls = base[base["stall_flag"] == 1]
    picked.extend(stalls.sample(min(6, len(stalls)), random_state=7).index.tolist())
    picked = list(dict.fromkeys(picked))[:50]
    cohort = base.loc[picked].sort_values("grant_dt")
    cohort.to_csv(OUT / "feasibility_50.csv", index=False)
    print(json.dumps({"n": int(len(cohort)),
                      "types": cohort["type"].value_counts().to_dict(),
                      "sizes": cohort["size"].value_counts().to_dict(),
                      "speeds": cohort["speed"].value_counts().to_dict(),
                      "stalls": int(cohort["stall_flag"].sum()),
                      "years": [int(y) for y in sorted(cohort["grant_dt"].dt.year.unique())]},
                     indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
