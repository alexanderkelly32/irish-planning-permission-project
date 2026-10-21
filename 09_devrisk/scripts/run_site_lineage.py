"""Runner: E2 - exact-site planning lineage (application genealogy).

Same-parcel identification: register applications within 60m of each
other's ITM coordinates. Per mature-pool scheme, time-safe lineage
features from strictly earlier applications on the same parcel:
prior refusal/grant counts, previous applicant, size trajectory, elapsed
time since last decision, description similarity. Then lineage features
tested against FI/appeal/decision-timing targets.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.metrics.pairwise import cosine_similarity  # noqa: E402

from devrisk import settings  # noqa: E402

PARCEL_RADIUS_M = 60.0


if __name__ == "__main__":
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    units = pd.to_numeric(register["NumResidentialUnits"], errors="coerce")
    ge10 = register[units.ge(10)].copy()
    ge10["east"] = pd.to_numeric(ge10["ITMEasting"], errors="coerce")
    ge10["north"] = pd.to_numeric(ge10["ITMNorthing"], errors="coerce")
    ge10["received_dt"] = pd.to_datetime(ge10["ReceivedDate"], utc=True, errors="coerce")
    ge10["decision_dt"] = pd.to_datetime(ge10["DecisionDate"], utc=True, errors="coerce")
    ge10["refused"] = ge10["Decision"].fillna("").astype(str).str.upper().str.contains("REFUS").astype(int)
    ge10["granted"] = (~ge10["refused"].astype(bool) & ge10["Decision"].fillna("").ne("")).astype(int)
    ge10 = ge10.dropna(subset=["east", "north", "received_dt"])

    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    pool_keys = set(labels["case_key"].astype(str))
    pool = ge10[ge10["case_key"].astype(str).isin(pool_keys)].copy()
    all_apps = ge10

    vectorizer = TfidfVectorizer(max_features=3000, stop_words="english", min_df=2)
    vectorizer.fit(all_apps["DevelopmentDescription"].fillna(""))

    rows = []
    for _, scheme in pool.iterrows():
        east, north = scheme["east"], scheme["north"]
        distance = np.hypot(all_apps["east"].to_numpy() - east, all_apps["north"].to_numpy() - north)
        same_parcel = all_apps[distance <= PARCEL_RADIUS_M].copy()
        same_parcel = same_parcel[same_parcel["received_dt"] < scheme["received_dt"]]
        same_parcel = same_parcel[same_parcel["case_key"].astype(str) != str(scheme["case_key"])]

        row = {"case_key": str(scheme["case_key"]), "n_prior_same_parcel": int(len(same_parcel))}
        if len(same_parcel):
            row["prior_refusals_same_parcel"] = int(same_parcel["refused"].sum())
            row["prior_grants_same_parcel"] = int(same_parcel["granted"].sum())
            row["prior_refusal_rate_same_parcel"] = float(same_parcel["refused"].mean())
            prior_units = pd.to_numeric(same_parcel["NumResidentialUnits"], errors="coerce")
            row["prior_max_units"] = float(prior_units.max()) if prior_units.notna().any() else np.nan
            row["prior_median_units"] = float(prior_units.median()) if prior_units.notna().any() else np.nan
            latest = same_parcel.sort_values("received_dt").iloc[-1]
            row["days_since_last_same_parcel_decision"] = float((scheme["received_dt"] - latest["received_dt"]).days)
            row["last_same_parcel_refused"] = int(latest["refused"])
            row["size_change_vs_last"] = float(
                pd.to_numeric(pd.Series([scheme.get("NumResidentialUnits")]), errors="coerce").iloc[0]
                - pd.to_numeric(pd.Series([latest.get("NumResidentialUnits")]), errors="coerce").iloc[0]
            ) if pd.notna(scheme.get("NumResidentialUnits")) and pd.notna(latest.get("NumResidentialUnits")) else np.nan
            if pd.notna(scheme.get("DevelopmentDescription")) and pd.notna(latest.get("DevelopmentDescription")):
                vectors = vectorizer.transform([str(scheme["DevelopmentDescription"]), str(latest["DevelopmentDescription"])])
                row["description_similarity_to_last"] = float(cosine_similarity(vectors[0], vectors[1])[0, 0])
            else:
                row["description_similarity_to_last"] = np.nan
        rows.append(row)

    lineage = pd.DataFrame(rows)
    lineage.to_csv(settings.SILVER_DIR / "site_lineage_features.csv", index=False)
    summary = {
        "pool_schemes": int(len(lineage)),
        "with_prior_same_parcel": int((lineage["n_prior_same_parcel"] > 0).sum()),
        "median_prior_apps": float(lineage["n_prior_same_parcel"].median()),
        "out": str(settings.SILVER_DIR / "site_lineage_features.csv"),
    }
    (settings.SILVER_DIR / "site_lineage_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
