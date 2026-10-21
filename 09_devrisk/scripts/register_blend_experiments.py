import json

p = "09_devrisk/data/silver/experiment_registry.json"
r = json.load(open(p))
ids = {e["id"] for e in r}
new = [
    {"id": "authority_prior_auc_correction",
     "hypothesis": "authority prior AUC equals 0.5 by construction",
     "data": "2025 holdout n=15,221; GE10 n=113",
     "result": "authority prior AUC 0.673 overall, 0.698 GE10 - prior claim of 0.5 was WRONG (holds only for constant prior)",
     "verdict": "falsified",
     "reason": "documents the correction; authority prior is a real competitor on ranking and level in commercial segments",
     "revisit_conditions": None},
    {"id": "validation_blend_v1",
     "hypothesis": "blend of model ranking + authority-level calibration beats either alone in decision value",
     "data": "frozen v4 scoring of 2024+2025 (n=35,713); fit w + threshold on 2024 (n=20,492, GE10 197); eval 2025 (n=15,221, GE10 113)",
     "result": "overall: model 0.6781 vs always 0.6527 (+0.0254 [0.020,0.030]) vs authority 0.6659 (+0.0122 [0.008,0.016]); blend 0.6778 = model (calibration already strong); GE10: blend 0.439 > model 0.429 > authority 0.389 > always 0.360 (CI too wide, n=113); fitted model threshold 0.350 ~ theoretical 0.333",
     "verdict": "keep",
     "reason": "robust decision value over always-proceed on overall population with tight CIs; blend recommended architecture for GE10 though small-n prevents claim; resolves the 19.2% threshold artefact",
     "revisit_conditions": "prospective GE10 outcomes 2026+; deeper GE10 calibration cohort"},
]
for e in new:
    if e["id"] not in ids:
        r.append(e)
json.dump(r, open(p, "w"), indent=1)
print("registry", len(r))
