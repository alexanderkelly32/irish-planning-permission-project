"""Prospective 2026 report for LRD25A/0014W (113 units, Newcastle, SDCC) -
outcome unknown. Production models trained on pre-submission data; frozen
v4 refusal model is primary (time-valid for a 2026 query); LRD-regime
caveat stated. Same bounded 18-section structure as the SD17A demo.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402
from devrisk.models.planning_adapter import proposal_from_application, score_planning  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "report" / "prospective"
OUT.mkdir(parents=True, exist_ok=True)

KEY = "South Dublin County Council__LRD25A/0014W"
SUBMISSION = pd.Timestamp("2025-12-19")

FAMILIES = ["access", "road", "parking", "storey", "drainage", "water", "flood",
            "ecolog", "archaeolog", "design", "phase", "demolition", "protected",
            "change of use", "apartment", "amenity"]


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * np.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return max(centre - margin, 0.0), min(centre + margin, 1.0)


def cal_bands(preds, y, n_bins=10):
    qs = np.quantile(preds, np.linspace(0, 1, n_bins + 1))
    out = []
    for i in range(n_bins):
        mask = (preds >= qs[i]) & (preds <= qs[i + 1])
        if mask.sum() < 30:
            continue
        k, n = int(y[mask].sum()), int(mask.sum())
        lo, hi = wilson(k, n)
        out.append({"lo": float(qs[i]), "hi": float(qs[i + 1]), "n": n,
                    "rate": k / n, "ci_lo": lo, "ci_hi": hi})
    return out


def band_for(bands, p):
    for b in bands:
        if b["lo"] <= p <= b["hi"]:
            return b
    return None


def main() -> None:
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = reg.drop_duplicates("case_key")
    reg["recv"] = pd.to_datetime(reg["ReceivedDate"], utc=True, errors="coerce").dt.tz_localize(None)
    reg["dec"] = pd.to_datetime(reg["DecisionDate"], utc=True, errors="coerce").dt.tz_localize(None)
    dec = reg["Decision"].fillna("").str.lower()
    reg["granted"] = dec.str.contains("grant|conditional|unconditional", regex=True).astype(int)
    reg["refused"] = dec.str.contains("refus").astype(int)
    reg = reg[((reg["granted"] == 1) | (reg["refused"] == 1))]
    reg["dur"] = (reg["dec"] - reg["recv"]).dt.days
    reg["fi"] = pd.notna(reg["FIRequestDate"]).astype(int)
    reg["appeal"] = pd.notna(reg["AppealSubmittedDate"]).astype(int)
    reg["units"] = pd.to_numeric(reg["NumResidentialUnits"], errors="coerce").fillna(1)
    reg["year"] = reg["recv"].dt.year
    desc = reg["DevelopmentDescription"].fillna("").str.lower()
    for fam in FAMILIES:
        reg[f"f_{fam}"] = desc.str.contains(fam, regex=False).astype(int)
    reg["desc_len"] = desc.str.len()
    reg["log_units"] = np.log1p(reg["units"])
    reg["clean"] = ((reg["granted"] == 1) & (reg["fi"] == 0) & (reg["appeal"] == 0) &
                    (reg["dur"] <= 365)).astype(int)
    reg["late6m"] = (reg["dur"] > 183).astype(int)
    reg["y"] = reg["refused"].astype(int)
    reg["grant_appeal_flag"] = ((reg["granted"] == 1) & (reg["appeal"] == 1)).astype(int)
    reg["refusal_appeal_flag"] = ((reg["refused"] == 1) & (reg["appeal"] == 1)).astype(int)
    reg["path"] = "other"
    reg.loc[(reg["granted"] == 1) & (reg["fi"] == 0) & (reg["appeal"] == 0), "path"] = "direct_grant"
    reg.loc[(reg["granted"] == 1) & (reg["fi"] == 1) & (reg["appeal"] == 0), "path"] = "fi_grant"
    reg.loc[(reg["refused"] == 1) & (reg["fi"] == 1) & (reg["appeal"] == 0), "path"] = "fi_refusal"
    reg.loc[(reg["refused"] == 1) & (reg["fi"] == 0) & (reg["appeal"] == 0), "path"] = "direct_refusal"
    reg.loc[(reg["granted"] == 1) & (reg["appeal"] == 1), "path"] = "grant_appeal"
    reg.loc[(reg["refused"] == 1) & (reg["appeal"] == 1), "path"] = "refusal_appeal"
    reg = reg[(reg["path"] != "other") & (reg["year"] >= 2010)].reset_index(drop=True)

    feats = ["log_units", "desc_len", "year"] + [f"f_{f}" for f in FAMILIES]
    all_d = pd.get_dummies(reg["PlanningAuthority"], prefix="a").astype(int)
    train = reg[reg["recv"] < SUBMISSION]
    X_tr = pd.concat([train[feats], all_d.loc[train.index]], axis=1)

    sample = reg[reg["case_key"] == KEY]
    if sample.empty:
        # undecided scheme: build the feature row from the full register
        reg_full0 = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
        row = reg_full0[reg_full0["case_key"] == KEY].iloc[0]
        import re as _re
        d_low = str(row["DevelopmentDescription"]).lower()
        feat_row = {"log_units": np.log1p(float(pd.to_numeric(row["NumResidentialUnits"], errors="coerce") or 1)),
                    "desc_len": len(str(row["DevelopmentDescription"])), "year": 2025}
        for fam in FAMILIES:
            feat_row[f"f_{fam}"] = int(_re.search(fam, d_low) is not None)
        s_full = row
        s_log_units = feat_row["log_units"]
        s_f_apartment = feat_row["f_apartment"]
        s_units_val = float(pd.to_numeric(row["NumResidentialUnits"], errors="coerce") or 1)
        X_s = pd.DataFrame([feat_row]).reindex(columns=X_tr.columns).fillna(0.0)
        X_s.loc[0, "a_South Dublin County Council"] = 1.0
    else:
        s_full = sample.iloc[0]
        s_log_units = float(s_full["log_units"])
        s_f_apartment = float(s_full["f_apartment"])
        s_units_val = float(s_full["units"])
        X_s = pd.concat([sample[feats], all_d.loc[sample.index]], axis=1).reindex(columns=X_tr.columns).fillna(0.0)

    band_train = reg[reg["year"] < 2023]
    band_cal = reg[(reg["year"].between(2023, 2025)) & (reg["recv"] < SUBMISSION)]
    X_bt = pd.concat([band_train[feats], all_d.loc[band_train.index]], axis=1)
    X_bc = pd.concat([band_cal[feats], all_d.loc[band_cal.index]], axis=1)

    def bands_for(y_col):
        m = GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.05,
                                       min_samples_leaf=30, random_state=7)
        m.fit(X_bt, band_train[y_col])
        return cal_bands(m.predict_proba(X_bc)[:, 1], band_cal[y_col].to_numpy())

    bands = {"refusal": bands_for("y"), "fi": bands_for("fi"), "appeal": bands_for("appeal"),
             "clean": bands_for("clean"), "tail": bands_for("late6m"),
             "appeal_tp": bands_for("grant_appeal_flag"),
             "appeal_ap": bands_for("refusal_appeal_flag")}

    def fit_predict(y_col):
        m = GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.05,
                                       min_samples_leaf=30, random_state=7)
        m.fit(X_tr, train[y_col])
        return float(m.predict_proba(X_s)[:, 1][0])

    m_ref = GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.05,
                                       min_samples_leaf=30, random_state=7)
    m_ref.fit(X_bt, band_train["y"])
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(m_ref.predict_proba(X_bc)[:, 1], band_cal["y"].to_numpy())
    p_ref_raw = fit_predict("y")
    p_ref = float(iso.predict([p_ref_raw])[0])
    p_fi = fit_predict("fi")
    p_appeal = fit_predict("appeal")
    p_appeal_tp = fit_predict("grant_appeal_flag")
    p_appeal_ap = fit_predict("refusal_appeal_flag")
    p_clean = fit_predict("clean")
    p_tail = fit_predict("late6m")
    pm = LogisticRegression(max_iter=4000, C=1.0)
    pm.fit(X_tr, train["path"])
    pp = pm.predict_proba(X_s)[0]
    path_names = list(pm.classes_)

    frozen = score_planning(proposal_from_application(
        authority=s_full["PlanningAuthority"], description=s_full["DevelopmentDescription"],
        units=int(pd.to_numeric(s_full.get("NumResidentialUnits", s_full.get("units", 1)), errors="coerce") or 1),
        site_area_sqm=float(s_full["AreaofSite"]) if pd.notna(s_full.get("AreaofSite")) else None,
        floor_area_sqm=float(s_full["FloorArea"]) if pd.notna(s_full.get("FloorArea")) else None,
        itm_easting=float(s_full["ITMEasting"]), itm_northing=float(s_full["ITMNorthing"]),
        submission_year=2025))

    hist = train[train["PlanningAuthority"] == s_full["PlanningAuthority"]]
    d = np.sqrt((hist["log_units"] - s_log_units) ** 2 * 2.0 +
                (hist["f_apartment"] - s_f_apartment) ** 2 * 4.0 +
                (hist["units"] - s_units_val) ** 2 / 400.0)
    k = min(15, len(d))
    idx = np.argsort(d)[:k]
    nn_ref = float(hist["y"].iloc[idx].mean())
    nn_lo, nn_hi = wilson(int(round(nn_ref * k)), k)
    div_fired = abs(p_ref - nn_ref) > 0.15

    tokens = set(re.findall(r"[a-z0-9]{3,}", str(s_full["DevelopmentDescription"]).lower()))
    refused_hist = train[train["y"] == 1].copy()
    refused_hist["tok"] = refused_hist["DevelopmentDescription"].fillna("").str.lower().apply(
        lambda t: set(re.findall(r"[a-z0-9]{3,}", t)))
    refused_hist["sim"] = refused_hist["tok"].apply(lambda ts: len(ts & tokens) / max(len(ts | tokens), 1))
    top = refused_hist.sort_values("sim", ascending=False).head(12)
    theme_map = {"density_scale": r"density|scale|overdevelop|height|storey|units|number of",
                 "design": r"design|visual|amenity|character|appearance|material|finish",
                 "access_roads": r"access|road|traffic|junction|parking|turning",
                 "water_flood": r"flood|drainage|water|sewer|attenuation",
                 "ecology_heritage": r"ecolog|habitat|tree|natura|archaeolog|heritage|protected",
                 "other": r".*"}
    def theme_of(t):
        for name, pat in theme_map.items():
            if name == "other":
                continue
            if re.search(pat, t or "", re.I):
                return name
        return "other"
    themes_seen = top["DevelopmentDescription"].map(theme_of).value_counts()

    A = []
    A.append("# Planning Underwriting Report — PROSPECTIVE (outcome unknown)")
    A.append(f"**Scheme:** {KEY}")
    A.append(f"**Submitted:** 2025-12-19 | **113 residential units**, c. 4.08 ha, Newcastle, South Dublin County Council (Large-scale Residential Development route)")
    A.append("")
    A.append("## 0. How to read this report")
    A.append("One headline probability per section = the calibrated model estimate; its confidence line shows the historical resolution rate of similar scores (Wilson 95% CI + support). Where a physically-similar reference class disagrees by >15pp, one caution sentence fires. Associations, not causes. This scheme was submitted in December 2025 and its outcome is NOT yet known - every number below is a prospective estimate.")
    A.append("")
    A.append("## 1. Permission risk")
    A.append(f"- **Refusal probability: {p_ref*100:.1f}%** (calibrated; frozen v4 production model: **{frozen['refusal_probability']*100:.1f}%**, calibration +-0.9pp, risk band {frozen['risk_band']})")
    b = band_for(bands["refusal"], p_ref)
    if b:
        A.append(f"- Confidence: historically, applications scored like this were refused at **{b['rate']*100:.1f}%** [{b['ci_lo']*100:.1f}, {b['ci_hi']*100:.1f}] (n={b['n']})")
    A.append(f"- Context: the 15 most similar schemes in this authority were refused at {nn_ref*100:.1f}% [{nn_lo*100:.1f}, {nn_hi*100:.1f}]")
    A.append("- REGIME NOTE: the LRD route replaced the SHD regime in Dec 2021; the production model was trained largely on pre-LRD applications. Treat the refusal estimate as informative but regime-sensitive.")
    if div_fired:
        A.append(f"- **Caution**: model and similar schemes disagree (>15pp) - expected model error is higher.")
    A.append("")
    A.append("## 2. Further-information likelihood")
    A.append(f"- **{p_fi*100:.1f}%**; confidence: similar scores resolved to FI at {band_for(bands['fi'], p_fi)['rate']*100:.1f}% [{band_for(bands['fi'], p_fi)['ci_lo']*100:.1f}, {band_for(bands['fi'], p_fi)['ci_hi']*100:.1f}] (n={band_for(bands['fi'], p_fi)['n']})" if band_for(bands['fi'], p_fi) else f"- **{p_fi*100:.1f}%**")
    A.append("")
    A.append("## 3. Appeal risk - third-party vs applicant")
    b_tp = band_for(bands["appeal_tp"], p_appeal_tp)
    b_ap = band_for(bands["appeal_ap"], p_appeal_ap)
    A.append(f"- **Third-party appeal (against a grant): {p_appeal_tp*100:.1f}%**" +
             (f"; historically, similar scores drew third-party appeals at {b_tp['rate']*100:.1f}% [{b_tp['ci_lo']*100:.1f}, {b_tp['ci_hi']*100:.1f}] (n={b_tp['n']})" if b_tp else ""))
    A.append(f"- Applicant appeal (against a refusal): **{p_appeal_ap*100:.1f}%**" +
             (f"; band {b_ap['rate']*100:.1f}% [{b_ap['ci_lo']*100:.1f}, {b_ap['ci_hi']*100:.1f}] (n={b_ap['n']})" if b_ap else ""))
    A.append("- Party inferred from the decision side (appeals against grants = third-party; against refusals = applicant) - the register does not record party directly.")
    A.append("")
    A.append("## 4. Clean-outcome probability")
    b_clean = band_for(bands["clean"], p_clean)
    A.append(f"- **{p_clean*100:.1f}%** (grant, no FI, no appeal, decision <=12m)" +
             (f"; confidence: similar scores resolved clean at {b_clean['rate']*100:.1f}% [{b_clean['ci_lo']*100:.1f}, {b_clean['ci_hi']*100:.1f}] (n={b_clean['n']})" if b_clean else ""))
    A.append(f"- vs grant probability **{(1-p_ref)*100:.1f}%** - the gap is process friction. Historically clean and grant predictions correlate only r=0.355.")
    A.append("")
    A.append("## 5. Six-month decision tail")
    b_tail = band_for(bands["tail"], p_tail)
    A.append(f"- **{p_tail*100:.1f}%** (overall prevalence 11.1%)" +
             (f"; confidence: similar scores exceeded 6 months at {b_tail['rate']*100:.1f}% [{b_tail['ci_lo']*100:.1f}, {b_tail['ci_hi']*100:.1f}] (n={b_tail['n']})" if b_tail else ""))
    A.append("")
    A.append("## 6. Pre-commencement conditions")
    from devrisk.condition_model import condition_predictions
    cp = condition_predictions(str(s_full["DevelopmentDescription"]),
                               float(pd.to_numeric(s_full.get("NumResidentialUnits", 1), errors="coerce") or 1),
                               s_full["PlanningAuthority"], 2025)
    A.append(f"- **Pre-commencement-condition probability (conditional on grant): {cp['p_precommencement']*100:.1f}%**")
    A.append(f"- Financial-condition probability: **{cp['p_financial']*100:.1f}%**")
    A.append(f"- Model accuracy: {cp['accuracy']} (corpus n={cp['n_corpus']}, {cp['corpus_window']})")
    A.append(f"- National context: pre-commencement {cp['national_prevalence_precommencement']['rate']*100:.1f}% "
             f"[{cp['national_prevalence_precommencement']['ci'][0]*100:.1f}, {cp['national_prevalence_precommencement']['ci'][1]*100:.1f}]; "
             f"financial {cp['national_prevalence_financial']['rate']*100:.1f}% "
             f"[{cp['national_prevalence_financial']['ci'][0]*100:.1f}, {cp['national_prevalence_financial']['ci'][1]*100:.1f}]")
    if cp["era_caveat"]:
        A.append(f"- Note: {cp['era_caveat']}")
    A.append("")
    A.append("## 7. Planning path distribution")
    for i, name in enumerate(path_names):
        A.append(f"- {name}: **{pp[i]*100:.1f}%**" + (" (collapsed)" if pp[i] < 0.02 else ""))
    A.append("")
    A.append("## 8. Precedent-theme matching")
    A.append(f"- {len(top)} most similar historical refusals: theme mix {dict(themes_seen)}")
    for _, r in top.head(5).iterrows():
        A.append(f"  - {r['case_key']}: {theme_of(r['DevelopmentDescription'])} - {str(r.get('DevelopmentDescription'))[:85]}")
    A.append("")
    A.append("## 9. Ultimate success probability")
    p_resub = 0.59
    for n_m, pc in [(1, 0.017), (2, 0.056), (3, 0.187), (4, 0.249)]:
        ult = (1 - p_ref) + p_ref * p_resub * pc
        A.append(f"- assuming {n_m} historically-supported rescue changes if refused: **{ult*100:.1f}%** (gain +{(ult-(1-p_ref))*100:.1f}pp over grant-only)")
    A.append("")
    A.append("## 10. Abandonment base rate")
    A.append("- 41.0% [40.5, 41.5] of refused applications are never resubmitted on the parcel within 4 years (n=40,172)")
    A.append("")
    A.append("## 11. Rescue / mutation plan (if refused)")
    A.append("- Grant rate by historically-supported rescue changes matched: 0 -> 0.0%; 1 -> 1.7% [0.5, 5.9]; 2 -> 5.6% [3.8, 8.1]; 3 -> 18.7% [16.2, 21.5]; 4 -> 24.9% [22.8, 27.1]. Fresh-era confirmed. *Historically associated* - not causal.")
    A.append("")
    A.append("## 12. Drafting associations + measured word effects")
    A.append("- Trimmed/similar description converts 91.5% vs 66.9%; same route 82.8%; adding new technical language anti-associated.")
    A.append("- Measured phrase effects (model-implied sensitivity, not causal; median delta across schemes):")
    A.append("  - Add \"at a reduced density with generous setbacks and landscaping\": **-1.9pp** (79% of schemes improve)")
    A.append("  - Add \"with generous public open space and amenity areas\": **+1.6pp** (counter-intuitive - comparable-bucket artefact; do not present as advice)")
    A.append("  - Add \"including a creche\": ~0pp (no measured effect)")
    A.append("  - Add \"including Part V social housing provision\": ~0pp")
    A.append("  - Remove \"demolition of...\" phrasing: bimodal (-5.3 to +1.7pp, scheme-dependent)")
    A.append("  - Add \"change of use of existing structures\": bimodal (-7.3 to +4.5pp, scheme-dependent)")
    A.append("")
    A.append("### 12b. Scheme-specific counterfactuals (this scheme's own wording and unit count)")
    units_val = int(pd.to_numeric(s_full.get("NumResidentialUnits", 1), errors="coerce") or 1)
    from devrisk.models.planning_adapter import proposal_from_application as pfa, score_planning as sp
    base_p26 = sp(pfa(authority=s_full["PlanningAuthority"], description=s_full["DevelopmentDescription"],
                      units=units_val, site_area_sqm=float(s_full["AreaofSite"]) if pd.notna(s_full.get("AreaofSite")) else None,
                      itm_easting=float(s_full["ITMEasting"]), itm_northing=float(s_full["ITMNorthing"]), submission_year=2025))["refusal_probability"]
    A.append(f"- Base (as submitted, {units_val} units): **{base_p26*100:.1f}%** refusal")
    for new_units in sorted({max(int(units_val * m), 1) for m in (0.7, 0.8, 0.9, 1.1, 1.2, 1.3)}):
        try:
            p26 = sp(pfa(authority=s_full["PlanningAuthority"], description=s_full["DevelopmentDescription"],
                         units=new_units, site_area_sqm=float(s_full["AreaofSite"]) if pd.notna(s_full.get("AreaofSite")) else None,
                         itm_easting=float(s_full["ITMEasting"]), itm_northing=float(s_full["ITMNorthing"]), submission_year=2025))["refusal_probability"]
            A.append(f"- {new_units} units: **{p26*100:.1f}%** ({(p26-base_p26)*100:+.1f}pp)")
        except Exception:
            continue
    for label, fn in [("add \"reduced density with generous setbacks and landscaping\"",
                       lambda d: d + " at a reduced density with generous setbacks and landscaping"),
                      ("remove technical language (drainage/access clauses)",
                       lambda d: re.sub(r"\b(?:attenuation|SUDS|suds|surface water management|drainage network)\b[^,\.]*", "", d, flags=re.I)),
                      ("add \"including a creche\"", lambda d: d + " including a creche")]:
        d2 = fn(str(s_full["DevelopmentDescription"]))
        if d2 == str(s_full["DevelopmentDescription"]):
            continue
        try:
            p26 = sp(pfa(authority=s_full["PlanningAuthority"], description=d2, units=units_val,
                         site_area_sqm=float(s_full["AreaofSite"]) if pd.notna(s_full.get("AreaofSite")) else None,
                         itm_easting=float(s_full["ITMEasting"]), itm_northing=float(s_full["ITMNorthing"]), submission_year=2025))["refusal_probability"]
            A.append(f"- {label}: **{p26*100:.1f}%** ({(p26-base_p26)*100:+.1f}pp)")
        except Exception:
            continue
    A.append("- Model-implied sensitivities only; magnitude context: typical lever size 0-4.5pp.")
    A.append("")
    A.append("## 13. Price vs market benchmark")
    ppr = pd.read_parquet(settings.BRONZE_DIR / "ppr_bronze.parquet",
                          columns=["date_of_sale", "county", "price", "description_of_property"])
    ppr["price"] = ppr["price"].astype(str).str.replace("€", "", regex=False).str.replace(",", "", regex=False)
    ppr["price"] = pd.to_numeric(ppr["price"], errors="coerce")
    ppr["dt"] = pd.to_datetime(ppr["date_of_sale"], utc=True, errors="coerce").dt.tz_localize(None)
    window = ppr[(ppr["dt"] >= SUBMISSION - pd.Timedelta(days=180)) & (ppr["dt"] <= SUBMISSION) &
                 (ppr["county"] == "Dublin")].dropna(subset=["price"])
    if len(window) >= 20:
        A.append(f"- Dublin new-dwelling median, 6 months pre-submission: **€{window['price'].median():,.0f}** (IQR €{window['price'].quantile(0.25):,.0f}-€{window['price'].quantile(0.75):,.0f}, n={len(window)})")
    A.append("")
    A.append("## 14. Site & applicant track record")
    reg_full = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg_full["recv"] = pd.to_datetime(reg_full["ReceivedDate"], utc=True, errors="coerce").dt.tz_localize(None)
    app_full = reg_full[reg_full["case_key"] == KEY].iloc[0]
    same_site = reg_full[((reg_full["ITMEasting"] - app_full["ITMEasting"]).abs() < 150) &
                         ((reg_full["ITMNorthing"] - app_full["ITMNorthing"]).abs() < 150) &
                         (reg_full["case_key"] != KEY)]
    prior = same_site[same_site["recv"] < SUBMISSION].sort_values("recv")
    A.append(f"- Site: {app_full.get('DevelopmentAddress') or 'address not recorded'}")
    A.append(f"- Applicant: {str(app_full.get('ApplicantForename', '')).strip()} {str(app_full.get('ApplicantSurname', '')).strip()}".strip() or "- Applicant: not recorded in the ePlan register")
    A.append(f"- Prior applications within 150m before submission: **{len(prior)}**")
    A.append("")
    A.append("## 15. Static authority baseline")
    bl = pd.read_csv(SILVER / "report" / "zero_day" / "authority_type_baselines.csv")
    bl_row = bl[(bl["authority"] == "South Dublin County Council") & (bl["type"] == "house")]
    if len(bl_row):
        r = bl_row.iloc[0]
        A.append(f"- SDCC house applications: historical refusal rate **{r['refusal_rate']*100:.1f}%** [{r['ci_low']*100:.1f}, {r['ci_high']*100:.1f}], {r['delta_vs_national_pp']:+.1f}pp vs national (n={r['n']})")
    A.append("")
    A.append("## 16. Option / land-bid calculator")
    A.append("- Included only with client assumptions (none supplied) - omitted here.")
    A.append("")
    A.append("## 17. Deliverable competing supply (3km, Monte Carlo)")
    base = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                           columns=["case_key", "PlanningAuthority", "ITMEasting", "ITMNorthing",
                                    "NumResidentialUnits", "GrantDate"]).drop_duplicates("case_key")
    base["units"] = pd.to_numeric(base["NumResidentialUnits"], errors="coerce")
    base["grant_dt"] = pd.to_datetime(base["GrantDate"], utc=True, errors="coerce").dt.tz_localize(None)
    labels = pd.read_csv(SILVER / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    labels = labels[labels["activation_linked"].astype(str).str.lower() == "true"]
    labels["activation"] = pd.to_numeric(labels["activation_days"], errors="coerce")
    base = base.merge(labels[["case_key", "activation"]], on="case_key", how="left")
    base["comm_dt"] = base["grant_dt"] + pd.to_timedelta(base["activation"], unit="D")
    dist = np.sqrt((base["ITMEasting"] - app_full["ITMEasting"]) ** 2 +
                   (base["ITMNorthing"] - app_full["ITMNorthing"]) ** 2)
    pipe = base[(dist <= 3000) & (base["case_key"] != KEY) & (base["grant_dt"] <= SUBMISSION) &
                (base["units"].notna())].copy()
    grant_comm = base.dropna(subset=["comm_dt", "grant_dt"]).copy()
    grant_comm["g2c"] = (grant_comm["comm_dt"] - grant_comm["grant_dt"]).dt.days
    hist_comm = grant_comm[(grant_comm["grant_dt"] < SUBMISSION - pd.Timedelta(days=365)) &
                           (grant_comm["PlanningAuthority"] == s_full["PlanningAuthority"])]
    rng = np.random.default_rng(7)
    for hd, hm in ((730, 24), (1095, 36), (1825, 60)):
        probs = []
        for _, row in pipe.iterrows():
            elapsed = max((SUBMISSION - row["grant_dt"]).days, 0)
            elig = hist_comm["g2c"][hist_comm["g2c"] > elapsed]
            probs.append(float((elig <= elapsed + hd).mean()) if len(elig) >= 15 else 0.5)
        draws = np.array([float((pipe["units"].to_numpy() * (rng.random(len(probs)) < probs)).sum())
                          for _ in range(300)])
        A.append(f"- {hm}m: nominal {pipe['units'].sum():.0f} units; expected deliverable **{np.median(draws):.0f}** (80% range {np.quantile(draws, 0.10):.0f}-{np.quantile(draws, 0.90):.0f})")
    A.append("")
    A.append("## 18. Planning fingerprint")
    A.append(f"- Approval {(1-p_ref)*100:.1f}% | Clean {p_clean*100:.1f}% | 6m tail {p_tail*100:.1f}% | FI {p_fi*100:.1f}% | Appeal {p_appeal*100:.1f}%")
    A.append("- Divergence layer: " + ("FIRED on refusal risk" if div_fired else "no divergence fired"))
    A.append("- Confidence line = the weakest component's bound. No aggregate score.")
    A.append("")
    A.append("---")
    A.append("## Dossier - PROSPECTIVE REPORT")
    A.append("- Outcome NOT known as of 2026-10-08. This report is a submission-date estimate; outcomes will be logged when the decision publishes.")

    (OUT / "report_LRD25A_0014W.md").write_text("\n".join(A) + "\n", encoding="utf-8")
    print("\n".join(A)[:2800])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
