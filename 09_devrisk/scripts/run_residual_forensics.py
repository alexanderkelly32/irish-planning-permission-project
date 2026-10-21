"""Runner: commencement residual forensics - matched cohort + condition pack.

1. Residuals from the latest-era commencement model; 25 fastest + 25
   slowest, matched on authority/unit-band/type/developer-history.
2. Condition-text extraction per scheme from planner PDFs (decision
   conditions block) into PACK_24 for manual semantic classification.
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".vendor"))

import fitz  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingRegressor  # noqa: E402

from devrisk import settings  # noqa: E402

RNG = np.random.default_rng(7)
REPORT_DIR = settings.ROOT / "02_development" / "source_data" / "planner_reports"


def conditions_text(pdf_path: Path) -> str:
    try:
        with fitz.open(pdf_path) as doc:
            text = " ".join(page.get_text() for page in doc)
    except Exception:
        return ""
    match = re.search(r"subject to the following", text, re.I)
    if not match:
        match = re.search(r"conditions", text, re.I)
    if not match:
        return ""
    start = match.start()
    end_match = re.search(r"\b(?:reasons|grounds for|note|appeal)", text[start:], re.I)
    end = start + end_match.start() if end_match else min(start + 4000, len(text))
    block = re.sub(r"\s+", " ", text[start:end])
    return block[:2500]


if __name__ == "__main__":
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = register[["case_key", "GrantDate", "NumResidentialUnits", "DevelopmentDescription",
                    "PlanningAuthority", "ApplicationNumber"]].drop_duplicates("case_key")
    applicants = pd.read_csv(settings.SILVER_DIR / "applicant_track_record_features.csv")
    base = labels.merge(reg, on="case_key", how="inner").merge(applicants[["case_key", "has_applicant"]], on="case_key", how="left")
    base["grant_dt"] = pd.to_datetime(base["GrantDate"], utc=True, errors="coerce")
    base["grant_year"] = base["grant_dt"].dt.year
    base["activation"] = pd.to_numeric(base["activation_days"], errors="coerce").clip(lower=0)
    base["units"] = pd.to_numeric(base["NumResidentialUnits"], errors="coerce")
    base["band"] = pd.cut(base["units"], bins=[0, 29, 99, np.inf], labels=["10-29", "30-99", "100+"]).astype(str)
    base["type"] = np.where(base["DevelopmentDescription"].fillna("").str.contains("apartment|duplex", case=False, regex=True), "apartments", "houses")
    base["log_units"] = np.log1p(base["units"].fillna(0))
    base["type_apartment"] = (base["type"] == "apartments").astype(int)
    comm = base[base["activation_linked"].astype(str).str.lower() == "true"].dropna(subset=["activation", "grant_dt"])
    train = comm[comm["grant_dt"] < pd.Timestamp("2022-01-01", tz="UTC")]
    test = comm[comm["grant_dt"] >= pd.Timestamp("2022-01-01", tz="UTC")]

    model = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=250, max_depth=3,
                                      learning_rate=0.05, min_samples_leaf=15, random_state=7)
    FEATS = ["log_units", "type_apartment", "grant_year"]
    model.fit(train[FEATS].fillna(0.0), train["activation"])
    test = test.copy()
    test["predicted"] = np.maximum(model.predict(test[FEATS].fillna(0.0)), 1.0)
    test["residual"] = test["activation"] - test["predicted"]

    fast = test.nsmallest(25, "residual")
    slow = test.nlargest(25, "residual")

    def match_pair(fast_row, slow_pool):
        best = None
        best_score = -1
        for _, candidate in slow_pool.iterrows():
            score = (int(candidate["PlanningAuthority"] == fast_row["PlanningAuthority"])
                     + int(candidate["band"] == fast_row["band"])
                     + int(candidate["type"] == fast_row["type"])
                     + int(candidate["has_applicant"] == fast_row["has_applicant"]))
            if score > best_score:
                best, best_score = candidate, score
        return best if best_score >= 2 else None

    pairs = []
    slow_pool = slow.copy()
    for _, fast_row in fast.iterrows():
        candidate = match_pair(fast_row, slow_pool)
        if candidate is not None:
            pairs.append((fast_row, candidate))
            slow_pool = slow_pool[slow_pool["case_key"] != candidate["case_key"]]

    rows = []
    for fast_row, slow_row in pairs:
        for label, row in (("fast", fast_row), ("slow", slow_row)):
            rows.append({
                "residual_group": label,
                "case_key": str(row["case_key"]),
                "authority": row["PlanningAuthority"],
                "grant_year": row["grant_year"],
                "units": row["units"],
                "band": row["band"],
                "type": row["type"],
                "has_developer_history": row["has_applicant"],
                "actual_days": row["activation"],
                "predicted_days": row["predicted"],
                "residual_days": row["residual"],
                "application_number": row["ApplicationNumber"],
            })
    cohort = pd.DataFrame(rows)
    # ePlan URLs for condition checking
    links = pd.read_csv(settings.ROOT / "01_flood" / "current" / "ge10_with_flooding.csv",
                        usecols=["PlanningAuthority", "ApplicationNumber", "LinkAppDetails"], low_memory=False)
    cohort = cohort.merge(links, left_on=["authority", "application_number"],
                          right_on=["PlanningAuthority", "ApplicationNumber"], how="left").drop(
        columns=["PlanningAuthority", "ApplicationNumber"])
    cohort.to_csv(settings.SILVER_DIR / "audit" / "residual_forensics_cohort.csv", index=False)

    # Condition texts
    pdf_by_app: dict[str, Path] = {}
    for pdf in REPORT_DIR.rglob("*_planner_report*.pdf"):
        match = re.match(r"^(\d+)_planner_report", pdf.name)
        if match:
            pdf_by_app.setdefault(match.group(1), pdf)
    texts = []
    for _, row in cohort.iterrows():
        pdf = pdf_by_app.get(str(row["application_number"]))
        texts.append({"case_key": row["case_key"], "application_number": row["application_number"],
                      "conditions_text": conditions_text(pdf) if pdf else ""})
    texts_df = pd.DataFrame(texts)
    texts_df.to_csv(settings.SILVER_DIR / "audit" / "residual_forensics_conditions.csv", index=False)

    pack_dir = settings.SILVER_DIR / "audit_packs"
    zip_path = pack_dir / "PACK_24_residual_forensics.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(settings.SILVER_DIR / "audit" / "residual_forensics_cohort.csv",
                      arcname="residual_forensics_cohort.csv")
        archive.write(settings.SILVER_DIR / "audit" / "residual_forensics_conditions.csv",
                      arcname="residual_forensics_conditions.csv")
        archive.writestr("INSTRUCTIONS.txt", (
            "PACK 24: commencement residual forensics.\n"
            "Matched pairs: 25 fastest vs 25 slowest commencement residuals\n"
            "(matched on authority, unit band, type, developer history).\n"
            "For each scheme, read the conditions text and classify what was\n"
            "outstanding at grant. Suggested classes:\n"
            "  precomm_agreement / contribution / bond / uisce / drainage /\n"
            "  roads / archaeology_ecology / phasing / part_v / other /\n"
            "  demolition / infrastructure / nothing_obvious\n"
            "Add your verdict in a new column 'readiness_driver' + notes.\n"
            "RETURN: into the 'returned' folder.\n"
        ))
    report = {
        "matched_pairs": len(pairs),
        "fast_median_residual": round(float(fast["residual"].median()), 0),
        "slow_median_residual": round(float(slow["residual"].median()), 0),
        "schemes_with_condition_text": int((texts_df["conditions_text"].str.len() > 50).sum()),
        "pack": str(zip_path),
    }
    out = settings.SILVER_DIR / "residual_forensics_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
