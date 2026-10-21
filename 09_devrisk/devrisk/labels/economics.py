"""Economic timing and price labels (brief sections 5.5, 5.6).

Per scheme with confirmed PPR links:
  - first/last sale dates; time-to-first-sale from final grant and from
    commencement; sales count; coverage vs expected units;
  - slow-exit flags (no first sale within 24/36 months, matured only);
  - price benchmark: scheme median price vs contemporaneous same-county
    comparable transactions (same window), percentile position.

Eligibility: build-to-rent / social (AHB) / retained schemes are excluded
from sell-through labels. Sales counts are never presented as true
sell-through where tenure or phase boundaries are unknown.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np
import pandas as pd

from .activation import _parse_date, days_between

BTR_HINTS = r"build to rent|build-to-rent|private rental|prs\b|rental scheme|forward fund|forward-fund"


def eligible_for_sales(description: Any, approved_housing_body: Any = "") -> bool:
    text = str(description or "").lower()
    ahb = str(approved_housing_body or "").strip().lower() in {"yes", "y", "true"}
    if ahb:
        return False
    import re

    return not bool(re.search(BTR_HINTS, text, flags=re.IGNORECASE))


def build_exit_labels(
    schemes: pd.DataFrame,
    ppr_links: pd.DataFrame,
    ppr: pd.DataFrame,
    *,
    censor_date: str,
) -> pd.DataFrame:
    """schemes: case_key, final_grant_date, expected_units, description,
    approved_housing_body, commencement_date (first confirmed)."""
    censor = pd.to_datetime(censor_date, utc=True).date()
    rows = []
    for _, scheme in schemes.iterrows():
        scheme_id = str(scheme["case_key"])
        description = scheme.get("DevelopmentDescription") or scheme.get("description") or ""
        ahb = scheme.get("approved_housing_body", "")
        eligible = eligible_for_sales(description, ahb)
        grant = _parse_date(scheme.get("final_grant_date"))
        commencement = _parse_date(scheme.get("commencement_date"))

        linked = ppr_links[ppr_links["scheme_id"] == scheme_id]
        confirmed = linked[linked["confidence_band"] == "confirmed"] if len(linked) else pd.DataFrame()
        sales = pd.DataFrame()
        if not confirmed.empty:
            sales = ppr[ppr["source_row_id"].isin(confirmed["ppr_source_row_id"])].copy()
            if "not_full_market_price_flag" in sales.columns:
                sales = sales[~sales["not_full_market_price_flag"]]
            sales["sale_date"] = pd.to_datetime(sales["sale_date_dt"], utc=True, errors="coerce")
            sales = sales.dropna(subset=["sale_date"]).sort_values("sale_date")
            # Label hygiene: a scheme's first sale cannot predate its grant
            # (older same-named phases pollute the estate match). 90-day
            # grace for off-plan sales.
            if grant is not None:
                cutoff = pd.Timestamp(grant - dt.timedelta(days=90), tz="UTC")
                sales = sales[sales["sale_date"] >= cutoff]
            # Also cannot predate commencement by more than a year (same
            # contamination mode on the commencement axis).
            if commencement is not None:
                comm_cutoff = pd.Timestamp(commencement - dt.timedelta(days=365), tz="UTC")
                sales = sales[sales["sale_date"] >= comm_cutoff]

        first_sale = _parse_date(sales["sale_date"].iloc[0]) if not sales.empty else None
        last_sale = _parse_date(sales["sale_date"].iloc[-1]) if not sales.empty else None
        time_to_first_sale_from_grant = days_between(grant, first_sale)
        time_to_first_sale_from_commencement = days_between(commencement, first_sale)

        expected_units = pd.to_numeric(pd.Series([scheme.get("expected_units")]), errors="coerce").iloc[0]
        sales_count = int(len(sales))
        coverage = None if pd.isna(expected_units) or expected_units <= 0 else round(sales_count / float(expected_units), 4)

        slow_exit_24m = None
        slow_exit_36m = None
        # Slow exit is only defined where sales linkage exists; schemes without
        # confirmed PPR links are UNKNOWN (linkage failure is not evidence of
        # slow sales - brief section 5.5).
        if eligible and first_sale is not None and commencement is not None:
            tfs = days_between(commencement, first_sale)
            if tfs is not None:
                slow_exit_24m = int(tfs >= 730)
                slow_exit_36m = int(tfs >= 1096)

        median_price = float(sales["price_num"].median()) if not sales.empty and sales["price_num"].notna().any() else None
        rows.append({
            "scheme_id": scheme_id,
            "sales_eligible": bool(eligible),
            "eligibility_reason": "AHB/social" if ahb else ("BTR/rental hints" if not eligible else ""),
            "sales_linked": sales_count,
            "sales_coverage": coverage,
            "first_sale_date": first_sale.isoformat() if first_sale else None,
            "last_sale_date": last_sale.isoformat() if last_sale else None,
            "time_to_first_sale_from_grant_days": time_to_first_sale_from_grant,
            "time_to_first_sale_from_commencement_days": time_to_first_sale_from_commencement,
            "slow_exit_24m": slow_exit_24m,
            "slow_exit_36m": slow_exit_36m,
            "median_price": median_price,
            "label_rule_version": "exit_v1",
        })
    return pd.DataFrame(rows)


def benchmark_prices(
    exit_labels: pd.DataFrame,
    ppr: pd.DataFrame,
    *,
    window_months: int = 12,
    min_benchmark_sales: int = 20,
) -> pd.DataFrame:
    """Scheme median price vs contemporaneous same-county transactions.

    Returns per scheme: benchmark median, scheme percentile position, and a
    below-market flag when the scheme median sits below the benchmark 25th
    percentile (margin-pressure indicator, not a cost-overrun claim).
    """
    frame = ppr.copy()
    frame["sale_date"] = pd.to_datetime(frame["sale_date_dt"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["sale_date", "price_num"])
    frame = frame[~frame["not_full_market_price_flag"]]
    rows = []
    for _, scheme in exit_labels.iterrows():
        first_sale = _parse_date(scheme.get("first_sale_date"))
        if first_sale is None or scheme.get("median_price") is None:
            rows.append({"scheme_id": scheme["scheme_id"], "benchmark_median": None, "scheme_percentile": None, "below_market_25pct": None, "benchmark_n": 0})
            continue
        start = first_sale - dt.timedelta(days=window_months * 30)
        end = first_sale + dt.timedelta(days=window_months * 30)
        county = _county_for_scheme(scheme["scheme_id"], frame)
        window = frame[(frame["sale_date"] >= pd.Timestamp(start, tz="UTC")) & (frame["sale_date"] <= pd.Timestamp(end, tz="UTC"))]
        if county:
            window = window[window["county_norm"] == county]
        if len(window) < min_benchmark_sales:
            rows.append({"scheme_id": scheme["scheme_id"], "benchmark_median": None, "scheme_percentile": None, "below_market_25pct": None, "benchmark_n": int(len(window))})
            continue
        benchmark = float(window["price_num"].median())
        percentile = float((window["price_num"] <= scheme["median_price"]).mean())
        q25 = float(window["price_num"].quantile(0.25))
        rows.append({
            "scheme_id": scheme["scheme_id"],
            "benchmark_median": benchmark,
            "scheme_percentile": round(percentile, 4),
            "below_market_25pct": int(scheme["median_price"] < q25),
            "benchmark_n": int(len(window)),
        })
    return pd.DataFrame(rows)


_COUNTY_CACHE: dict[str, str] = {}


def _county_for_scheme(scheme_id: str, ppr: pd.DataFrame) -> str:
    if scheme_id in _COUNTY_CACHE:
        return _COUNTY_CACHE[scheme_id]
    return ""
