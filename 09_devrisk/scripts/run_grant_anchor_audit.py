"""Runner: A. Grant-anchoring audit.

Distinguishes local-authority decision vs final grant vs ACP appeal
decision. Quantifies schemes whose commencement anchor is the conditional
decision rather than final permission, and re-anchors labels.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

if __name__ == "__main__":
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    reg = register[["case_key", "PlanningAuthority", "DecisionDate", "GrantDate", "AppealDecisionDate",
                    "AppealStatus", "AppealSubmittedDate"]].drop_duplicates("case_key")
    frame = labels[["case_key", "activation_days", "activation_linked"]].merge(reg, on="case_key", how="left")
    for column in ("DecisionDate", "GrantDate", "AppealDecisionDate", "AppealSubmittedDate"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")

    # Anchoring diagnostics
    n = int(len(frame))
    grant_null = int(frame["GrantDate"].isna().sum())
    appeal_after_decision = int(((frame["AppealDecisionDate"].notna()) & (frame["DecisionDate"].notna()) &
                                 (frame["AppealDecisionDate"] > frame["DecisionDate"])).sum())
    appeal_after_grant = int(((frame["AppealDecisionDate"].notna()) & (frame["GrantDate"].notna()) &
                              (frame["AppealDecisionDate"] > frame["GrantDate"])).sum())
    # Cases where the commencement anchor (grant or decision fallback) predates
    # the appeal decision - the anchor is NOT the final permission.
    anchor = frame["GrantDate"].where(frame["GrantDate"].notna(), frame["DecisionDate"])
    anchor_predates_appeal = int(((frame["AppealDecisionDate"].notna()) & (anchor < frame["AppealDecisionDate"])).sum())
    # These cases' true final permission = appeal decision; label re-anchor.
    reanchor = frame[(frame["AppealDecisionDate"].notna()) & (anchor < frame["AppealDecisionDate"])].copy()
    reanchor["final_permission"] = frame.loc[reanchor.index, "AppealDecisionDate"]
    reanchor["anchor_shift_days"] = (reanchor["final_permission"] - anchor[reanchor.index]).dt.days

    report = {
        "schemes": n,
        "grant_date_null": grant_null,
        "appeal_after_decision": appeal_after_decision,
        "appeal_after_grant": appeal_after_grant,
        "anchor_predates_appeal_decision": anchor_predates_appeal,
        "anchor_shift_days_summary": {
            "n": int(len(reanchor)),
            "median_days": round(float(reanchor["anchor_shift_days"].median()), 0) if len(reanchor) else None,
            "max_days": round(float(reanchor["anchor_shift_days"].max()), 0) if len(reanchor) else None,
        },
    }
    reanchor[["case_key", "anchor_shift_days"]].to_csv(settings.SILVER_DIR / "grant_anchor_audit.csv", index=False)
    out = settings.SILVER_DIR / "grant_anchor_audit.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
