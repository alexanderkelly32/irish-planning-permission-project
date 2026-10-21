"""Select the ~90-scheme readiness validation cohort.

Design: activation-linked schemes, grant 2020-2023, >=5 units, iDocs-capable
councils, stratified by activation tercile x council (cap 12/council) with
developer-group diversity. Saves silver/idocs/validation_cohort.csv.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

OUT = settings.SILVER_DIR / "idocs"

CAP_PER_COUNCIL = 12
TARGET = 90


def main() -> None:
    hosts = json.loads((OUT / "council_hosts.json").read_text(encoding="utf-8"))
    usable = {k for k, v in hosts.items() if v and "idocs" not in v.lower() and "plandocs" not in v and "apps." not in v}
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "PlanningAuthority", "ApplicationNumber",
                                   "NumResidentialUnits", "GrantDate", "LinkAppDetails"])
    reg["grant_dt"] = pd.to_datetime(reg["GrantDate"], utc=True, errors="coerce")
    base = labels[["case_key", "activation_days", "activation_linked"]].merge(reg, on="case_key", how="inner")
    base = base[base["activation_linked"].astype(str).str.lower() == "true"]
    base = base[base["PlanningAuthority"].isin(usable)]
    base = base[base["grant_dt"].dt.year.between(2020, 2023)]
    base["units"] = pd.to_numeric(base["NumResidentialUnits"], errors="coerce")
    base = base[base["units"] >= 5]
    base["activation"] = pd.to_numeric(base["activation_days"], errors="coerce").clip(lower=0)
    base = base.dropna(subset=["activation", "grant_dt"])
    base["tercile"] = pd.qcut(base["activation"], 3, labels=["fast", "mid", "slow"])
    try:
        entities = pd.read_csv(settings.SILVER_DIR / "applicant_entities_with_cro.csv", dtype=str)
        base = base.merge(entities[["case_key", "group_id"]].drop_duplicates("case_key"), on="case_key", how="left")
    except Exception:
        base["group_id"] = np.nan
    rng = np.random.default_rng(42)
    picked = []
    per_tercile = TARGET // 3
    for tercile, group in base.groupby("tercile", observed=True):
        group = group.sample(frac=1, random_state=42)
        counts = {}
        group_counts = {}
        for _, row in group.iterrows():
            if len([p for p in picked if p["tercile"] == tercile]) >= per_tercile:
                break
            council = row["PlanningAuthority"]
            if counts.get(council, 0) >= CAP_PER_COUNCIL:
                continue
            gid = str(row["group_id"]) if pd.notna(row["group_id"]) else f"none_{row['case_key']}"
            if group_counts.get(gid, 0) >= 4:
                continue
            picked.append(row)
            counts[council] = counts.get(council, 0) + 1
            group_counts[gid] = group_counts.get(gid, 0) + 1
    cohort = pd.DataFrame(picked)
    cohort = cohort.sort_values(["tercile", "PlanningAuthority"])
    cohort.to_csv(OUT / "validation_cohort.csv", index=False)
    summary = {
        "n": int(len(cohort)),
        "by_tercile": cohort["tercile"].value_counts().to_dict(),
        "by_council": cohort["PlanningAuthority"].value_counts().to_dict(),
        "activation_median": float(cohort["activation"].median()),
        "activation_p10": float(cohort["activation"].quantile(0.1)),
        "activation_p90": float(cohort["activation"].quantile(0.9)),
    }
    (OUT / "validation_cohort_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
