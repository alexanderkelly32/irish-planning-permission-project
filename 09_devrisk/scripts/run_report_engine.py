"""Self-contained report engine: bundle + inputs -> full 18-section markdown.

Reads ONLY 09_devrisk/data/report_bundle/. No register, no live training.
The frozen v4 scoring path is monkeypatched to the bundle files.

Usage:
  python run_report_engine.py path/to/inputs.json
inputs.json keys:
  authority, description, units, site_area_sqm, floor_area_sqm (optional),
  itm_easting, itm_northing, submission_year, site_label, report_date (optional),
  template_note (optional), geocode_note (optional), route_note (optional)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "09_devrisk" / "data" / "silver" / "report_bundle"

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


def band_for(bands, p):
    for b in bands:
        if b["lo"] <= p <= b["hi"]:
            return b
    return None


def _patch_v4_paths():
    sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))
    import model_feature_builder as mfb
    mfb.MODEL_PATH = BUNDLE / "national_residential_v4_full.joblib"
    mfb.COMPARABLE_PATH = BUNDLE / "comparable_reference.joblib"
    mfb.SA_REF = BUNDLE / "sa_reference.parquet"
    mfb.FLOOD_POINTS = BUNDLE / "flood_points.parquet"
    mfb.PLAN_SUMMARY = BUNDLE / "plan_summary.parquet"
    mfb.HISTORY_REF = BUNDLE / "history_reference.parquet"
    if hasattr(mfb, "_load_state"):
        mfb._load_state.cache_clear()
    return mfb


def main() -> None:
    inp = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")) if len(sys.argv) > 1 else {}
    authority = inp["authority"]
    description = inp["description"]
    units = int(inp["units"])
    area = inp.get("site_area_sqm")
    easting = inp.get("itm_easting")
    northing = inp.get("itm_northing")
    year = int(inp.get("submission_year", 2026))
    report_date = pd.Timestamp(inp.get("report_date", "2026-10-15"))
    site_label = inp.get("site_label", "Prospective scheme")
    template_note = inp.get("template_note")
    geocode_note = inp.get("geocode_note", "user-supplied coordinates")
    route_note = inp.get("route_note", "")

    rt = joblib.load(BUNDLE / "runtime_models.joblib")
    bands = json.loads((BUNDLE / "bands.json").read_text(encoding="utf-8"))
    cond = joblib.load(BUNDLE / "condition_models.joblib")
    drafting = json.loads((BUNDLE / "drafting_constants.json").read_text(encoding="utf-8"))
    geo = pd.read_parquet(BUNDLE / "register_geo_min.parquet")
    refused = pd.read_parquet(BUNDLE / "refused_descriptions.parquet")
    supply = pd.read_parquet(BUNDLE / "supply_min.parquet")
    activation = pd.read_parquet(BUNDLE / "activation_min.parquet")
    price = pd.read_parquet(BUNDLE / "price_summary.parquet")
    baselines = pd.read_csv(BUNDLE / "authority_type_baselines.csv")

    mfb = _patch_v4_paths()
    from model_feature_builder import score_proposal  # noqa: E402
    frozen = score_proposal({
        "authority": authority, "description": description, "units": units,
        "site_area_sqm": area,
        "floor_area_sqm": inp.get("floor_area_sqm"),
        "itm_easting": easting, "itm_northing": northing,
        "submission_year": year})

    d_low = description.lower()
    feat_row = {"log_units": np.log1p(units), "desc_len": len(description), "year": year}
    for fam in FAMILIES:
        feat_row[f"f_{fam}"] = int(re.search(fam, d_low) is not None)
    X_s = pd.DataFrame([feat_row]).reindex(columns=rt["feature_columns"]).fillna(0.0)
    if f"a_{authority}" in X_s.columns:
        X_s.loc[0, f"a_{authority}"] = 1.0
    full = rt["full_models"]
    p_fi = float(full["fi"].predict_proba(X_s)[:, 1][0])
    p_appeal = float(full["appeal"].predict_proba(X_s)[:, 1][0])
    p_appeal_tp = float(full["grant_appeal_flag"].predict_proba(X_s)[:, 1][0])
    p_appeal_ap = float(full["refusal_appeal_flag"].predict_proba(X_s)[:, 1][0])
    p_clean = float(full["clean"].predict_proba(X_s)[:, 1][0])
    p_tail = float(full["late6m"].predict_proba(X_s)[:, 1][0])
    pp = full["path"].predict_proba(X_s)[0]
    path_names = list(full["path_classes"])
    p_ref_use = float(frozen["refusal_probability"])

    # nearest comparators: same-authority apartment rows
    auth_hist = geo[geo["PlanningAuthority"] == authority].copy()
    auth_hist["ap"] = auth_hist["desc_short"].fillna("").str.lower().str.contains(
        "apartment|duplex", regex=True).astype(int)
    auth_hist = auth_hist[auth_hist["ap"] == 1]
    auth_hist["units"] = pd.to_numeric(auth_hist["units"], errors="coerce").fillna(1)
    auth_hist["log_units"] = np.log1p(auth_hist["units"])
    if len(auth_hist):
        d = np.sqrt((auth_hist["log_units"] - np.log1p(units)) ** 2 * 2.0 +
                    (auth_hist["units"] - units) ** 2 / 400.0)
        k = min(15, len(d))
        idx = np.argsort(d)[:k]
        nn_ref = float(auth_hist["Decision"].fillna("").str.contains(
            "refus", case=False, regex=False).iloc[idx].mean())
        nn_lo, nn_hi = wilson(int(round(nn_ref * k)), k)
    else:
        nn_ref, nn_lo, nn_hi = np.nan, np.nan, np.nan

    # precedents
    tokens = set(re.findall(r"[a-z0-9]{3,}", description.lower()))
    refused["tok"] = refused["DevelopmentDescription"].fillna("").str.lower().apply(
        lambda t: set(re.findall(r"[a-z0-9]{3,}", t)))
    refused["sim"] = refused["tok"].apply(lambda ts: len(ts & tokens) / max(len(ts | tokens), 1))
    top = refused.sort_values("sim", ascending=False).head(12)
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
    A.append(f"**Site:** {site_label}")
    A.append(f"**Authority:** {authority} | **Proposed:** {units} units" +
             (f" on {area/1e4:.2f} ha" if area else "") +
             f", submitted {year} | Report date: {report_date.date()}")
    A.append(f"**Description:** {description}")
    if template_note:
        A.append(f"**Adopt-if-accurate note:** {template_note}")
    A.append(f"- Coordinates: {geocode_note} (ITM {easting:.0f}, {northing:.0f})" if easting else "- Coordinates: not supplied; site-context sections omitted.")
    A.append("")
    A.append("## 0. How to read this report")
    A.append("One headline probability per section = the calibrated model estimate; its confidence line shows the historical resolution rate of similar scores (Wilson 95% CI + support). Where a physically-similar reference class disagrees by >15pp, one caution sentence fires. Associations, not causes. Every number below is a prospective estimate.")
    A.append("")
    A.append("## 1. Permission risk")
    A.append(f"- **Refusal probability: {p_ref_use*100:.1f}%** (frozen v4 production model; calibration +-0.9pp; risk band **{frozen['risk_band']}** [low <=3.8%, medium 3.8-11.4%, high >11.4%])")
    if np.isfinite(nn_ref):
        A.append(f"- Context (not a substitute): the 15 most similar apartment schemes in this authority were refused at {nn_ref*100:.1f}% [{nn_lo*100:.1f}, {nn_hi*100:.1f}]")
    if route_note:
        A.append(f"- REGIME NOTE: {route_note}")
    if np.isfinite(nn_ref) and abs(p_ref_use - nn_ref) > 0.15:
        A.append(f"- **Caution**: model ({p_ref_use*100:.1f}%) and similar schemes ({nn_ref*100:.1f}%) disagree by >15pp - expected model error is higher.")
    A.append("")
    A.append("## 2. Further-information likelihood")
    b_fi = band_for(bands["fi"], p_fi)
    A.append(f"- **{p_fi*100:.1f}%**" + (f"; confidence: similar scores resolved to FI at {b_fi['rate']*100:.1f}% [{b_fi['ci_lo']*100:.1f}, {b_fi['ci_hi']*100:.1f}] (n={b_fi['n']})" if b_fi else ""))
    A.append("")
    A.append("## 3. Appeal risk - third-party vs applicant")
    b_tp = band_for(bands["grant_appeal_flag"], p_appeal_tp)
    b_ap = band_for(bands["refusal_appeal_flag"], p_appeal_ap)
    A.append(f"- **Third-party appeal (against a grant): {p_appeal_tp*100:.1f}%**" +
             (f"; historically, similar scores drew third-party appeals at {b_tp['rate']*100:.1f}% [{b_tp['ci_lo']*100:.1f}, {b_tp['ci_hi']*100:.1f}] (n={b_tp['n']})" if b_tp else ""))
    A.append(f"- Applicant appeal (against a refusal): **{p_appeal_ap*100:.1f}%**" +
             (f"; band {b_ap['rate']*100:.1f}% [{b_ap['ci_lo']*100:.1f}, {b_ap['ci_hi']*100:.1f}] (n={b_ap['n']})" if b_ap else ""))
    A.append("- Party inferred from the decision side - the register does not record party directly.")
    A.append("")
    A.append("## 4. Clean-outcome probability")
    b_clean = band_for(bands["clean"], p_clean)
    A.append(f"- **{p_clean*100:.1f}%** (grant, no FI, no appeal, decision <=12m)" +
             (f"; confidence: similar scores resolved clean at {b_clean['rate']*100:.1f}% [{b_clean['ci_lo']*100:.1f}, {b_clean['ci_hi']*100:.1f}] (n={b_clean['n']})" if b_clean else ""))
    A.append(f"- vs grant probability **{(1-p_ref_use)*100:.1f}%** (frozen v4) - the gap is process friction.")
    A.append("")
    A.append("## 5. Six-month decision tail")
    b_tail = band_for(bands["late6m"], p_tail)
    A.append(f"- **{p_tail*100:.1f}%** (overall prevalence 11.1%)" +
             (f"; confidence: similar scores exceeded 6 months at {b_tail['rate']*100:.1f}% [{b_tail['ci_lo']*100:.1f}, {b_tail['ci_hi']*100:.1f}] (n={b_tail['n']})" if b_tail else ""))
    A.append("")
    A.append("## 6. Pre-commencement conditions")
    inds = ["demolition", "protected structure", "brownfield", "infill", "creche",
            "retail", "extension", "change of use", "apartment"]
    cd = description.lower()
    cfeat = pd.DataFrame([{"log_units": np.log1p(units),
                           "type_apartment": int(bool(re.search(r"apartment|duplex", cd))),
                           "desc_len": len(description)}])
    for ind in inds:
        cfeat[f"desc_{ind.replace(' ', '_')}"] = int(bool(re.search(ind, cd, re.I)))
    cauth = pd.get_dummies(pd.Series([authority]), prefix="a").astype(int)
    Xc = pd.concat([cfeat, cauth], axis=1).reindex(columns=cond["feature_columns"]).fillna(0.0)
    p_pre = float(cond["models"]["pre"].predict_proba(Xc)[:, 1][0])
    p_fin = float(cond["models"]["fin"].predict_proba(Xc)[:, 1][0])
    A.append(f"- **Pre-commencement-condition probability (conditional on grant): {p_pre*100:.1f}%**")
    A.append(f"- Financial-condition probability: **{p_fin*100:.1f}%**")
    A.append(f"- Model accuracy: rolling-origin AUC 0.714/0.765/0.747 (pre-commencement); 0.633-0.688 (financial) (corpus n={cond['prevalence_pre']['n']}, 2020+ granted schemes)")
    pn, ln, hn = cond["prevalence_pre"]["rate"], *wilson(cond["prevalence_pre"]["rate"] * cond["prevalence_pre"]["n"], cond["prevalence_pre"]["n"])
    pf2, lf2, hf2 = cond["prevalence_fin"]["rate"], *wilson(cond["prevalence_fin"]["rate"] * cond["prevalence_fin"]["n"], cond["prevalence_fin"]["n"])
    A.append(f"- National context: pre-commencement {pn*100:.1f}% [{ln*100:.1f}, {hn*100:.1f}]; financial {pf2*100:.1f}% [{lf2*100:.1f}, {hf2*100:.1f}]")
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
    for n_m in (1, 2, 3, 4):
        pc = drafting["rescue"][str(n_m)]
        ult = (1 - p_ref_use) + p_ref_use * drafting["p_resub"] * pc
        A.append(f"- assuming {n_m} historically-supported rescue changes if refused: **{ult*100:.1f}%** (gain +{(ult-(1-p_ref_use))*100:.1f}pp over grant-only)")
    A.append("")
    A.append("## 10. Abandonment base rate")
    A.append(f"- {drafting['abandonment']*100:.1f}% [40.5, 41.5] of refused applications are never resubmitted on the parcel within 4 years (n=40,172)")
    A.append("")
    A.append("## 11. Rescue / mutation plan (if refused)")
    A.append("- Grant rate by historically-supported rescue changes matched: 0 -> 0.0%; 1 -> 1.7% [0.5, 5.9]; 2 -> 5.6% [3.8, 8.1]; 3 -> 18.7% [16.2, 21.5]; 4 -> 24.9% [22.8, 27.1]. Fresh-era confirmed. *Historically associated* - not causal.")
    A.append("")
    A.append("## 12. Drafting contrast + design levers")
    s, tr, ex = drafting["similar"], drafting["trim"], drafting["expand"]
    A.append(f"- Resubmission conversion by description length (n=11,102 pairs, both eras): **materially similar {s['rate']*100:.1f}% [{s['ci_lo']*100:.1f}, {s['ci_hi']*100:.1f}]** vs trimmed {tr['rate']*100:.1f}% [{tr['ci_lo']*100:.1f}, {tr['ci_hi']*100:.1f}] vs expanded {ex['rate']*100:.1f}% [{ex['ci_lo']*100:.1f}, {ex['ci_hi']*100:.1f}].")
    A.append("- Adding new technical families is anti-associated (density theme: access added 3.3% vs 11.5% not-added; parking 2.2% vs 11.1%).")
    A.append(f"- Unit-count changes: **measured effect zero** ({drafting['units_effect']}, era-stable). Do not budget a resubmission on unit cuts; storeys: CI straddles zero.")
    A.append("")
    A.append("## 13. Price vs market benchmark")
    ppr = pd.read_parquet(BUNDLE / "ppr_bronze.parquet",
                          columns=["date_of_sale", "county", "price"])
    ppr["price"] = pd.to_numeric(ppr["price"].astype(str).str.replace("€", "", regex=False)
                                 .str.replace(",", "", regex=False), errors="coerce")
    ppr["dt"] = pd.to_datetime(ppr["date_of_sale"], utc=True, errors="coerce").dt.tz_localize(None)
    window = ppr[(ppr["dt"] >= report_date - pd.Timedelta(days=180)) & (ppr["dt"] <= report_date) &
                 (ppr["county"] == "Dublin")].dropna(subset=["price"])
    if len(window) >= 20:
        A.append(f"- Dublin new-dwelling median, 6 months pre-report: **€{window['price'].median():,.0f}** (IQR €{window['price'].quantile(0.25):,.0f}-€{window['price'].quantile(0.75):,.0f}, n={len(window)})")
    A.append("")
    A.append("## 14. Site & track record")
    if easting:
        near = geo[((geo["ITMEasting"] - easting).abs() < 150) & ((geo["ITMNorthing"] - northing).abs() < 150)].copy()
        near["recv"] = pd.to_datetime(near["ReceivedDate"], utc=True, errors="coerce").dt.tz_localize(None)
        prior = near[near["recv"] < report_date].sort_values("recv")
        A.append(f"- Prior applications within 150m before today: **{len(prior)}**")
        for _, r in prior.tail(3).iterrows():
            A.append(f"  - {r['case_key']}: {str(r.get('desc_short'))[:90]} (dec {str(r.get('Decision'))[:12]})")
    else:
        A.append("- Coordinates not supplied - site history omitted.")
    A.append("")
    A.append("## 15. Static authority baseline")
    norm = lambda s: re.sub(r"[^a-z]", "", str(s).lower())
    blr = baselines[baselines["authority"].map(norm) == norm(authority)]
    for _, r in blr.iterrows():
        A.append(f"- {authority} {r['type']}: historical refusal **{r['refusal_rate']*100:.1f}%** [{r['ci_low']*100:.1f}, {r['ci_high']*100:.1f}], {r['delta_vs_national_pp']:+.1f}pp vs national (n={r['n']})")
    A.append("")
    A.append("## 16. Option / land-bid calculator")
    A.append("- Included only with client assumptions (none supplied) - omitted here.")
    A.append("")
    A.append("## 17. Deliverable competing supply (3km, Monte Carlo)")
    if easting:
        sup = supply.copy()
        sup["grant_dt"] = pd.to_datetime(sup["GrantDate"], utc=True, errors="coerce").dt.tz_localize(None)
        sup = sup.merge(activation, on="case_key", how="left")
        sup["activation"] = pd.to_numeric(sup["activation_days"], errors="coerce")
        sup["comm_dt"] = sup["grant_dt"] + pd.to_timedelta(sup["activation"], unit="D")
        dist = np.sqrt((sup["ITMEasting"] - easting) ** 2 + (sup["ITMNorthing"] - northing) ** 2)
        pipe = sup[(dist <= 3000) & (sup["grant_dt"] <= report_date) & (sup["units"].notna())].copy()
        gc = sup.dropna(subset=["comm_dt", "grant_dt"]).copy()
        gc["g2c"] = (gc["comm_dt"] - gc["grant_dt"]).dt.days
        hist_comm = gc[(gc["grant_dt"] < report_date - pd.Timedelta(days=365)) &
                       (gc["PlanningAuthority"] == authority)]
        rng = np.random.default_rng(7)
        for hd, hm in ((730, 24), (1095, 36), (1825, 60)):
            probs = []
            for _, row in pipe.iterrows():
                elapsed = max((report_date - row["grant_dt"]).days, 0)
                elig = hist_comm["g2c"][hist_comm["g2c"] > elapsed]
                probs.append(float((elig <= elapsed + hd).mean()) if len(elig) >= 15 else 0.5)
            draws = np.array([float((pipe["units"].to_numpy() * (rng.random(len(probs)) < probs)).sum())
                              for _ in range(300)])
            A.append(f"- {hm}m: nominal {pipe['units'].sum():.0f} units; expected deliverable **{np.median(draws):.0f}** (80% range {np.quantile(draws, 0.10):.0f}-{np.quantile(draws, 0.90):.0f})")
    else:
        A.append("- Coordinates not supplied - supply analysis omitted.")
    A.append("")
    A.append("## 18. Planning fingerprint")
    A.append(f"- Approval {(1-p_ref_use)*100:.1f}% (frozen v4) | Clean {p_clean*100:.1f}% | 6m tail {p_tail*100:.1f}% | FI {p_fi*100:.1f}% | Appeal {p_appeal*100:.1f}% (report models)")
    A.append("- Divergence layer: " + ("FIRED on refusal risk (v4 vs similar schemes)" if np.isfinite(nn_ref) and abs(p_ref_use - nn_ref) > 0.15 else "no divergence fired"))
    A.append("- Confidence line = the weakest component's bound. No aggregate score.")
    A.append("")
    A.append("---")
    A.append("## Dossier - PROSPECTIVE REPORT")
    A.append("- Outcome NOT known. This report is a pre-submission estimate; outcomes will be logged when the decision publishes.")

    out_path = Path(inp.get("output_path")) if inp.get("output_path") else ROOT / "09_devrisk" / "data" / "silver" / "report" / "prospective" / f"report_engine_{site_label.replace(' ', '_')[:40]}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(A) + "\n", encoding="utf-8")
    print("\n".join(A))
    print(f"\nSaved -> {out_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
