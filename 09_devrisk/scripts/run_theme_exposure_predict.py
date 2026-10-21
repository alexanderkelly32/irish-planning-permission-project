"""Run theme-exposure v6 for LRD25A/0014W (prospective scheme)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "09_devrisk" / "data" / "silver" / "theme_exposure"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
sys.path.insert(0, str(ROOT / "09_devrisk"))
from build_dublin_submission_model import strip_text_leakage_clues  # noqa: E402
from devrisk import settings  # noqa: E402

TARGET = "South Dublin County Council__LRD25A/0014W"


def main() -> None:
    bundle = joblib.load(OUT / "theme_exposure_v6.joblib")
    vectorizer = bundle["vectorizer"]
    lex_models = bundle["lex_models"]
    lexicons = bundle["lexicons"]
    base = bundle["base"]
    ref_rates = bundle["ref_rates"]
    global_sm = bundle["global_sm"]
    all_tags = bundle["all_tags"]
    train = bundle["train"]

    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "DevelopmentDescription", "NumResidentialUnits",
                                   "AreaofSite", "PlanningAuthority"])
    row = reg[reg["case_key"] == TARGET]
    if row.empty:
        print("not found")
        return
    row = row.iloc[0]
    text = strip_text_leakage_clues(str(row["DevelopmentDescription"])) or ""
    units = pd.to_numeric(row["NumResidentialUnits"], errors="coerce")
    size = pd.cut([units], [9, 30, 80, 500], labels=["s", "m", "l"])[0]
    X = vectorizer.transform([text])
    from sklearn.metrics.pairwise import cosine_similarity
    sims = cosine_similarity(X, vectorizer.transform(train["text"]))
    order = np.argsort(-sims, axis=1)[0, :20]
    profile = {}
    for t in all_tags:
        ref = ref_rates.get((row["PlanningAuthority"], size, t), global_sm[t])
        lex_count = len(re.findall("|".join(re.escape(w) for w in lexicons[t]), text, re.IGNORECASE))
        lex = float(lex_models[t].predict_proba([[lex_count, np.log1p(units) if not np.isnan(units) else 0]])[0, 1])
        prec = float(np.take(train[t].to_numpy(), order).mean())
        ens = (ref + lex + prec) / 3.0
        profile[t] = {"ref_class": round(float(ref), 3), "lexicon_hits": int(lex_count),
                      "lexicon": round(lex, 3), "precedent_vote": round(prec, 3),
                      "ensemble": round(float(ens), 3)}
    refusal = 0.171
    for t in all_tags:
        profile[t]["absolute_risk"] = round(profile[t]["ensemble"] * refusal, 3)
    result = {"scheme": TARGET, "units": float(units), "size_bucket": str(size),
              "authority": str(row["PlanningAuthority"]), "refusal_headline": refusal,
              "profile": profile}
    (OUT / "predict_LRD25A_0014W.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
