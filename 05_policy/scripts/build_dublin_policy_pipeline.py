#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from pypdf import PdfReader
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.metrics.pairwise import linear_kernel
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


ROOT = Path(__file__).resolve().parents[2]
POLICY_ROOT = ROOT / "05_policy"
CURRENT_DIR = POLICY_ROOT / "current"
EXTRACTED_TEXT_DIR = POLICY_ROOT / "documents" / "extracted_text"
MODEL_DIR = CURRENT_DIR / "models"

POLICY_MANIFEST = POLICY_ROOT / "source_data" / "dublin_policy_manifest.csv"
FI_DATA = ROOT / "04_fi" / "current" / "greater_than_10_units_with_refusal_reasons_plus_ge10_fi_requests_enriched.csv"
FLOOD_DATA = ROOT / "01_flood" / "current" / "ge10_with_flooding.csv"
REFUSAL_CASES = ROOT / "03_refusal" / "current" / "refusal_reasons_cases_master.csv"
OPENAI_KEY_FILE = ROOT / "openai_key.env"

DUBLIN_AUTHORITIES = [
    "Dublin City Council",
    "Dun Laoghaire Rathdown County Council",
    "Fingal County Council",
    "South Dublin County Council",
]

THEME_PATTERNS = {
    "traffic_access": [
        r"\btraffic\b",
        r"\baccess\b",
        r"\bjunction\b",
        r"\broad\b",
        r"\bparking\b",
        r"\bvisibility\b",
        r"\bdmurs\b",
        r"\btransport\b",
        r"\bcycle\b",
        r"\bpedestrian\b",
        r"\bmobility\b",
    ],
    "flooding_drainage": [
        r"\bflood",
        r"\bsurface water\b",
        r"\bdrainage\b",
        r"\bsuds\b",
        r"\battenuation\b",
        r"\boverland flow\b",
        r"\bstormwater\b",
    ],
    "water_wastewater": [
        r"\birish water\b",
        r"\bwastewater\b",
        r"\bsewer\b",
        r"\bwater supply\b",
        r"\bfoul water\b",
        r"\bpublic water\b",
        r"\binfrastructure\b",
        r"\bservices\b",
    ],
    "design_layout": [
        r"\bdesign\b",
        r"\blayout\b",
        r"\burban design\b",
        r"\bpublic realm\b",
        r"\bstreetscape\b",
        r"\bcharacter\b",
        r"\barchitectural\b",
    ],
    "density_scale": [
        r"\bdensity\b",
        r"\boverdevelopment\b",
        r"\bscale\b",
        r"\bheight\b",
        r"\bmass(ing)?\b",
        r"\bplot ratio\b",
        r"\bsite coverage\b",
        r"\bintensification\b",
        r"\bcompact growth\b",
        r"\btall building\b",
        r"\bstorey\b",
    ],
    "residential_amenity": [
        r"\bamenit",
        r"\boverlooking\b",
        r"\bovershadow",
        r"\bprivacy\b",
        r"\bdaylight\b",
        r"\bsunlight\b",
        r"\bnoise\b",
        r"\bopen space\b",
        r"\blandscape\b",
        r"\bplay\b",
    ],
    "land_use_policy": [
        r"\bzoning\b",
        r"\bcounty development plan\b",
        r"\blocal area plan\b",
        r"\bpolicy\b",
        r"\bobjective\b",
        r"\bnational planning framework\b",
        r"\bcompact settlements guideline\b",
        r"\bdevelopment standards\b",
        r"\bstrategy\b",
    ],
    "heritage_archaeology": [
        r"\bprotected structure\b",
        r"\barchitectural conservation area\b",
        r"\barchaeolog",
        r"\bheritage\b",
        r"\bconservation\b",
    ],
    "ecology_trees": [
        r"\becolog",
        r"\bbiodivers",
        r"\bhabitat",
        r"\bnatura\b",
        r"\bappropriate assessment\b",
        r"\btree\b",
        r"\bgreen infrastructure\b",
        r"\bstrategic flood risk\b",
    ],
    "premature_or_info_gap": [
        r"\bpremature\b",
        r"\binsufficient information\b",
        r"\binadequate information\b",
        r"\bunable to make a full assessment\b",
        r"\bclarify\b",
    ],
}

CATEGORY_PATTERNS = {
    "housing_type_tags": {
        "apartment": [r"\bapartment"],
        "house": [r"\bhouse(s)?\b"],
        "duplex": [r"\bduplex"],
        "townhouse": [r"\btownhouse"],
        "bungalow": [r"\bbungalow"],
        "student": [r"\bstudent accommodation\b", r"\bpbsa\b"],
        "senior": [r"\bolder persons\b", r"\bretirement\b"],
        "shared_living": [r"\bco-living\b", r"\bshared accommodation\b"],
    },
    "density_tags": {
        "density": [r"\bdensity\b"],
        "plot_ratio": [r"\bplot ratio\b"],
        "site_coverage": [r"\bsite coverage\b"],
        "compact_growth": [r"\bcompact growth\b", r"\bcompact development\b", r"\bintensification\b"],
    },
    "height_tags": {
        "height": [r"\bheight\b", r"\bstorey\b", r"\bstoreys\b"],
        "massing": [r"\bmassing\b", r"\bscale\b", r"\btall building\b"],
    },
    "design_tags": {
        "layout": [r"\blayout\b"],
        "urban_design": [r"\burban design\b"],
        "public_realm": [r"\bpublic realm\b", r"\bstreetscape\b"],
        "amenity": [r"\bamenit", r"\bprivacy\b", r"\bdaylight\b", r"\bsunlight\b", r"\boverlooking\b"],
    },
    "access_tags": {
        "traffic": [r"\btraffic\b"],
        "access": [r"\baccess\b", r"\bjunction\b"],
        "active_travel": [r"\bcycle\b", r"\bpedestrian\b", r"\bwalkability\b", r"\bdmurs\b"],
    },
    "parking_tags": {
        "car_parking": [r"\bcar parking\b", r"\bparking\b"],
        "cycle_parking": [r"\bcycle parking\b", r"\bbicycle parking\b"],
    },
    "flood_tags": {
        "flood_risk": [r"\bflood", r"\bstrategic flood risk\b"],
        "drainage": [r"\bdrainage\b", r"\bsuds\b", r"\battenuation\b", r"\bsurface water\b"],
    },
    "ecology_tags": {
        "biodiversity": [r"\bbiodivers", r"\becolog", r"\bhabitat"],
        "appropriate_assessment": [r"\bappropriate assessment\b", r"\bnatura\b"],
        "trees": [r"\btree\b"],
    },
    "heritage_tags": {
        "heritage": [r"\bheritage\b", r"\bprotected structure\b", r"\bconservation\b"],
        "archaeology": [r"\barchaeolog"],
    },
    "open_space_tags": {
        "open_space": [r"\bopen space\b", r"\bpublic open space\b"],
        "landscape": [r"\blandscape\b", r"\bgreen infrastructure\b"],
        "play": [r"\bplay\b"],
    },
    "infrastructure_tags": {
        "water_services": [r"\birish water\b", r"\bwastewater\b", r"\bsewer\b", r"\bwater supply\b"],
        "utilities": [r"\binfrastructure\b", r"\bservices\b", r"\butilities\b"],
    },
}

CASE_TEXT_COLUMNS = [
    "DevelopmentDescription",
    "units_total_best",
    "site_area_ha_best",
    "parking_spaces_best",
    "max_storeys_best",
    "has_retail_best",
    "has_commercial_best",
    "has_mixed_use_best",
    "has_creche_best",
]


def ensure_dirs() -> None:
    CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    EXTRACTED_TEXT_DIR.mkdir(parents=True, exist_ok=True)


def normalize_whitespace(text: str) -> str:
    text = str(text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def safe_slug(value: str) -> str:
    value = str(value or "").strip().lower()
    value = value.replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


def normalize_application_number(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def build_merge_key(authority: str, appno: str) -> str:
    return f"{safe_slug(authority)}__{normalize_application_number(appno)}"


def decision_to_target(value: str) -> float:
    if pd.isna(value):
        return np.nan
    text = re.sub(r"\s+", " ", str(value).strip().upper())
    if "REFUSE" in text or text == "REFUSED":
        return 1.0
    if text == "CONDITIONAL" or "GRANT" in text or "APPROVED" in text or text == "MODIFIED":
        return 0.0
    return np.nan


def load_openai_api_key() -> str | None:
    env_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if env_key:
        return env_key
    if not OPENAI_KEY_FILE.exists():
        return None
    raw = OPENAI_KEY_FILE.read_text(encoding="utf-8", errors="ignore").strip()
    if not raw:
        return None
    if "=" in raw:
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "OPENAI_API_KEY" and value.strip():
                return value.strip().strip("\"'")
    if raw.startswith("sk-"):
        return raw.splitlines()[0].strip()
    return None


def parse_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True)


def detect_heading(block: str) -> str | None:
    first = normalize_whitespace(block).split("\n", 1)[0].strip()
    if not first:
        return None
    if len(first) > 140:
        return None
    if re.match(r"^\d+(\.\d+)*\s+[A-Z]", first):
        return first
    letters = re.sub(r"[^A-Za-z]+", "", first)
    if letters and first.upper() == first and len(letters) >= 8:
        return first.title()
    return None


def classify_constraint_strength(text: str) -> str:
    strong = [
        r"\bshall\b",
        r"\bmust\b",
        r"\bwill not be permitted\b",
        r"\bnot permitted\b",
        r"\bprohibited\b",
        r"\bcontrary to\b",
        r"\brefuse\b",
        r"\brestricted\b",
    ]
    medium = [
        r"\bshould\b",
        r"\bseek to\b",
        r"\bencourage\b",
        r"\bpromote\b",
        r"\bensure\b",
        r"\brequire\b",
    ]
    if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in strong):
        return "hard"
    if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in medium):
        return "medium"
    return "soft"


def match_tags(text: str, patterns: dict[str, list[str]]) -> list[str]:
    found = []
    for tag, regexes in patterns.items():
        if any(re.search(regex, text, flags=re.IGNORECASE) for regex in regexes):
            found.append(tag)
    return found


def match_category_tags(text: str, category_patterns: dict[str, dict[str, list[str]]]) -> dict[str, str]:
    output = {}
    for field, mapping in category_patterns.items():
        tags = []
        for tag, regexes in mapping.items():
            if any(re.search(regex, text, flags=re.IGNORECASE) for regex in regexes):
                tags.append(tag)
        output[field] = ";".join(tags)
    return output


def extract_pdf_pages(pdf_path: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    pages = []
    total_chars = 0
    nonempty_pages = 0
    try:
        reader = PdfReader(str(pdf_path), strict=False)
    except Exception as exc:
        return [], {
            "extraction_status": "failed",
            "extraction_error": str(exc),
            "page_count": 0,
            "total_chars": 0,
            "nonempty_pages": 0,
            "low_text_ratio": 1.0,
        }

    for page_index, page in enumerate(reader.pages, start=1):
        try:
            page_text = normalize_whitespace(page.extract_text() or "")
        except Exception:
            page_text = ""
        page_chars = len(page_text)
        total_chars += page_chars
        if page_chars >= 80:
            nonempty_pages += 1
        pages.append(
            {
                "page_number": page_index,
                "page_text": page_text,
                "page_chars": page_chars,
            }
        )

    page_count = len(pages)
    low_text_ratio = 1.0 if page_count == 0 else 1.0 - (nonempty_pages / page_count)
    if page_count == 0:
        status = "failed"
    elif total_chars < 2000 or nonempty_pages < max(2, int(page_count * 0.2)):
        status = "low_text"
    else:
        status = "ok"
    return pages, {
        "extraction_status": status,
        "extraction_error": "",
        "page_count": page_count,
        "total_chars": total_chars,
        "nonempty_pages": nonempty_pages,
        "low_text_ratio": round(low_text_ratio, 4),
    }


def write_extracted_text(doc_row: pd.Series, pages: list[dict[str, object]]) -> str:
    authority_dir = EXTRACTED_TEXT_DIR / safe_slug(doc_row["authority"])
    authority_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{safe_slug(doc_row['document_label'])}.txt"
    path = authority_dir / file_name
    chunks = []
    for page in pages:
        chunks.append(f"=== PAGE {page['page_number']} ===\n{page['page_text']}\n")
    path.write_text("\n".join(chunks), encoding="utf-8")
    return str(path.relative_to(POLICY_ROOT)).replace("\\", "/")


def build_policy_documents_index(manifest_df: pd.DataFrame) -> pd.DataFrame:
    cached = CURRENT_DIR / "policy_documents_index.csv"
    if cached.exists() and os.environ.get("FORCE_POLICY_REEXTRACT", "").strip().lower() not in {"1", "true", "yes"}:
        cached_df = pd.read_csv(cached)
        if "extracted_text_path" in cached_df.columns and cached_df["extracted_text_path"].fillna("").astype(str).str.len().gt(0).all():
            return cached_df
    rows: list[dict[str, object]] = []
    for _, row in manifest_df.iterrows():
        if row["status"] != "downloaded":
            continue
        pdf_path = POLICY_ROOT / row["relative_file"]
        pages, quality = extract_pdf_pages(pdf_path)
        text_path = ""
        if pages:
            text_path = write_extracted_text(row, pages)
        doc_id = f"{safe_slug(row['authority'])}__{int(row['coverage_start_year'])}_{int(row['coverage_end_year'])}__{safe_slug(row['document_label'])}"
        rows.append(
            {
                "doc_id": doc_id,
                "authority": row["authority"],
                "document_label": row["document_label"],
                "document_type": row["document_type"],
                "coverage_start_year": int(row["coverage_start_year"]),
                "coverage_end_year": int(row["coverage_end_year"]),
                "source_url": row["source_url"],
                "relative_file": row["relative_file"],
                "extracted_text_path": text_path,
                "extraction_status": quality["extraction_status"],
                "extraction_error": quality["extraction_error"],
                "page_count": quality["page_count"],
                "total_chars": quality["total_chars"],
                "nonempty_pages": quality["nonempty_pages"],
                "low_text_ratio": quality["low_text_ratio"],
                "note": row.get("note", ""),
            }
        )
    df = pd.DataFrame(rows)
    df.to_csv(CURRENT_DIR / "policy_documents_index.csv", index=False)
    return df


def load_extracted_pages_from_text(relative_path: str) -> list[dict[str, object]]:
    path = POLICY_ROOT / relative_path
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")
    parts = re.split(r"^=== PAGE (\d+) ===\s*$", text, flags=re.MULTILINE)
    pages = []
    if len(parts) < 3:
        cleaned = normalize_whitespace(text)
        if cleaned:
            pages.append({"page_number": 1, "page_text": cleaned, "page_chars": len(cleaned)})
        return pages
    for i in range(1, len(parts), 2):
        page_number = int(parts[i])
        page_text = normalize_whitespace(parts[i + 1])
        pages.append({"page_number": page_number, "page_text": page_text, "page_chars": len(page_text)})
    return pages


def chunk_document(doc_row: pd.Series, pages: list[dict[str, object]], target_chars: int = 1600) -> list[dict[str, object]]:
    chunks = []
    current_blocks: list[str] = []
    current_pages: list[int] = []
    current_section = doc_row["document_label"]
    chunk_counter = 1

    def flush() -> None:
        nonlocal chunk_counter, current_blocks, current_pages
        if not current_blocks:
            return
        chunk_text = normalize_whitespace("\n\n".join(current_blocks))
        if not chunk_text:
            current_blocks = []
            current_pages = []
            return
        page_range = f"{min(current_pages)}-{max(current_pages)}" if current_pages else ""
        plan_key = f"{safe_slug(doc_row['authority'])}__{int(doc_row['coverage_start_year'])}_{int(doc_row['coverage_end_year'])}"
        chunks.append(
            {
                "chunk_id": f"{doc_row['doc_id']}__chunk_{chunk_counter:04d}",
                "doc_id": doc_row["doc_id"],
                "plan_key": plan_key,
                "authority": doc_row["authority"],
                "plan_start_year": int(doc_row["coverage_start_year"]),
                "plan_end_year": int(doc_row["coverage_end_year"]),
                "document_label": doc_row["document_label"],
                "document_type": doc_row["document_type"],
                "section_title": current_section,
                "page_range": page_range,
                "chunk_text": chunk_text,
                "chunk_chars": len(chunk_text),
            }
        )
        chunk_counter += 1
        overlap_blocks = current_blocks[-1:] if len(current_blocks) > 1 else []
        overlap_pages = current_pages[-1:] if len(current_pages) > 1 else current_pages[-1:]
        current_blocks = overlap_blocks.copy()
        current_pages = overlap_pages.copy()

    for page in pages:
        page_text = str(page["page_text"] or "")
        if not page_text:
            continue
        raw_blocks = [normalize_whitespace(x) for x in re.split(r"\n\s*\n", page_text) if normalize_whitespace(x)]
        if not raw_blocks:
            raw_blocks = [page_text]
        for block in raw_blocks:
            heading = detect_heading(block)
            if heading:
                current_section = heading
            current_blocks.append(block)
            current_pages.append(int(page["page_number"]))
            if sum(len(x) for x in current_blocks) >= target_chars:
                flush()
    flush()
    return chunks


def build_policy_chunks(documents_df: pd.DataFrame) -> pd.DataFrame:
    cached = CURRENT_DIR / "policy_chunks.csv"
    if cached.exists() and os.environ.get("FORCE_POLICY_RECHUNK", "").strip().lower() not in {"1", "true", "yes"}:
        return pd.read_csv(cached)
    rows: list[dict[str, object]] = []
    for _, doc_row in documents_df.iterrows():
        pages = load_extracted_pages_from_text(doc_row["extracted_text_path"])
        rows.extend(chunk_document(doc_row, pages))
    df = pd.DataFrame(rows)
    df.to_csv(CURRENT_DIR / "policy_chunks.csv", index=False)
    return df


def build_policy_clause_tags(chunks_df: pd.DataFrame) -> pd.DataFrame:
    cached = CURRENT_DIR / "policy_clause_tags.csv"
    if cached.exists() and os.environ.get("FORCE_POLICY_RETAG", "").strip().lower() not in {"1", "true", "yes"}:
        return pd.read_csv(cached)
    rows = []
    for _, row in chunks_df.iterrows():
        text = str(row["chunk_text"])
        matched_themes = match_tags(text, THEME_PATTERNS)
        category_tags = match_category_tags(text, CATEGORY_PATTERNS)
        rows.append(
            {
                "chunk_id": row["chunk_id"],
                "policy_theme_tags": ";".join(matched_themes),
                "constraint_strength": classify_constraint_strength(text),
                **category_tags,
            }
        )
    df = pd.DataFrame(rows)
    df.to_csv(CURRENT_DIR / "policy_clause_tags.csv", index=False)
    return df


def build_case_text(row: pd.Series) -> str:
    lines = [str(row.get("DevelopmentDescription", "") or "")]
    for column in CASE_TEXT_COLUMNS[1:]:
        value = row.get(column)
        if pd.notna(value) and str(value) != "":
            lines.append(f"{column}: {value}")
    fi_text = row.get("fi_request_items_joined")
    if pd.notna(fi_text) and str(fi_text).strip():
        lines.append(f"FI: {str(fi_text)[:4000]}")
    return normalize_whitespace("\n".join(lines))


def aggregate_plan_theme_features(chunks_df: pd.DataFrame, clause_tags_df: pd.DataFrame) -> pd.DataFrame:
    merged = chunks_df.merge(clause_tags_df, on="chunk_id", how="left")
    rows = []
    for plan_key, group in merged.groupby("plan_key", dropna=False):
        row = {
            "plan_key": plan_key,
            "policy_plan_chunk_count": int(len(group)),
            "policy_plan_total_chars": float(group["chunk_chars"].fillna(0).sum()),
            "policy_plan_hard_constraint_share": float((group["constraint_strength"] == "hard").mean()),
        }
        theme_counter: Counter[str] = Counter()
        for tags in group["policy_theme_tags"].fillna(""):
            for tag in [t for t in str(tags).split(";") if t]:
                theme_counter[tag] += 1
        denom = max(1, len(group))
        for theme in sorted(THEME_PATTERNS):
            row[f"policy_plan_theme_count__{theme}"] = float(theme_counter.get(theme, 0))
            row[f"policy_plan_theme_share__{theme}"] = float(theme_counter.get(theme, 0) / denom)
        rows.append(row)
    return pd.DataFrame(rows)


def load_dublin_cases() -> pd.DataFrame:
    df = pd.read_csv(FI_DATA, low_memory=False)
    df = df[df["PlanningAuthority"].isin(DUBLIN_AUTHORITIES)].copy()
    df["merge_key"] = [build_merge_key(a, b) for a, b in zip(df["PlanningAuthority"], df["ApplicationNumber"])]
    if "case_key" not in df.columns:
        df["case_key"] = df["merge_key"]
    else:
        df["case_key"] = df["case_key"].fillna("").astype(str).str.strip()
        invalid_mask = df["case_key"].str.lower().isin({"", "nan", "none", "null"})
        df.loc[invalid_mask, "case_key"] = df.loc[invalid_mask, "merge_key"]
    df["decision_date_dt"] = parse_date(df["DecisionDate"])
    df["received_date_dt"] = parse_date(df["ReceivedDate"])
    df["effective_decision_date"] = df["decision_date_dt"].fillna(df["received_date_dt"])
    df["target_refused"] = df["Decision"].map(decision_to_target)
    df["case_text"] = df.apply(build_case_text, axis=1)
    return df


def load_flood_features() -> pd.DataFrame:
    df = pd.read_csv(FLOOD_DATA, low_memory=False)
    df = df[df["PlanningAuthority"].isin(DUBLIN_AUTHORITIES)].copy()
    df["merge_key"] = [build_merge_key(a, b) for a, b in zip(df["PlanningAuthority"], df["ApplicationNumber"])]
    keep = ["merge_key", "coastal_depth_max_m", "fluvial_depth_max_m", "coastal_hit_any", "fluvial_hit_any", "coastal_min_logdist", "fluvial_min_logdist"]
    present = [c for c in keep if c in df.columns]
    return df[present].drop_duplicates(subset=["merge_key"])


def load_refusal_case_tags() -> pd.DataFrame:
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    df = pd.read_csv(REFUSAL_CASES, low_memory=False)
    df = df[df["council"].isin(DUBLIN_AUTHORITIES)].copy()
    return df.rename(
        columns={
            "council": "PlanningAuthority",
            "application_number": "ApplicationNumber",
            "decision_date": "DecisionDate_refusal_case",
        }
    )[["case_key", "reason_count", "case_primary_tags", "case_top_primary_tag"]]


def assign_policy_plan(cases_df: pd.DataFrame, manifest_df: pd.DataFrame) -> pd.DataFrame:
    downloaded = manifest_df[manifest_df["status"] == "downloaded"].copy()
    gaps = manifest_df[manifest_df["status"] == "missing_public_source"].copy()
    downloaded["plan_key"] = [
        f"{safe_slug(a)}__{int(s)}_{int(e)}"
        for a, s, e in zip(downloaded["authority"], downloaded["coverage_start_year"], downloaded["coverage_end_year"])
    ]
    plan_ranges = (
        downloaded.groupby(["authority", "coverage_start_year", "coverage_end_year", "plan_key"], as_index=False)
        .size()
        .sort_values(["authority", "coverage_start_year", "coverage_end_year"])
    )
    gap_ranges = gaps[["authority", "coverage_start_year", "coverage_end_year", "note"]].copy()

    plan_key = []
    coverage_flag = []
    plan_start = []
    plan_end = []
    gap_note = []
    for _, row in cases_df.iterrows():
        authority = row["PlanningAuthority"]
        year = np.nan if pd.isna(row["effective_decision_date"]) else row["effective_decision_date"].year
        candidates = plan_ranges[
            (plan_ranges["authority"] == authority)
            & (plan_ranges["coverage_start_year"] <= year)
            & (plan_ranges["coverage_end_year"] >= year)
        ].sort_values(["coverage_start_year", "coverage_end_year"], ascending=[False, False])
        if not candidates.empty:
            chosen = candidates.iloc[0]
            plan_key.append(chosen["plan_key"])
            coverage_flag.append("ok")
            plan_start.append(int(chosen["coverage_start_year"]))
            plan_end.append(int(chosen["coverage_end_year"]))
            gap_note.append("")
            continue
        gaps_match = gap_ranges[
            (gap_ranges["authority"] == authority)
            & (gap_ranges["coverage_start_year"] <= year)
            & (gap_ranges["coverage_end_year"] >= year)
        ]
        if not gaps_match.empty:
            gap = gaps_match.iloc[0]
            plan_key.append("")
            coverage_flag.append("manifest_gap")
            plan_start.append(int(gap["coverage_start_year"]))
            plan_end.append(int(gap["coverage_end_year"]))
            gap_note.append(str(gap.get("note", "")))
        else:
            plan_key.append("")
            coverage_flag.append("no_plan_found")
            plan_start.append(np.nan)
            plan_end.append(np.nan)
            gap_note.append("")

    enriched = cases_df.copy()
    enriched["policy_plan_key"] = plan_key
    enriched["policy_coverage_flag"] = coverage_flag
    enriched["policy_plan_start_year"] = plan_start
    enriched["policy_plan_end_year"] = plan_end
    enriched["policy_gap_note"] = gap_note
    return enriched


def add_case_pressure_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["case_units_density_per_ha"] = out["units_total_best"] / out["site_area_ha_best"].replace({0: np.nan})
    out["case_parking_per_unit"] = out["parking_spaces_best"] / out["units_total_best"].replace({0: np.nan})
    out["case_open_space_per_unit"] = out["open_space_sqm_best"] / out["units_total_best"].replace({0: np.nan})
    out["case_is_tall_scheme"] = (out["max_storeys_best"].fillna(0) >= 6).astype(float)
    out["case_is_medium_height_scheme"] = (out["max_storeys_best"].fillna(0) >= 4).astype(float)
    out["case_is_large_scheme"] = (out["units_total_best"].fillna(0) >= 100).astype(float)
    out["case_low_parking_ratio"] = (out["case_parking_per_unit"].fillna(99) < 0.75).astype(float)
    out["case_high_density_pressure"] = (out["case_units_density_per_ha"].fillna(0) >= 40).astype(float)
    out["case_flood_pressure"] = ((out.get("coastal_hit_any", 0).fillna(0) > 0) | (out.get("fluvial_hit_any", 0).fillna(0) > 0)).astype(float)
    out["case_policy_gap_flag"] = (out["policy_coverage_flag"] != "ok").astype(float)
    return out


def maybe_compute_openai_embeddings(texts: list[str], output_path: Path, enabled: bool) -> np.ndarray | None:
    if not enabled or OpenAI is None:
        return None
    api_key = load_openai_api_key()
    if not api_key:
        return None
    if output_path.exists():
        return np.load(output_path)
    client = OpenAI(api_key=api_key)
    embeddings = []
    batch_size = 64
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = client.embeddings.create(model="text-embedding-3-small", input=batch)
        embeddings.extend(item.embedding for item in response.data)
    arr = np.asarray(embeddings, dtype=np.float32)
    np.save(output_path, arr)
    return arr


def build_policy_matches_and_features(
    cases_df: pd.DataFrame,
    chunks_df: pd.DataFrame,
    clause_tags_df: pd.DataFrame,
    use_openai_embeddings: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    chunk_meta = chunks_df.merge(clause_tags_df, on="chunk_id", how="left")
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=30000, min_df=1)
    chunk_matrix = vectorizer.fit_transform(chunk_meta["chunk_text"].fillna(""))
    joblib.dump(vectorizer, MODEL_DIR / "policy_tfidf_vectorizer.joblib")

    openai_chunk = maybe_compute_openai_embeddings(
        chunk_meta["chunk_text"].fillna("").tolist(),
        MODEL_DIR / "policy_chunk_embeddings.npy",
        enabled=use_openai_embeddings,
    )
    openai_case = maybe_compute_openai_embeddings(
        cases_df["case_text"].fillna("").tolist(),
        MODEL_DIR / "case_text_embeddings.npy",
        enabled=use_openai_embeddings,
    )

    theme_names = sorted(THEME_PATTERNS)
    match_rows = []
    feature_rows = []
    indexed_chunks = {k: g.index.to_numpy() for k, g in chunk_meta.groupby("plan_key")}
    case_matrix = vectorizer.transform(cases_df["case_text"].fillna(""))

    for idx, row in cases_df.iterrows():
        plan_key = row["policy_plan_key"]
        if not plan_key or plan_key not in indexed_chunks:
            blank = {
                "case_key": row["case_key"],
                "policy_similarity_top1": 0.0,
                "policy_similarity_top3_mean": 0.0,
                "policy_similarity_top5_mean": 0.0,
                "policy_match_count": 0.0,
                "policy_similarity_method": "none",
            }
            for theme in theme_names:
                blank[f"policy_match_theme_count__{theme}"] = 0.0
                blank[f"policy_match_theme_share__{theme}"] = 0.0
            feature_rows.append(blank)
            continue

        chunk_idx = indexed_chunks[plan_key]
        tfidf_scores = linear_kernel(case_matrix[idx], chunk_matrix[chunk_idx]).ravel()
        score_method = "tfidf"
        scores = tfidf_scores
        if openai_chunk is not None and openai_case is not None:
            case_vec = openai_case[idx]
            chunk_vecs = openai_chunk[chunk_idx]
            denom = (np.linalg.norm(case_vec) * np.linalg.norm(chunk_vecs, axis=1)) + 1e-9
            embed_scores = (chunk_vecs @ case_vec) / denom
            scores = (0.65 * tfidf_scores) + (0.35 * embed_scores)
            score_method = "tfidf+openai"

        top_k = min(5, len(scores))
        top_positions = np.argsort(-scores)[:top_k]
        selected_scores = scores[top_positions]
        selected_chunk_idx = chunk_idx[top_positions]
        selected = chunk_meta.iloc[selected_chunk_idx]

        theme_counter: Counter[str] = Counter()
        for rank, (_, chunk_row) in enumerate(selected.iterrows(), start=1):
            tags = [t for t in str(chunk_row.get("policy_theme_tags", "")).split(";") if t]
            for tag in tags:
                theme_counter[tag] += 1
            match_rows.append(
                {
                    "case_key": row["case_key"],
                    "PlanningAuthority": row["PlanningAuthority"],
                    "policy_plan_key": plan_key,
                    "rank": rank,
                    "chunk_id": chunk_row["chunk_id"],
                    "document_label": chunk_row["document_label"],
                    "section_title": chunk_row["section_title"],
                    "page_range": chunk_row["page_range"],
                    "similarity_score": float(selected_scores[rank - 1]),
                    "similarity_method": score_method,
                    "policy_theme_tags": chunk_row.get("policy_theme_tags", ""),
                    "constraint_strength": chunk_row.get("constraint_strength", ""),
                    "chunk_text_preview": str(chunk_row["chunk_text"])[:600],
                }
            )

        feature_row = {
            "case_key": row["case_key"],
            "policy_similarity_top1": float(selected_scores[0]) if top_k >= 1 else 0.0,
            "policy_similarity_top3_mean": float(np.mean(selected_scores[: min(3, top_k)])) if top_k else 0.0,
            "policy_similarity_top5_mean": float(np.mean(selected_scores)) if top_k else 0.0,
            "policy_match_count": float(top_k),
            "policy_similarity_method": score_method,
        }
        for theme in theme_names:
            count = float(theme_counter.get(theme, 0))
            feature_row[f"policy_match_theme_count__{theme}"] = count
            feature_row[f"policy_match_theme_share__{theme}"] = count / max(1.0, float(top_k))
        feature_rows.append(feature_row)

    matches_df = pd.DataFrame(match_rows)
    features_df = pd.DataFrame(feature_rows)
    matches_df.to_csv(CURRENT_DIR / "dublin_case_policy_matches.csv", index=False)
    features_df.to_csv(CURRENT_DIR / "dublin_case_policy_features.csv", index=False)
    return matches_df, features_df


def summarize_top_matches(matches_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for case_key, group in matches_df.groupby("case_key"):
        group = group.sort_values("rank")
        top_chunks = []
        top_themes = Counter()
        for _, row in group.head(3).iterrows():
            label = f"{row['document_label']} [{row['page_range']}]"
            top_chunks.append(label)
            for tag in [t for t in str(row["policy_theme_tags"]).split(";") if t]:
                top_themes[tag] += 1
        rows.append(
            {
                "case_key": case_key,
                "top_matched_policy_chunks": " || ".join(top_chunks),
                "top_matched_policy_themes": ";".join(tag for tag, _ in top_themes.most_common(5)),
            }
        )
    return pd.DataFrame(rows)


def build_model_dataset(
    manifest_df: pd.DataFrame,
    chunks_df: pd.DataFrame,
    clause_tags_df: pd.DataFrame,
    use_openai_embeddings: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cases_df = load_dublin_cases()
    cases_df = cases_df.merge(load_flood_features(), on="merge_key", how="left")
    cases_df = cases_df.merge(load_refusal_case_tags(), on="case_key", how="left", suffixes=("", "_refusal"))
    cases_df = assign_policy_plan(cases_df, manifest_df)
    plan_features = aggregate_plan_theme_features(chunks_df, clause_tags_df)
    cases_df = cases_df.merge(plan_features, left_on="policy_plan_key", right_on="plan_key", how="left")
    matches_df, match_features_df = build_policy_matches_and_features(cases_df, chunks_df, clause_tags_df, use_openai_embeddings)
    cases_df = cases_df.merge(match_features_df, on="case_key", how="left")
    cases_df = add_case_pressure_features(cases_df)
    summary_df = summarize_top_matches(matches_df)
    cases_df = cases_df.merge(summary_df, on="case_key", how="left")

    numeric_fill_cols = [
        c
        for c in cases_df.columns
        if (
            c.startswith("policy_plan_")
            or c.startswith("policy_match_")
            or c.startswith("policy_similarity_")
            or c in {
                "case_units_density_per_ha",
                "case_parking_per_unit",
                "case_open_space_per_unit",
                "case_is_tall_scheme",
                "case_is_medium_height_scheme",
                "case_is_large_scheme",
                "case_low_parking_ratio",
                "case_high_density_pressure",
                "case_flood_pressure",
                "case_policy_gap_flag",
            }
        )
    ]
    for col in numeric_fill_cols:
        if col not in {"policy_similarity_method", "policy_coverage_flag", "policy_gap_note", "policy_plan_key"}:
            cases_df[col] = pd.to_numeric(cases_df[col], errors="coerce")
    cases_df.to_csv(CURRENT_DIR / "dublin_refusal_model_dataset.csv", index=False)
    return cases_df, matches_df


def build_feature_lists(df: pd.DataFrame) -> tuple[list[str], list[str], list[str], list[str]]:
    base_numeric = [
        "units_total_best",
        "units_houses_best",
        "units_apartments_best",
        "units_duplex_best",
        "units_townhouses_best",
        "units_bungalows_best",
        "bed_1_best",
        "bed_2_best",
        "bed_3_best",
        "bed_4_best",
        "bed_5_best",
        "parking_spaces_best",
        "cycle_parking_spaces_best",
        "site_area_ha_best",
        "floor_area_sqm_best",
        "open_space_sqm_best",
        "max_storeys_best",
        "retail_area_sqm_best",
        "commercial_area_sqm_best",
        "creche_area_sqm_best",
        "fi_events_count",
        "fi_received_events_count",
        "fi_request_items_count",
        "coastal_depth_max_m",
        "fluvial_depth_max_m",
        "coastal_hit_any",
        "fluvial_hit_any",
        "coastal_min_logdist",
        "fluvial_min_logdist",
        "case_units_density_per_ha",
        "case_parking_per_unit",
        "case_open_space_per_unit",
        "case_is_tall_scheme",
        "case_is_medium_height_scheme",
        "case_is_large_scheme",
        "case_low_parking_ratio",
        "case_high_density_pressure",
        "case_flood_pressure",
        "case_policy_gap_flag",
    ]
    base_binary = [
        "has_retail_best",
        "has_commercial_best",
        "has_mixed_use_best",
        "has_creche_best",
        "has_community_best",
        "has_hotel_best",
        "has_industrial_best",
        "fi_request_has_items",
    ]
    categorical = ["PlanningAuthority", "policy_coverage_flag", "policy_similarity_method"]
    policy_numeric = [c for c in df.columns if c.startswith("policy_plan_") or c.startswith("policy_match_") or c.startswith("policy_similarity_")]
    base_numeric = [c for c in base_numeric if c in df.columns and pd.api.types.is_numeric_dtype(df[c]) and df[c].notna().any()]
    base_binary = [c for c in base_binary if c in df.columns]
    categorical = [c for c in categorical if c in df.columns]
    policy_numeric = [
        c
        for c in policy_numeric
        if c in df.columns and c not in {"policy_similarity_method", "policy_plan_key"} and pd.api.types.is_numeric_dtype(df[c])
    ]
    return base_numeric, base_binary, categorical, policy_numeric


def split_time_based(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    eligible = df[df["target_refused"].notna() & df["effective_decision_date"].notna()].copy()
    eligible = eligible.sort_values("effective_decision_date")
    split_idx = max(1, int(len(eligible) * 0.8))
    train_df = eligible.iloc[:split_idx].copy()
    test_df = eligible.iloc[split_idx:].copy()
    if test_df["target_refused"].nunique() < 2:
        split_idx = max(1, int(len(eligible) * 0.75))
        train_df = eligible.iloc[:split_idx].copy()
        test_df = eligible.iloc[split_idx:].copy()
    return train_df, test_df


def build_model_pipeline(numeric_cols: list[str], categorical_cols: list[str]) -> Pipeline:
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "num",
                Pipeline(steps=[("imputer", SimpleImputer(strategy="median"))]),
                numeric_cols,
            ),
            (
                "cat",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                categorical_cols,
            ),
        ],
        sparse_threshold=1.0,
    )
    model = LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5, solver="liblinear")
    return Pipeline(steps=[("preprocessor", preprocessor), ("model", model)])


def compute_metrics(y_true: np.ndarray, probabilities: np.ndarray) -> dict[str, float]:
    return {
        "roc_auc": float(roc_auc_score(y_true, probabilities)),
        "pr_auc": float(average_precision_score(y_true, probabilities)),
        "brier": float(brier_score_loss(y_true, probabilities)),
    }


def per_authority_metrics(df: pd.DataFrame, probability_col: str) -> dict[str, dict[str, float]]:
    results = {}
    for authority, group in df.groupby("PlanningAuthority"):
        if group["target_refused"].nunique() < 2:
            continue
        results[authority] = compute_metrics(group["target_refused"].to_numpy(), group[probability_col].to_numpy())
    return results


def transformed_feature_names(pipeline: Pipeline) -> list[str]:
    return list(pipeline.named_steps["preprocessor"].get_feature_names_out())


def build_case_driver_strings(
    policy_model: Pipeline,
    scoring_df: pd.DataFrame,
    feature_columns: list[str],
    policy_feature_columns: set[str],
) -> list[str]:
    transformed = policy_model.named_steps["preprocessor"].transform(scoring_df[feature_columns])
    coefs = policy_model.named_steps["model"].coef_[0]
    if hasattr(transformed, "multiply"):
        contributions = transformed.multiply(coefs).toarray()
    else:
        contributions = transformed * coefs
    feature_names = transformed_feature_names(policy_model)
    outputs = []
    for row_idx in range(contributions.shape[0]):
        contrib = contributions[row_idx]
        ranked = np.argsort(-np.abs(contrib))
        picked = []
        for feat_idx in ranked:
            name = feature_names[feat_idx]
            base_name = name.split("__", 1)[-1]
            if base_name in policy_feature_columns or base_name.startswith("policy_"):
                continue
            value = scoring_df.iloc[row_idx].get(base_name, "")
            picked.append(f"{base_name}={value} ({contrib[feat_idx]:.3f})")
            if len(picked) == 3:
                break
        outputs.append(" | ".join(picked))
    return outputs


def prediction_band(probability: float) -> str:
    if probability < 0.35:
        return "low"
    if probability < 0.65:
        return "medium"
    return "high"


def grounded_policy_explanation(row: pd.Series) -> str:
    if row.get("policy_coverage_flag") != "ok":
        return f"Reduced policy coverage: {row.get('policy_coverage_flag')}."
    themes = str(row.get("top_matched_policy_themes", "") or "").replace(";", ", ")
    chunks = str(row.get("top_matched_policy_chunks", "") or "")
    if not themes and not chunks:
        return "No strong policy chunk matches were retrieved."
    parts = []
    if themes:
        parts.append(f"Likely policy pressure points: {themes}.")
    if chunks:
        parts.append(f"Matched chunks: {chunks}.")
    return " ".join(parts)


def train_and_score(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    train_df, test_df = split_time_based(df)
    base_numeric, base_binary, categorical, policy_numeric = build_feature_lists(df)
    baseline_features = base_numeric + base_binary + categorical
    policy_features = baseline_features + policy_numeric

    baseline_model = build_model_pipeline(base_numeric + base_binary, categorical)
    policy_model = build_model_pipeline(base_numeric + base_binary + policy_numeric, categorical)

    baseline_model.fit(train_df[baseline_features], train_df["target_refused"])
    policy_model.fit(train_df[policy_features], train_df["target_refused"])

    joblib.dump(baseline_model, MODEL_DIR / "dublin_refusal_baseline_logistic.joblib")
    joblib.dump(policy_model, MODEL_DIR / "dublin_refusal_policy_logistic.joblib")

    scored = df.copy()
    eligible_mask = scored["target_refused"].notna() & scored["effective_decision_date"].notna()
    eligible = scored.loc[eligible_mask].copy()
    eligible["split"] = np.where(eligible.index.isin(test_df.index), "holdout", "train")
    eligible["baseline_refusal_probability"] = baseline_model.predict_proba(eligible[baseline_features])[:, 1]
    eligible["policy_refusal_probability"] = policy_model.predict_proba(eligible[policy_features])[:, 1]
    eligible["prediction_band"] = eligible["policy_refusal_probability"].map(prediction_band)
    eligible["grounded_policy_explanation"] = eligible.apply(grounded_policy_explanation, axis=1)
    eligible["top_non_policy_drivers"] = build_case_driver_strings(
        policy_model=policy_model,
        scoring_df=eligible,
        feature_columns=policy_features,
        policy_feature_columns=set(policy_numeric),
    )

    metrics = {
        "train_rows": int(len(train_df)),
        "holdout_rows": int(len(test_df)),
        "train_start_date": str(train_df["effective_decision_date"].min()),
        "train_end_date": str(train_df["effective_decision_date"].max()),
        "holdout_start_date": str(test_df["effective_decision_date"].min()),
        "holdout_end_date": str(test_df["effective_decision_date"].max()),
        "baseline_holdout": compute_metrics(
            test_df["target_refused"].to_numpy(),
            baseline_model.predict_proba(test_df[baseline_features])[:, 1],
        ),
        "policy_holdout": compute_metrics(
            test_df["target_refused"].to_numpy(),
            policy_model.predict_proba(test_df[policy_features])[:, 1],
        ),
        "policy_holdout_by_authority": per_authority_metrics(
            eligible[eligible["split"] == "holdout"],
            "policy_refusal_probability",
        ),
    }
    return eligible, metrics


def save_outputs(scored_df: pd.DataFrame, metrics: dict[str, object]) -> None:
    keep_cols = [
        "case_key",
        "PlanningAuthority",
        "ApplicationNumber",
        "Decision",
        "effective_decision_date",
        "target_refused",
        "split",
        "baseline_refusal_probability",
        "policy_refusal_probability",
        "prediction_band",
        "policy_plan_key",
        "policy_plan_start_year",
        "policy_plan_end_year",
        "policy_coverage_flag",
        "policy_gap_note",
        "top_matched_policy_themes",
        "top_matched_policy_chunks",
        "grounded_policy_explanation",
        "top_non_policy_drivers",
        "reason_count",
        "case_primary_tags",
        "case_top_primary_tag",
    ]
    keep_cols = [c for c in keep_cols if c in scored_df.columns]
    scored_df[keep_cols].to_csv(CURRENT_DIR / "dublin_refusal_predictions.csv", index=False)
    (CURRENT_DIR / "dublin_refusal_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")


def main() -> None:
    ensure_dirs()
    manifest_df = pd.read_csv(POLICY_MANIFEST)
    documents_df = build_policy_documents_index(manifest_df)
    chunks_df = build_policy_chunks(documents_df)
    clause_tags_df = build_policy_clause_tags(chunks_df)
    use_openai_embeddings = os.environ.get("USE_OPENAI_EMBEDDINGS", "").strip().lower() in {"1", "true", "yes"}
    dataset_df, _ = build_model_dataset(
        manifest_df=manifest_df,
        chunks_df=chunks_df,
        clause_tags_df=clause_tags_df,
        use_openai_embeddings=use_openai_embeddings,
    )
    scored_df, metrics = train_and_score(dataset_df)
    save_outputs(scored_df, metrics)


if __name__ == "__main__":
    main()
