import json

p = "09_devrisk/data/silver/experiment_registry.json"
r = json.load(open(p))
ids = {e["id"] for e in r}
new = [
    {
        "id": "theme_exposure_v6",
        "hypothesis": "Multi-label refusal-theme exposure predictable at submission time (conditional on refusal)",
        "data": "retagged master + llm_new: 819 refused GE10 with themes; train<2022 (572) / test 2022-2025 (247)",
        "prediction_time": "submission day",
        "protocol": "per-theme one-vs-rest: prevalence, authority x size ref-class, lexicon logistic, TF-IDF logistic, precedent vote (top-20 TF-IDF matches), ensemble; time-safe split",
        "leakage_check": "temporal split; lexicons fit on train text only; themes labels only",
        "baseline": "marginal prevalence top-1/2/3 42.9/58.3/76.5",
        "metric": "top-k coverage of true multi-label theme set + per-theme AUC",
        "result": "ensemble top-1/2/3 53.8/68.0/81.8; per-theme AUC: density 0.73 (ref), heritage 0.71 (tfidf), water 0.71, premature 0.69, amenity 0.68, design 0.58, land_use 0.58, traffic 0.60, ecology 0.56, flood 0.60",
        "ci": None,
        "verdict": "keep",
        "reason": "materially above prevalence on top-1 (+10.9pp) and top-3 (81.8 vs 76.5); density/heritage/water/premature separable; beats prior single-label attempts via multi-label framing; conditional on refusal only",
        "revisit_conditions": "calibration by era; per-theme drafting rules",
    },
    {
        "id": "drafting_contrast_v2",
        "hypothesis": "Resubmission description length and added technical families associate with conversion",
        "data": "11,102 refusal->revised pairs (sprint2 refusal_grant_pairs)",
        "prediction_time": "n/a (descriptive association)",
        "protocol": "length-ratio buckets trim<0.9/similar/expand>1.1, Wilson CIs, era split pre2022/2022+, per theme of refused version; per-family added flags",
        "leakage_check": "descriptive only; eras checked",
        "baseline": "overall conversion ~11%",
        "metric": "conversion rate + Wilson CI",
        "result": "similar 26.6% [25.2,28.0] vs trim 7.3% [6.4,8.2] vs expand 5.6% [4.9,6.3]; ordering stable both eras (pre2022 24.8/5.6/5.1; 2022+ 33.0/15.6/8.3) and all themes; added technical families anti-associated (density theme: access 3.3 vs 11.5%, parking 2.2 vs 11.1%, open space 1.8 vs 11.3%)",
        "ci": "Wilson",
        "verdict": "keep",
        "reason": "supersedes agreement-rate claim (91.5/66.9 was agreement, not conversion); R3 becomes keep materially similar length - aggressive trim hurts as much as expansion; correlational only",
        "revisit_conditions": "confound check within similar bucket; applicant-change control",
    },
]
for e in new:
    if e["id"] not in ids:
        r.append(e)
json.dump(r, open(p, "w"), indent=1)
print("registry now", len(r))
