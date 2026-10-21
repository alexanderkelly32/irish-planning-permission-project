"""Runner: post-grant readiness event extraction + fast/slow clock comparison.

Reads readiness doc JSONs (run_readiness_download.py output), extracts dated
post-grant events (compliance submissions/acceptances, bonds, contributions,
Part V, drainage/SuDS, roads, Uisce, archaeology/ecology, naming, revised
details), builds per-scheme readiness clocks, compares fast vs slow
commencement residuals. Analysis only - no model fit.

Outputs: silver/idocs/readiness_events.csv + readiness_clocks_report.json
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

DOCS = settings.SILVER_DIR / "idocs" / "docs"

DATE_RES = [
    re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})\b"),
    re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)[,.]?\s+(\d{2,4})", re.I),
    re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?[,.]?\s+(\d{2,4})", re.I),
]
MONTHS = {m.lower(): i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"])}

MONTH_PATTERN = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
                 r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)")
MONTH_PREFIX = {k: i + 1 for i, k in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}

MONTH_CAP = "(" + MONTH_PATTERN + ")"

NUM_DATE_RE = re.compile(r"\b([LlOo]?\d{1,2})\s*[/.|]\s*([LlOo]?\d{1,2})\s*[/.|]\s*(\d{2,4})\b")
DAY_MONTH_RE = re.compile(
    r"\b(\d{1,2})\s*(?:st|nd|rd|th)?\s*" + MONTH_CAP + r"[\s,.]*(\d{4})(?:\d{1,2}:\d{2})?\b", re.I)
MONTH_DAY_RE = re.compile(
    r"\b" + MONTH_CAP + r"[\s,.]*(\d{1,2})\s*(?:st|nd|rd|th)?[\s,.]*(\d{4})\b", re.I)
MONTH_YEAR_RE = re.compile(r"\b" + MONTH_CAP + r"[\s,.]*(\d{4})\b", re.I)
LABEL_RE = re.compile(r"\b(date|dated|recd\.?|received|sent|issued)\s*:?\s*", re.I)


def _clean_num(g: str) -> str:
    return g.translate(str.maketrans("lLOo", "1100"))


def _month_num(name: str) -> int | None:
    return MONTH_PREFIX.get(name.lower()[:3])


def _mk_ts(y: int, mo: int, d: int):
    if 1995 <= y <= 2028 and 1 <= mo <= 12 and 1 <= d <= 31:
        try:
            return pd.Timestamp(year=y, month=mo, day=d)
        except ValueError:
            return None
    return None


def _scan(text: str, month_year_ok: bool = False):
    for m in NUM_DATE_RE.finditer(text or ""):
        d, mo, y = int(_clean_num(m.group(1))), int(_clean_num(m.group(2))), int(_clean_num(m.group(3)))
        if y < 100:
            y += 2000
        ts = _mk_ts(y, mo, d)
        if ts is not None:
            return ts
    for m in DAY_MONTH_RE.finditer(text or ""):
        ts = _mk_ts(int(m.group(3)), _month_num(m.group(2)), int(_clean_num(m.group(1))))
        if ts is not None:
            return ts
    for m in MONTH_DAY_RE.finditer(text or ""):
        ts = _mk_ts(int(m.group(3)), _month_num(m.group(1)), int(m.group(2)))
        if ts is not None:
            return ts
    if month_year_ok:
        for m in MONTH_YEAR_RE.finditer(text or ""):
            mo = _month_num(m.group(1))
            if mo and 1995 <= int(m.group(2)) <= 2028:
                return pd.Timestamp(year=int(m.group(2)), month=mo, day=1)
    return None


def extract_date(text: str, comment: str):
    """Return (Timestamp|None, source). Observed dates only, no inference."""
    if text:
        for m in LABEL_RE.finditer(text):
            window = text[m.end():m.end() + 90]
            ts = _scan(window)
            if ts is not None:
                return ts, "date_label"
    if text:
        ts = _scan(text[:400])
        if ts is not None:
            return ts, "header"
    if comment:
        ts = _scan(comment)
        if ts is not None:
            return ts, "comment"
    if text:
        ts = _scan(text, month_year_ok=True)
        if ts is not None:
            return ts, "month_only"
    return None, None


def doc_date(text: str, comment: str):
    ts, _ = extract_date(text, comment)
    return ts

CATEGORY_RE = {
    "bond_security": r"bond|security",
    "contribution": r"contribution|development lev|financial cond",
    "part_v": r"part ?v|social housing|affordable",
    "drainage_suds": r"drainage|suds|surface water|attenuation",
    "roads_access": r"road|access|footpath|junction|car park|traffic",
    "uisce": r"uisce|irish water|water supply|wastewater|sewer|watermain",
    "archaeology": r"archaeolog",
    "ecology": r"ecolog|habitat|bat |bird|tree|natura|landscap",
    "naming": r"naming|name plaque|development name",
    "phasing": r"phas",
    "revised_details": r"revised (?:plan|detail|drawing)|final (?:drawing|detail|plan)s?",
}
ACCEPT_RE = re.compile(r"approved|agreed|accepted|complied with|compliance confirmed|in order|satisfied|acceptable", re.I)
REJECT_RE = re.compile(r"not accepted|not in order|refused|returned|incomplete|does not comply|not agreed|requested further|further information", re.I)
SUBMIT_RE = re.compile(r"received|submitted|lodged|enclosed|herewith", re.I)
COND_NO_RE = re.compile(r"condition (?:no\.? ?|number )?(\d{1,2}(?:\([a-z]\))?)", re.I)
ALL_CLEAR_RE = re.compile(r"all (?:pre-?commencement )?conditions (?:have been )?(?:complied|now complied|are complied|compiled)|compliance with all conditions|conditions .{0,40}complied with", re.I)


def parse_date(text: str):
    ts, _ = extract_date(text, "")
    return ts


def classify(text: str, comment: str, doc_type: str):
    blob = f"{doc_type} {comment} {text or ''}"
    categories = [name for name, pat in CATEGORY_RE.items() if re.search(pat, blob, re.I)]
    if ACCEPT_RE.search(blob) and ALL_CLEAR_RE.search(blob):
        status = "all_clear"
    elif ACCEPT_RE.search(blob):
        status = "accepted"
    elif REJECT_RE.search(blob):
        status = "rejected"
    elif SUBMIT_RE.search(blob):
        status = "submitted"
    else:
        status = "noted"
    cond_m = COND_NO_RE.search(comment or "")
    cond_no = cond_m.group(1) if cond_m else None
    return categories, status, cond_no


def main() -> None:
    with zipfile.ZipFile(settings.SILVER_DIR / "audit_packs" / "PACK_24_residual_forensics.zip") as z:
        cohort = pd.read_csv(z.open("residual_forensics_cohort.csv"))
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = register[["case_key", "GrantDate"]].drop_duplicates("case_key")
    reg["grant_dt"] = pd.to_datetime(reg["GrantDate"], utc=True, errors="coerce")
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    labels["activation"] = pd.to_numeric(labels["activation_days"], errors="coerce")
    linked = labels[labels["activation_linked"].astype(str).str.lower() == "true"]

    cohort = cohort.merge(reg[["case_key", "grant_dt"]], on="case_key", how="left")
    cohort = cohort.merge(linked[["case_key", "activation"]], on="case_key", how="left")
    cohort["ck"] = cohort["case_key"].str.replace(" ", "_").str[:80]

    events = []
    for scheme_dir in sorted(DOCS.glob("*/readiness")):
        key = scheme_dir.parent.name
        row = cohort[cohort["ck"] == key]
        if row.empty:
            continue
        app_no = row["application_number"].iloc[0]
        for doc_json in sorted(scheme_dir.glob("*.json")):
            try:
                d = json.loads(doc_json.read_text(encoding="utf-8"))
            except Exception:
                continue
            if d.get("status") != "ok" or not d.get("text"):
                continue
            text = d["text"]
            comment = d.get("comment", "")
            dt = doc_date(text, comment)
            categories, status, cond_no = classify(text, comment, d.get("type", ""))
            events.append({
                "case_key": row["case_key"].iloc[0],
                "app_no": app_no,
                "docid": d.get("docid"),
                "doc_type": d.get("type", ""),
                "comment": comment,
                "event_date": dt,
                "event_categories": "|".join(categories),
                "event_status": status,
                "condition_no": cond_no,
                "supporting_text": (text or "")[:300],
                "source_file": str(doc_json),
            })
    frame = pd.DataFrame(events)
    if frame.empty:
        print(json.dumps({"error": "no events"}, indent=2))
        return
    frame = frame.sort_values(["case_key", "event_date"], na_position="last")
    frame.to_csv(settings.SILVER_DIR / "idocs" / "readiness_events.csv", index=False)

    clocks = []
    for ck, group in frame.groupby("case_key"):
        row = cohort[cohort["ck"] == ck.replace(" ", "_")[:80]]
        if row.empty:
            row = cohort[cohort["case_key"] == ck]
        if row.empty:
            continue
        grant_dt = row["grant_dt"].iloc[0]
        if pd.notna(grant_dt):
            grant_dt = pd.Timestamp(grant_dt).tz_localize(None)
        activation = row["activation"].iloc[0]
        dated = group.dropna(subset=["event_date"]).sort_values("event_date")
        dated = dated[dated["event_date"] >= (grant_dt - pd.Timedelta(days=30))]
        entry = {"case_key": ck, "n_events": int(len(group)),
                 "n_dated": int(len(dated)), "n_docs": int(group["docid"].nunique())}
        if pd.notna(grant_dt):
            if len(dated):
                first = dated["event_date"].iloc[0]
                entry["grant_to_first_activity"] = (first - grant_dt).days
                accepted = dated[dated["event_status"].isin(["accepted", "all_clear"])]
                if len(accepted):
                    entry["grant_to_first_accepted"] = (accepted["event_date"].iloc[0] - grant_dt).days
                    entry["grant_to_last_clearance"] = (accepted["event_date"].iloc[-1] - grant_dt).days
                clear = dated[dated["event_status"] == "all_clear"]
                if len(clear):
                    entry["grant_to_all_clear"] = (clear["event_date"].iloc[0] - grant_dt).days
                if pd.notna(activation):
                    commenced = grant_dt + pd.Timedelta(days=float(activation))
                    pre_comm = dated[dated["event_date"] <= commenced]
                    entry["n_events_pre_commencement"] = int(len(pre_comm))
                    pre_acc = pre_comm[pre_comm["event_status"].isin(["accepted", "all_clear"])]
                    if len(pre_acc):
                        last_pre = pre_acc["event_date"].iloc[-1]
                        entry["grant_to_last_precomm_clearance"] = (last_pre - grant_dt).days
                        entry["last_precomm_clearance_to_commencement"] = activation - (last_pre - grant_dt).days
                    else:
                        entry["grant_to_last_precomm_clearance"] = None
                        entry["last_precomm_clearance_to_commencement"] = None
                    entry["commencement_days"] = activation
            entry["n_rejections"] = int((group["event_status"] == "rejected").sum())
            entry["n_accepted"] = int(group["event_status"].isin(["accepted", "all_clear"]).sum())
            entry["has_all_clear"] = int((group["event_status"] == "all_clear").sum() > 0)
            entry["n_conditions_seen"] = int(group["condition_no"].nunique(dropna=True))
            cond_iter = group.dropna(subset=["condition_no"]).groupby("condition_no")["event_status"].apply(list)
            entry["n_iterated_conditions"] = int(sum(
                1 for v in cond_iter if "rejected" in v and any(s in ("accepted", "all_clear") for s in v)))
        clocks.append(entry)
    clocks_df = pd.DataFrame(clocks)
    clocks_df.to_csv(settings.SILVER_DIR / "idocs" / "readiness_clocks.csv", index=False)

    merged = cohort.merge(clocks_df, on="case_key", how="inner")
    fast = merged[merged["residual_group"].str.contains("fast", case=False, na=False)]
    slow = merged[merged["residual_group"].str.contains("slow", case=False, na=False)]
    metrics = ["grant_to_first_activity", "grant_to_first_accepted", "grant_to_last_clearance",
               "grant_to_all_clear", "grant_to_last_precomm_clearance",
               "last_precomm_clearance_to_commencement", "n_events", "n_rejections",
               "n_accepted", "n_conditions_seen", "n_iterated_conditions",
               "n_events_pre_commencement"]
    report = {
        "coverage": {
            "schemes_with_events": int(len(merged)),
            "of_cohort": 48,
            "schemes_with_dated_events": int(merged["n_dated"].fillna(0).gt(0).sum()),
            "schemes_with_all_clear": int(merged["has_all_clear"].fillna(0).sum()),
        },
        "fast_vs_slow_median": {},
    }
    for metric in metrics:
        if metric in merged.columns:
            fv = fast[metric].dropna().median()
            sv = slow[metric].dropna().median()
            report["fast_vs_slow_median"][metric] = {
                "fast": round(float(fv), 1) if pd.notna(fv) else None,
                "slow": round(float(sv), 1) if pd.notna(sv) else None,
                "n_fast": int(fast[metric].notna().sum()),
                "n_slow": int(slow[metric].notna().sum()),
            }
    if "last_precomm_clearance_to_commencement" in merged.columns:
        sub = merged.dropna(subset=["last_precomm_clearance_to_commencement"])
        report["precomm_clearance_to_commencement"] = {
            "n": int(len(sub)),
            "median_last_precomm_clearance_to_commencement":
                round(float(sub["last_precomm_clearance_to_commencement"].median()), 1),
            "min": round(float(sub["last_precomm_clearance_to_commencement"].min()), 1),
            "max": round(float(sub["last_precomm_clearance_to_commencement"].max()), 1),
            "median_commencement": round(float(sub["commencement_days"].median()), 1),
        }
    out = settings.SILVER_DIR / "idocs" / "readiness_clocks_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
