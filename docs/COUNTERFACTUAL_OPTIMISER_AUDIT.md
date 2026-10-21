# Counterfactual Optimiser — Repository & Model Audit (2026-10-08)

## 1. Existing implementations (all located and reproduced)

| Component | Location | Status |
|---|---|---|
| Optionality sweep v1 | `scripts/run_sprint1_optionality.py`; `silver/sprint1/optionality_surface.csv` | reproduced: units 0.5x-2.0x flat; description rewrites 1-4pp |
| Description-axis sweep | `scripts/run_sprint1b_description_axis.py`; `silver/sprint1/description_surface.csv` | reproduced |
| Mutation engine | `scripts/run_sprint2_mutation.py`; `silver/sprint2/refusal_grant_pairs.csv` (11,102 pairs) | reproduced: units-reduction sign-flip on fresh era documented |
| Rescue plan | `scripts/run_sprint2b_rescue.py`; `silver/sprint2/rescue_plan_report.json` | reproduced: monotone 0/1.7/5.6/18.7/24.9%; fresh-era 0/1.2/4.5/17.4/21.0% |
| Scheme-specific counterfactuals | `scripts/run_counterfactuals.py`; `silver/report/counterfactuals/counterfactuals_report.json` | reproduced |
| Prospective examples | `silver/report/prospective/report_LRD25A_0014W.md` §12b; `silver/report/demo/report_SD17A_0397.md` | reproduced |
| Frozen scoring path | `05_policy/scripts/model_feature_builder.py`; adapter `devrisk/models/planning_adapter.py` | read-only, never retrained |

## 2. Mechanical explanation: why unit changes are flat

Read of `build_feature_row` / `_bucket_for` / `_comparable_features` /
`_plan_features` / `_history_features` (model_feature_builder.py):

1. **Units enter the model only through `application_bucket`**
   (`residential_bucket(description, units)`). There is NO raw units
   feature and NO density feature.
2. **Site area and floor area are parsed but UNUSED** - they never reach
   the feature row. Density cannot respond.
3. **The description text dominates** via cosine-NN comparable features
   (comp_top5/10/20 refusal rates). When units change but the description
   keeps "113 residential units", the text vector is unchanged and the
   comparables barely move.
4. **Isotonic calibration smooths** the ranking-model base score further,
   flattening small movements within a bucket.
5. **The only visible unit response is a bucket-boundary step.** Fine
   sweep on LRD25A/0014W (100-160 units, 1-unit steps): 11.4% flat from
   110-140 units, then **140 -> 145 units: +3.0pp** (14.4%), flat again
   above. The cliff is a comparable-pool switch, not a density effect.

Conclusions:
- The optimiser has effectively been optimising **wording and bucket
  placement**, not design.
- Any unit/density recommendation from the frozen model is MODEL_ONLY
  until a design-sensitive model exists (Model 2 below).
- The "146-unit cliff" in the prospective report is a tree/bucket split,
  must be labelled as such, and must not be presented as a planning
  insight.

## 3. Diagnosis of the prospective 113 -> 130 -> 140 -> 146 example

Reproduced exactly: 113/130/140 = 11.4%; 145+ = 14.4%. The step is the
`residential_bucket` boundary near 145 units for this description type.
Verdict: real model sensitivity (bucket switch), NOT a supported
planning extrapolation. The report's §12b line has been flagged to state
this explicitly.

## 4. What this audit changes

- Unit-only and isolated-feature perturbations are retired as evidence
  (MODEL_ONLY at best).
- The new system must generate COHERENT design bundles (units + density +
  mix + open space + height with arithmetic consistency), scored by:
  (a) the frozen model (calibrated risk only), (b) a NEW design-sensitive
  model trained on explicit design variables, (c) paired mutation evidence,
  (d) empirical neighbours.
- Nothing enters a production report without passing the promotion gates.
