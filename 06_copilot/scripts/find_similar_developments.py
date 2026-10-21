from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel
from sklearn.preprocessing import OneHotEncoder


DEFAULT_CSV = (
    "04_fi/current/"
    "greater_than_10_units_with_refusal_reasons_plus_ge10_fi_requests_enriched.csv"
)

TEXT_COLS = ["DevelopmentDescription", "DevelopmentAddress"]
CAT_COLS = ["PlanningAuthority", "ApplicationType", "case_top_primary_tag"]
NUM_COLS = [
    "units_total_best",
    "units_houses_best",
    "units_apartments_best",
    "units_duplex_best",
    "units_townhouses_best",
    "units_bungalows_best",
    "site_area_ha_best",
    "max_storeys_best",
    "ITMEasting",
    "ITMNorthing",
]


@dataclass
class SearchArtifacts:
    vectorizer: TfidfVectorizer
    cat_encoder: OneHotEncoder | None
    numeric_columns: list[str]
    numeric_fill: pd.Series
    numeric_mean: np.ndarray
    numeric_std: np.ndarray
    feature_columns: list[str]


def _combined_text(df: pd.DataFrame) -> pd.Series:
    parts = []
    for col in TEXT_COLS:
        if col in df.columns:
            parts.append(df[col].fillna("").astype(str))
    if not parts:
        return pd.Series([""] * len(df), index=df.index)
    txt = parts[0]
    for p in parts[1:]:
        txt = txt + " " + p
    return txt.str.strip()


def _numeric_frame(df: pd.DataFrame, numeric_columns: list[str]) -> pd.DataFrame:
    numeric = pd.DataFrame(index=df.index)
    for col in numeric_columns:
        numeric[col] = pd.to_numeric(df.get(col), errors="coerce")
    return numeric


def _cat_frame(df: pd.DataFrame, cat_columns: list[str]) -> pd.DataFrame:
    cat = pd.DataFrame(index=df.index)
    for col in cat_columns:
        cat[col] = df.get(col, "MISSING")
        cat[col] = cat[col].fillna("MISSING").astype(str).str.strip()
    return cat


def fit_search_artifacts(df: pd.DataFrame) -> SearchArtifacts:
    feature_columns = list(dict.fromkeys(TEXT_COLS + CAT_COLS + NUM_COLS + list(df.columns)))
    text = _combined_text(df)
    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        min_df=2,
        max_features=80_000,
        ngram_range=(1, 2),
    )
    vectorizer.fit(text)

    numeric_columns = [col for col in NUM_COLS if col in df.columns]
    numeric = _numeric_frame(df, numeric_columns)
    if numeric_columns:
        numeric_fill = numeric.median(numeric_only=True).fillna(0.0)
        vals = numeric.fillna(numeric_fill).fillna(0.0).to_numpy(dtype=np.float32)
        numeric_mean = vals.mean(axis=0, keepdims=True)
        numeric_std = vals.std(axis=0, keepdims=True)
        numeric_std[numeric_std == 0] = 1.0
    else:
        numeric_fill = pd.Series(dtype=np.float32)
        numeric_mean = np.zeros((1, 0), dtype=np.float32)
        numeric_std = np.ones((1, 0), dtype=np.float32)

    cat_columns = [col for col in CAT_COLS if col in df.columns]
    cat_encoder: OneHotEncoder | None = None
    if cat_columns:
        cat_encoder = OneHotEncoder(handle_unknown="ignore")
        cat_encoder.fit(_cat_frame(df, cat_columns))

    return SearchArtifacts(
        vectorizer=vectorizer,
        cat_encoder=cat_encoder,
        numeric_columns=numeric_columns,
        numeric_fill=numeric_fill,
        numeric_mean=numeric_mean,
        numeric_std=numeric_std,
        feature_columns=feature_columns,
    )


def transform_rows(df: pd.DataFrame, artifacts: SearchArtifacts) -> sparse.csr_matrix:
    text = _combined_text(df)
    x_text = artifacts.vectorizer.transform(text)

    if artifacts.numeric_columns:
        numeric = _numeric_frame(df, artifacts.numeric_columns)
        vals = (
            numeric.fillna(artifacts.numeric_fill)
            .fillna(0.0)
            .to_numpy(dtype=np.float32)
        )
        vals = (vals - artifacts.numeric_mean) / artifacts.numeric_std
        x_num = sparse.csr_matrix(vals)
    else:
        x_num = sparse.csr_matrix((len(df), 0), dtype=np.float32)

    if artifacts.cat_encoder is not None:
        cat_columns = [col for col in CAT_COLS if col in df.columns or col in artifacts.feature_columns]
        x_cat = artifacts.cat_encoder.transform(_cat_frame(df, cat_columns))
    else:
        x_cat = sparse.csr_matrix((len(df), 0), dtype=np.float32)

    x = sparse.hstack([x_text * 0.78, x_num * 0.12, x_cat * 0.10], format="csr")
    norms = np.sqrt(x.multiply(x).sum(axis=1)).A1
    norms[norms == 0] = 1.0
    return x.multiply((1.0 / norms)[:, None]).tocsr()


def build_feature_matrix(df: pd.DataFrame) -> sparse.csr_matrix:
    artifacts = fit_search_artifacts(df)
    return transform_rows(df, artifacts)


def build_query_frame(df: pd.DataFrame, **overrides: object) -> pd.DataFrame:
    row = {col: pd.NA for col in df.columns}
    for key, value in overrides.items():
        if key in row:
            row[key] = value
    return pd.DataFrame([row], columns=df.columns)


def resolve_query_index(
    df: pd.DataFrame,
    case_key: str | None,
    application_number: str | None,
    planning_authority: str | None,
) -> int:
    if case_key:
        matches = df.index[df["case_key"].astype(str).str.lower() == case_key.lower()].tolist()
        if not matches:
            raise ValueError(f"No row found for case_key='{case_key}'.")
        return int(matches[0])

    if not application_number:
        raise ValueError("Provide --case-key or --application-number.")

    ap = df["ApplicationNumber"].fillna("").astype(str).str.strip().str.lower()
    mask = ap == application_number.strip().lower()
    if planning_authority:
        pa = df["PlanningAuthority"].fillna("").astype(str).str.strip().str.lower()
        mask = mask & (pa == planning_authority.strip().lower())
    matches = df.index[mask].tolist()
    if not matches:
        raise ValueError(
            "No row found for the provided application number"
            + (" and planning authority." if planning_authority else ".")
        )
    if len(matches) > 1 and not planning_authority:
        sample = df.loc[matches[:5], ["PlanningAuthority", "case_key"]].to_string(index=False)
        raise ValueError(
            "Application number matched multiple rows. Add --planning-authority.\n"
            f"Examples:\n{sample}"
        )
    return int(matches[0])


def find_similar(
    df: pd.DataFrame,
    x: sparse.csr_matrix,
    query_idx: int,
    top_k: int,
) -> pd.DataFrame:
    sim = linear_kernel(x[query_idx], x).ravel()
    sim[query_idx] = -1.0
    k = min(top_k, max(0, len(df) - 1))
    top_idx = np.argpartition(-sim, kth=np.arange(k))[:k]
    top_idx = top_idx[np.argsort(-sim[top_idx])]
    out = df.loc[top_idx].copy()
    out.insert(0, "similarity", sim[top_idx])
    return out


def find_similar_to_query(
    df: pd.DataFrame,
    x_cases: sparse.csr_matrix,
    x_query: sparse.csr_matrix,
    top_k: int,
) -> pd.DataFrame:
    sim = linear_kernel(x_query, x_cases).ravel()
    k = min(top_k, len(df))
    top_idx = np.argpartition(-sim, kth=np.arange(k))[:k]
    top_idx = top_idx[np.argsort(-sim[top_idx])]
    out = df.loc[top_idx].copy()
    out.insert(0, "similarity", sim[top_idx])
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Find most similar developments for a selected case."
    )
    p.add_argument("--csv", default=DEFAULT_CSV, help="Input CSV path.")
    p.add_argument("--case-key", help="Query case key (preferred).")
    p.add_argument("--application-number", help="Query application number.")
    p.add_argument("--planning-authority", help="Optional for disambiguation.")
    p.add_argument("--top-k", type=int, default=20, help="Number of matches.")
    p.add_argument("--query-text", help="Free-text development query.")
    p.add_argument("--query-address", help="Optional address for free-text query.")
    p.add_argument("--query-units", type=float, help="Optional unit count for free-text query.")
    p.add_argument("--query-application-type", help="Optional application type for free-text query.")
    p.add_argument(
        "--output-csv",
        help="Optional output path to save full top-k rows with similarity scores.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise FileNotFoundError(f"Input CSV not found: {csv_path.resolve()}")

    df = pd.read_csv(csv_path, low_memory=False)
    required = {"case_key", "ApplicationNumber"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {sorted(missing)}")

    artifacts = fit_search_artifacts(df)
    x = transform_rows(df, artifacts)
    if args.query_text:
        query_df = build_query_frame(
            df,
            DevelopmentDescription=args.query_text,
            DevelopmentAddress=args.query_address,
            units_total_best=args.query_units,
            NumResidentialUnits=args.query_units,
            PlanningAuthority=args.planning_authority,
            ApplicationType=args.query_application_type,
        )
        out = find_similar_to_query(df, x, transform_rows(query_df, artifacts), max(1, args.top_k))
        print("Query case:")
        print(
            f"- PlanningAuthority: {args.planning_authority or ''}\n"
            f"- ApplicationType: {args.query_application_type or ''}\n"
            f"- Units: {args.query_units or ''}\n"
            f"- DevelopmentDescription: {args.query_text}"
        )
    else:
        query_idx = resolve_query_index(
            df,
            case_key=args.case_key,
            application_number=args.application_number,
            planning_authority=args.planning_authority,
        )
        out = find_similar(df, x, query_idx, max(1, args.top_k))

        query = df.loc[query_idx]
        print("Query case:")
        print(
            f"- case_key: {query.get('case_key', '')}\n"
            f"- PlanningAuthority: {query.get('PlanningAuthority', '')}\n"
            f"- ApplicationNumber: {query.get('ApplicationNumber', '')}\n"
            f"- Decision: {query.get('Decision', '')}"
        )
    print("\nTop similar developments:")
    display_cols = [
        c
        for c in [
            "similarity",
            "case_key",
            "PlanningAuthority",
            "ApplicationNumber",
            "Decision",
            "units_total_best",
            "DevelopmentDescription",
        ]
        if c in out.columns
    ]
    shown = out[display_cols].copy()
    shown["similarity"] = shown["similarity"].map(lambda v: f"{v:.4f}")
    print(shown.to_string(index=False, max_colwidth=95))

    if args.output_csv:
        out.to_csv(args.output_csv, index=False)
        print(f"\nSaved full results to: {Path(args.output_csv).resolve()}")


if __name__ == "__main__":
    main()
