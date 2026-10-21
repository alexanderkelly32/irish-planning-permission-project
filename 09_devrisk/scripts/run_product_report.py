"""Machine-produced development report prototype (product output).

Generates a markdown report per scheme: current status, what happens next,
timing (median + calibrated intervals), evidence, change log, confidence,
unknowns. Honest about when the engine cannot distinguish.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

OUT = settings.SILVER_DIR / "state_machine" / "reports"
OUT.mkdir(parents=True, exist_ok=True)
SNAP = pd.Timestamp("2026-10-01")

STATE_LABELS = {
    "submitted": "application submitted", "fi_requested": "further information requested",
    "fi_received": "further information received", "decision_issued": "decision issued",
    "appeal_active": "appeal active", "final_grant": "permission granted",
    "dormant_granted": "granted, no commencement yet", "notice_filed": "commencement notice filed",
    "commenced": "works commenced on site", "first_ccc": "first units certified",
    "partial_ccc": "units being certified in phases", "final_ccc": "final units certified",
    "first_sale": "first sale recorded", "active_sales": "selling/building out",
    "complete": "substantially complete",
}

UNKNOWNS = (
    "Funding secured / financing in place - not observable in public data (falsified: macro "
    "rates carry no cross-scheme signal; CRO charges are paid-access).",
    "Landowner vs applicant relationship - consent docs rarely name the landowner (4% coverage).",
    "Contractor appointed / procurement state - builder identity absent from BCMS open data.",
    "Internal developer go/no-go decision - the single largest source of dormancy; private.",
    "Utility connection agreements (ESB/Uisce) - pending FOI; treated as optional sensors.",
)


def build_report(key: str, states: pd.DataFrame, transitions: dict, reg_row, cur_row) -> str:
    s = states[states["case_key"] == key].sort_values("entered")
    lines = []
    lines.append(f"# Development report - {key}")
    lines.append(f"Generated {SNAP.date()} from observed public records only.")
    lines.append("")
    cur = cur_row.iloc[0]
    lines.append("## Current status")
    lines.append(f"- State: **{STATE_LABELS.get(cur['current_state'], cur['current_state'])}** "
                 f"({cur['observed_or_inferred']}, confidence {cur['confidence']})")
    lines.append(f"- Entered this state: {pd.to_datetime(cur['state_entered_date']).date()} "
                 f"({cur['days_in_state']} days ago)")
    lines.append(f"- Last observed event: {STATE_LABELS.get(cur['last_observed_event'], cur['last_observed_event'])} "
                 f"on {pd.to_datetime(cur['last_observed_event_date']).date()}")
    lines.append("")
    lines.append("## What happens next")
    nxt = cur["next_possible_states"].split("|")
    shown = 0
    for state in nxt:
        t = transitions.get(f"{cur['current_state']}->{state}")
        if not t:
            continue
        shown += 1
        lines.append(f"- **{STATE_LABELS.get(state, state)}**: n={t['n']}, median {t['median_days']}d "
                     f"(IQR {t['q25']}-{t['q75']}d); within 3m {t.get('within_3m')}%, "
                     f"6m {t.get('within_6m')}%, 12m {t.get('within_12m')}%")
    if not shown:
        lines.append("- No transition data held for this state pair - honest unknown.")
    lines.append("")
    lines.append("## Timing (calibrated, not precise)")
    lines.append("Intervals below are empirical; the engine does not claim day-level precision.")
    for state in nxt:
        t = transitions.get(f"{cur['current_state']}->{state}")
        if t and t.get("n"):
            lines.append(f"- {STATE_LABELS.get(state, state)}: median {t['median_days']}d; "
                         f"80% of cases between {t.get('pct80_lower')}d and {t.get('pct80_upper')}d")
    lines.append("")
    lines.append("## Evidence")
    for _, r in s.iterrows():
        lines.append(f"- {STATE_LABELS.get(r['state'], r['state'])} on "
                     f"{pd.to_datetime(r['entered']).date()} - source {r['source']} "
                     f"({r['observed_or_inferred']}, {r['confidence']})")
    lines.append("")
    lines.append("## Change log")
    prev = None
    for _, r in s.iterrows():
        if prev is not None:
            d = (r["entered"] - prev["entered"]).days
            lines.append(f"- {prev['state']} -> {r['state']}: {d}d")
        prev = r
    lines.append("")
    lines.append("## Confidence")
    obs = (s["observed_or_inferred"] == "observed").sum()
    lines.append(f"- {obs} of {len(s)} states observed directly; the rest inferred from absence.")
    lines.append("- High confidence in observed dates (register/BCMS/PPR); medium for inferred states.")
    lines.append("")
    lines.append("## Unknowns (private or unobservable)")
    for u in UNKNOWNS:
        lines.append(f"- {u}")
    lines.append("")
    lines.append("---")
    lines.append("Objective evidence only. Where the engine cannot distinguish developments, "
                "it says so explicitly.")
    return "\n".join(lines)


def main() -> None:
    states = pd.read_csv(settings.SILVER_DIR / "state_machine" / "states.csv")
    states["entered"] = pd.to_datetime(states["entered"], errors="coerce")
    cur = pd.read_csv(settings.SILVER_DIR / "state_machine" / "current_state.csv")
    transitions = json.loads((settings.SILVER_DIR / "state_machine" / "transitions.json").read_text(encoding="utf-8"))
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    register = register[["case_key", "PlanningAuthority", "NumResidentialUnits",
                         "DevelopmentDescription"]].drop_duplicates("case_key")
    for key in ["Wicklow County Council__2237", "Wicklow County Council__22258"]:
        reg_row = register[register["case_key"] == key]
        cur_row = cur[cur["case_key"] == key]
        if cur_row.empty:
            continue
        report = build_report(key, states, transitions, reg_row, cur_row)
        (OUT / f"report_{key.replace(' ', '_').replace('/', '_')[:70]}.md").write_text(
            report, encoding="utf-8")
        print(f"wrote report for {key}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
