"""PPR sales-milestone labels (brief sections 5.5, 13.4).

Only for schemes whose tenure/exit type is eligible (ordinary build-to-sell).
Milestones: first linked arm's-length sale; dates on which linked sales reach
25/50/90% of the expected individually saleable denominator. Every label
carries eligibility and a coverage denominator; transaction_count/granted_units
is never presented as true sell-through.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

INELIGIBLE_TENURES = {"build_to_rent", "social", "mixed_unknown", "retained"}


def eligible_for_sales(tenure_or_exit_type: str) -> bool:
    return str(tenure_or_exit_type or "unknown").strip().lower() not in INELIGIBLE_TENURES


def build_sales_milestones(
    scheme_id: str,
    transactions: pd.DataFrame,
    *,
    expected_sellable_units: int | None,
    tenure_or_exit_type: str = "build_to_sell",
) -> dict[str, Any]:
    """transactions: sale_date (parsed), price, eligible (arm's-length) columns."""
    if not eligible_for_sales(tenure_or_exit_type):
        return {
            "scheme_id": scheme_id,
            "eligible": False,
            "reason": f"tenure/exit type not individually sold: {tenure_or_exit_type}",
        }
    if expected_sellable_units is None or expected_sellable_units <= 0:
        return {"scheme_id": scheme_id, "eligible": False, "reason": "no defensible sellable-unit denominator"}

    sales = transactions.copy()
    if "eligible" in sales.columns:
        sales = sales[sales["eligible"].fillna(True)]
    sales["sale_date"] = pd.to_datetime(sales["sale_date"], utc=True, errors="coerce")
    sales = sales.dropna(subset=["sale_date"]).sort_values("sale_date")

    denominator = int(expected_sellable_units)
    milestones: dict[str, Any] = {"first_sale_date": None, "pct25_date": None, "pct50_date": None, "pct90_date": None}
    cum = 0
    for _, row in sales.iterrows():
        cum += 1
        if cum == 1:
            milestones["first_sale_date"] = row["sale_date"].date().isoformat()
        if cum >= max(1, round(denominator * 0.25)) and milestones["pct25_date"] is None:
            milestones["pct25_date"] = row["sale_date"].date().isoformat()
        if cum >= max(1, round(denominator * 0.5)) and milestones["pct50_date"] is None:
            milestones["pct50_date"] = row["sale_date"].date().isoformat()
        if cum >= max(1, round(denominator * 0.9)) and milestones["pct90_date"] is None:
            milestones["pct90_date"] = row["sale_date"].date().isoformat()
            break

    return {
        "scheme_id": scheme_id,
        "eligible": True,
        "denominator_units": denominator,
        "linked_transactions": int(len(sales)),
        "coverage_ratio": round(len(sales) / denominator, 4),
        "coverage_warning": len(sales) < denominator,
        "milestones": milestones,
        "label_rule_version": "ppr_milestones_v1",
    }
