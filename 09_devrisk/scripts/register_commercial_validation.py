import json

p = "09_devrisk/data/silver/experiment_registry.json"
r = json.load(open(p))
ids = {e["id"] for e in r}
e = {
    "id": "validation_commercial_v1",
    "hypothesis": "GE10/50+/100+ performance, calibration reliability, and decision value on unseen 2025 data",
    "data": "2025 holdout n=15,221; GE10 by bucket n=113; units joins for 50+ (n=58) and 100+ (n=21)",
    "result": "GE10 AUC 0.737 [0.624,0.843], Brier 0.1489 vs national prior 0.1673 (+1.84pp) but authority prior 0.1273 better at level; 50+ AUC 0.808 [0.649,0.955]; 100+ AUC 0.75 (n=21, prior wins Brier); overall max decile miscalibration 1.87pp; screening utility GE10: model 0.434 vs prior 0.363 (+7.1pp/scheme at loss multiple 2)",
    "verdict": "provisional",
    "reason": "ranking power transfers to GE10 and 50+; level-calibration does not beat authority priors at n<120; decision-value gain demonstrated but threshold selected on holdout itself (illustrative)",
    "revisit_conditions": "larger GE10 cohort (2024+2025 combined); threshold cross-validation; per-authority priors need same n for fair Brier comparison",
}
if e["id"] not in ids:
    r.append(e)
json.dump(r, open(p, "w"), indent=1)
print("registry", len(r))
