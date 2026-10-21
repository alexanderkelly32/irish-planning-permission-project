"""Turn manual revision-pair audit decisions into explicit evidence-only exports."""
from __future__ import annotations

from io import StringIO
from pathlib import Path

import pandas as pd


ALLOWED_AUDIT_STATUSES = {"accepted", "rejected", "pending"}
PAIR_KEYS = ["original_case_key", "revised_case_key"]


def read_revision_audit_csv(path: Path) -> pd.DataFrame:
    """Read the human-maintained audit sheet after common spreadsheet encodings."""
    raw = path.read_bytes()
    decoded = raw.decode("utf-8-sig", errors="surrogateescape")
    repaired: list[str] = []
    for char in decoded:
        codepoint = ord(char)
        if 0xDC80 <= codepoint <= 0xDCFF:
            byte = bytes([codepoint - 0xDC00])
            try:
                repaired.append(byte.decode("cp1252"))
            except UnicodeDecodeError:
                repaired.append("\ufffd")
        else:
            repaired.append(char)
    return pd.read_csv(StringIO("".join(repaired)))


def build_accepted_revision_exports(
    pairs: pd.DataFrame,
    audit: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return accepted evidence rows and their durable, pair-scoped case-group map."""
    for name, frame in [("pairs", pairs), ("audit", audit)]:
        missing = set(PAIR_KEYS) - set(frame.columns)
        if missing:
            raise ValueError(f"{name} is missing keys: {sorted(missing)}")
    reviewed = audit.copy()
    reviewed["audit_status"] = reviewed.get("audit_status", "pending").fillna("pending").astype(str).str.strip().str.lower()
    unknown = sorted(set(reviewed["audit_status"]) - ALLOWED_AUDIT_STATUSES)
    if unknown:
        raise ValueError(f"unknown audit statuses: {unknown}")
    reviewed["audit_notes"] = reviewed.get("audit_notes", "").fillna("").astype(str).str.strip()
    if (reviewed["audit_status"].eq("accepted") & reviewed["audit_notes"].eq("")).any():
        raise ValueError("accepted revision pairs require an audit note")
    if reviewed.duplicated(PAIR_KEYS).any():
        raise ValueError("audit contains duplicate revision-pair keys")

    accepted_audit = reviewed.loc[reviewed["audit_status"].eq("accepted"), PAIR_KEYS + ["audit_status", "audit_notes"]]
    accepted = pairs.merge(accepted_audit, on=PAIR_KEYS, how="inner", validate="one_to_one")
    accepted["project_group_id"] = (
        "revision_pair:"
        + accepted["original_case_key"].astype(str)
        + "__"
        + accepted["revised_case_key"].astype(str)
    )
    members: list[dict[str, str]] = []
    for _, row in accepted.iterrows():
        for key, role in [("original_case_key", "original_refused"), ("revised_case_key", "revised_granted")]:
            members.append({"case_key": str(row[key]), "project_group_id": str(row["project_group_id"]), "pair_role": role})
    group_map = pd.DataFrame(members, columns=["case_key", "project_group_id", "pair_role"])
    if group_map["case_key"].duplicated().any():
        raise ValueError("a case appears in multiple accepted revision pairs; resolve before grouping")
    return accepted, group_map
