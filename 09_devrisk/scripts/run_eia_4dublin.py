"""Runner: A-tier sprint - EIA features + 4Dublin validation.

1. EIA portal: join by Competent_Authority_Application to register
   applications; EIAR-required flag + application date -> features.
2. 4Dublin polygons: spatial validation of our reconstructed pipeline
   (granted/commenced/CCC/sold points) against official pipeline
   polygons.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from shapely.geometry import Point, shape  # noqa: E402
from shapely import STRtree  # noqa: E402

from devrisk import settings  # noqa: E402

if __name__ == "__main__":
    report: dict = {}

    # ---- EIA features ----
    eia = pd.read_csv(settings.RAW_DIR / "housing_open" / "eia_portal.csv", low_memory=False)
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = register[["case_key", "PlanningAuthority", "ApplicationNumber", "GrantDate", "ReceivedDate"]].drop_duplicates("case_key")
    reg["app_norm"] = reg["ApplicationNumber"].astype(str).str.upper().str.replace(r"\s+", "", regex=True)
    eia["app_norm"] = eia["Competent_Authority_Application"].fillna("").astype(str).str.upper().str.replace(r"\s+", "", regex=True)
    eia["eiar_required"] = (~eia["Portal_Ref"].isna()).astype(int)
    eia_map = eia.dropna(subset=["app_norm"]).groupby("app_norm").agg(
        eiar_required=("eiar_required", "max"),
        eia_receipt_date=("Date_of_receipt_of_application_", "min"),
    )
    reg = reg.merge(eia_map, on="app_norm", how="left")
    reg["eiar_required"] = reg["eiar_required"].fillna(0)
    pool = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    pool = pool[["case_key"]].merge(reg[["case_key", "eiar_required", "eia_receipt_date"]], on="case_key", how="left")
    pool.to_csv(settings.SILVER_DIR / "eia_features.csv", index=False)
    report["eia"] = {
        "eia_rows": int(len(eia)),
        "pool_with_eiar": int(pool["eiar_required"].sum()),
        "pool_eiar_share": round(float(pool["eiar_required"].mean()), 4),
    }

    # ---- 4Dublin validation ----
    polygons = json.loads((settings.RAW_DIR / "housing_open" / "4dublin_polygons.geojson").read_text(encoding="utf-8"))
    features = polygons["features"]
    geoms = [shape(f["geometry"]) for f in features]
    tree = STRtree(geoms)
    props = [f["properties"] for f in features]

    # Our reconstructed pipeline points: schemes with (grant, commencement, CCC, sale)
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    reg2 = register[["case_key", "PlanningAuthority", "ITMEasting", "ITMNorthing", "GrantDate"]].drop_duplicates("case_key")
    pipeline_points = labels[["case_key", "activation_days", "activation_linked", "completion_linked"]].merge(reg2, on="case_key", how="left")
    pipeline_points = pipeline_points[pipeline_points["PlanningAuthority"].str.contains("Dublin", case=False, na=False)]
    pipeline_points["east"] = pd.to_numeric(pipeline_points["ITMEasting"], errors="coerce")
    pipeline_points["north"] = pd.to_numeric(pipeline_points["ITMNorthing"], errors="coerce")
    pipeline_points = pipeline_points.dropna(subset=["east", "north"])

    # ITM polygons - query directly in ITM (no transform).
    matched = 0
    agreement = 0
    for _, row in pipeline_points.iterrows():
        idx = tree.query(Point(row["east"], row["north"]))
        if idx.size == 0:
            continue
        matched += 1
        agreement += 1  # official pipeline has a record at this site
    report["4dublin_validation"] = {
        "official_polygons": len(features),
        "our_dublin_pipeline_points": int(len(pipeline_points)),
        "matched_to_official_polygon": matched,
        "match_rate": round(matched / max(1, len(pipeline_points)), 3),
    }

    out = settings.SILVER_DIR / "eia_4dublin_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
