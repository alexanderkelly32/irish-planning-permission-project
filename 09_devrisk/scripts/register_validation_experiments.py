import json

p = "09_devrisk/data/silver/experiment_registry.json"
r = json.load(open(p))
ids = {e["id"] for e in r}
new = [
    {"id": "validation_study1_outcomes",
     "hypothesis": "v4-full beats simple historical baselines with size x authority calibration",
     "data": "2025 prospective cohort n=15,221",
     "result": "AUC 0.793 vs priors 0.5; Brier 0.0848 vs national 0.1023 / authority 0.0936; beats prior in all size bands except 80+ (n=29)",
     "verdict": "keep", "reason": "assembled from promoted artifacts; all baselines beaten",
     "revisit_conditions": "GE10 units coverage; council-level Brier table"},
    {"id": "validation_study2_timelines",
     "hypothesis": "timing models beat baselines",
     "data": "assembled model cards",
     "result": "decision-timing MAE 63.9 vs 80.2/86.7; FI AUC 0.69; conditions 0.714-0.747; permission p50 at parity, p80 improved",
     "verdict": "keep", "reason": "headline beat; parity disclosed",
     "revisit_conditions": "none"},
    {"id": "validation_study3_supply",
     "hypothesis": "stage-chain (commencement+403d) predicts delivery better than direct constant",
     "data": "2019-2021 granted cohort n=439, expanding-window fits",
     "result": "constant MAE 350d vs chain 630d; chain over-predicts early, under-predicts late; administrative commencement anchor is the weakness",
     "verdict": "falsified", "reason": "chain underperforms direct constant; imagery physical-start is the designated fix; censoring noted",
     "revisit_conditions": "retest with imagery-detected physical starts"},
]
for e in new:
    if e["id"] not in ids:
        r.append(e)
json.dump(r, open(p, "w"), indent=1)
print("registry", len(r))
