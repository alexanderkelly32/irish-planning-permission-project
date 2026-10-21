"""Runner: B redo - condition-level parsing of planner-report PDFs.

Splits the conditions block into individual numbered conditions, flags
each with pre-commencement implication + category. Per-scheme features:
n_conditions, n_precommencement, n_financial, n_uisce, n_drainage,
n_roads, n_archaeology_ecology, n_phasing, n_partv. Ablation vs
commencement on the PDF-covered subset.
"""
from __future__ import annotations

import json
import re
import sys
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

PRE_COMM_RE = re.compile(
    r"prior to (?:the )?(?:commencement|any development|construction)|before (?:any )?(?:development|construction|works) commenc",
    re.I)
BLOCK_START_RE = re.compile(r"subject to the following|shall be subject to|conditions? (?:attached|imposed)|comply with the following", re.I)
NUMBERED_RE = re.compile(r"(?:^|\n)\s*(\d{1,3})[\.\)]\s+([A-Z][^\n]{10,})", re.M)
CATEGORY_RE = {
    "financial": r"contribution|bond|security|financial",
    "uisce": r"uisce|irish water|water supply|wastewater|sewer",
    "drainage": r"drainage|suds|attenuation|surface water",
    "roads": r"road|access|footpath|cycle|traffic|junction|roundabout",
    "archaeology_ecology": r"archaeolog|ecolog|bat |habitat|tree|bird|natura",
    "phasing": r"phas",
    "partv": r"part v|social housing|affordable",
}


if __name__ == "__main__":
    pdfs = sorted(REPORT_DIR.rglob("*_planner_report*.pdf"))
    rows = []
    app_re = re.compile(r"^(\d+)_planner_report")
    for pdf in pdfs:
        try:
            with fitz.open(pdf) as doc:
                text = " ".join(page.get_text() for page in doc)
        except Exception:
            continue
        block = BLOCK_START_RE.search(text)
        if not block:
            continue
        tail = text[block.start():]
        end = re.search(r"\b(?:reasons for refusal|grounds|assessment|recommendation:|note:)", tail[40:], re.I)
        block_text = tail[:40 + end.start()] if end else tail[:4000]
        conditions = [m.group(2).strip() for m in NUMBERED_RE.finditer(block_text)]
        if not conditions:
            continue
        n_pre = sum(1 for c in conditions if PRE_COMM_RE.search(c))
        row = {"appno": app_re.match(pdf.name).group(1) if app_re.match(pdf.name) else pdf.stem[:20],
               "n_conditions": len(conditions), "n_precommencement": n_pre}
        for name, pattern in CATEGORY_RE.items():
            row[f"n_{name}"] = sum(1 for c in conditions if re.search(pattern, c, re.I))
            row[f"n_{name}_pre"] = sum(1 for c in conditions if re.search(pattern, c, re.I) and PRE_COMM_RE.search(c))
        rows.append(row)
    frame = pd.DataFrame(rows)
    frame.to_csv(settings.SILVER_DIR / "condition_level_features.csv", index=False)

    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = register[["case_key", "ApplicationNumber", "GrantDate", "NumResidentialUnits",
                    "DevelopmentDescription"]].drop_duplicates("case_key")
    reg["appno"] = reg["ApplicationNumber"].astype(str)
    base = labels.merge(reg, on="case_key", how="inner").merge(frame, on="appno", how="inner")
    base["grant_dt"] = pd.to_datetime(base["GrantDate"], utc=True, errors="coerce")
    base["grant_year"] = base["grant_dt"].dt.year
    base["activation"] = pd.to_numeric(base["activation_days"], errors="coerce").clip(lower=0)
    base["log_units"] = np.log1p(pd.to_numeric(base["NumResidentialUnits"], errors="coerce").fillna(0))
    base["type_apartment"] = base["DevelopmentDescription"].fillna("").str.contains("apartment|duplex", case=False, regex=True).astype(int)
    comm = base[base["activation_linked"].astype(str).str.lower() == "true"].dropna(subset=["activation", "grant_dt"])
    train = comm[comm["grant_dt"] < pd.Timestamp("2022-01-01", tz="UTC")]
    test = comm[comm["grant_dt"] >= pd.Timestamp("2022-01-01", tz="UTC")]
    CBASE = ["log_units", "type_apartment", "grant_year"]
    COND = [c for c in frame.columns if c != "appno"]

    report = {
        "schemes_with_condition_blocks": int(len(base)),
        "median_n_conditions": round(float(frame["n_conditions"].median()), 1) if len(frame) else None,
        "median_n_precommencement": round(float(frame["n_precommencement"].median()), 1) if len(frame) else None,
    }

    def run(cols):
        model = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=250, max_depth=3,
                                          learning_rate=0.05, min_samples_leaf=15, random_state=7)
        model.fit(train[cols].fillna(0.0), train["activation"])
        return np.maximum(model.predict(test[cols].fillna(0.0)), 1.0)

    if len(train) >= 30 and len(test) >= 15:
        p_base, p_cond = run(CBASE), run(CBASE + COND)
        y = test["activation"].to_numpy()
        report.update({
            "n_train": int(len(train)), "n_test": int(len(test)),
            "base_mae": round(float(np.mean(np.abs(y - p_base))), 0),
            "cond_mae": round(float(np.mean(np.abs(y - p_cond))), 0),
            "delta": round(float(np.mean(np.abs(y - p_cond)) - np.mean(np.abs(y - p_base))), 0),
        })
    out = settings.SILVER_DIR / "condition_level_ablation.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
