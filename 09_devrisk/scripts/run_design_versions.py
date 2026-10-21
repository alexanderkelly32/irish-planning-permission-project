"""Phase 3: versioned design-version dataset + lineage-linked mutation pairs.

Deterministic parsing of structured design fields from descriptions
(units, storeys, mix, creche, open space, demolition, Part V, bedrooms,
parking, phasing, access), linked into site lineages via 150m KD-tree
clusters, relationship classification (same_proposal_revised vs
replacement vs additional_phase), and a deltas table. Audit pack saved.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "optimiser"
OUT.mkdir(parents=True, exist_ok=True)


def parse_design(desc: str, units) -> dict:
    d = (desc or "").lower()
    m = re.search(r"(\d+)[ -]storey", d)
    return {
        "storeys": int(m.group(1)) if m else None,
        "apartment": int("apartment" in d or "duplex" in d),
        "house": int("house" in d or "dwelling" in d or "terrace" in d or "semi" in d),
        "creche": int("creche" in d),
        "open_space": int("open space" in d or "amenity" in d or "play area" in d),
        "demolition": int("demolition" in d),
        "part_v": int("part v" in d or "social housing" in d or "affordable" in d),
        "parking_mention": int("parking" in d or "car park" in d),
        "phasing": int("phase" in d),
        "access_mention": int("access" in d or "junction" in d),
        "bedrooms": int(sum(int(x) for x in re.findall(r"(\d+)[ -]?bed", d)[:6])),
        "desc_len": len(d),
        "units": units,
    }


def main() -> None:
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "PlanningAuthority", "DevelopmentDescription",
                                   "NumResidentialUnits", "AreaofSite", "ITMEasting", "ITMNorthing",
                                   "ReceivedDate", "DecisionDate", "FIRequestDate",
                                   "AppealSubmittedDate", "Decision"])
    reg = reg.drop_duplicates("case_key")
    reg = reg.dropna(subset=["ITMEasting", "ITMNorthing"])
    reg["recv"] = pd.to_datetime(reg["ReceivedDate"], utc=True, errors="coerce").dt.tz_localize(None)
    reg["dec_dt"] = pd.to_datetime(reg["DecisionDate"], utc=True, errors="coerce").dt.tz_localize(None)
    reg["units"] = pd.to_numeric(reg["NumResidentialUnits"], errors="coerce")
    reg = reg[(reg["units"] >= 5)]
    dec = reg["Decision"].fillna("").str.lower()
    reg = reg[dec.str.contains("refus|grant|conditional|unconditional", regex=True)]
    reg["refused"] = dec.str.contains("refus").astype(int)
    reg["granted"] = dec.str.contains("grant|conditional|unconditional", regex=True).astype(int)
    reg["fi"] = pd.notna(reg["FIRequestDate"]).astype(int)
    reg["appeal"] = pd.notna(reg["AppealSubmittedDate"]).astype(int)
    reg = reg.dropna(subset=["recv"]).sort_values("recv")

    rows = []
    for authority, g in reg.groupby("PlanningAuthority"):
        if len(g) < 2:
            continue
        coords = g[["ITMEasting", "ITMNorthing"]].to_numpy()
        tree = cKDTree(coords)
        parent = list(range(len(g)))
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
        for a, b in tree.query_pairs(r=150.0, output_type="ndarray"):
            union(int(a), int(b))
        g = g.copy().reset_index(drop=True)
        g["site_id"] = authority + "|" + pd.Series([find(i) for i in range(len(g))]).astype(str)
        rows.append(g)
    frame = pd.concat(rows, ignore_index=True)
    for i, r in frame.iterrows():
        d = parse_design(str(r["DevelopmentDescription"]), r["units"])
        for k, v in d.items():
            frame.loc[i, k] = v
    frame["year"] = frame["recv"].dt.year
    frame = frame[frame["site_id"].map(frame.groupby("site_id").size()) >= 2]
    frame.to_csv(OUT / "design_versions.csv", index=False)
    print("versions:", len(frame), "sites:", frame["site_id"].nunique(), flush=True)

    pairs = []
    for site_id, g in frame.sort_values("recv").groupby("site_id"):
        for i in range(len(g) - 1):
            a = g.iloc[i]
            b = g.iloc[i + 1]
            tok_a = set(re.findall(r"[a-z0-9]{3,}", str(a["DevelopmentDescription"]).lower()))
            tok_b = set(re.findall(r"[a-z0-9]{3,}", str(b["DevelopmentDescription"]).lower()))
            jac = len(tok_a & tok_b) / max(len(tok_a | tok_b), 1)
            if jac >= 0.4:
                rel = "same_proposal_revised"
            elif b["units"] and a["units"] and b["units"] >= a["units"] * 1.5:
                rel = "additional_phase"
            else:
                rel = "replacement"
            delta = {f"d_{c}": ((b[c] if b[c] is not None and not pd.isna(b[c]) else 0) -
                               (a[c] if a[c] is not None and not pd.isna(a[c]) else 0)) for c in
                     ["storeys", "apartment", "house", "creche", "open_space", "demolition",
                      "part_v", "parking_mention", "phasing", "access_mention", "bedrooms", "units"]}
            pairs.append({"site_id": site_id, "case_key_a": a["case_key"], "case_key_b": b["case_key"],
                          "recv_a": a["recv"], "recv_b": b["recv"], "year_a": a["year"],
                          "relationship": rel, "jaccard": round(jac, 3),
                          "outcome_b": "grant" if b["granted"] else "refuse",
                          "fi_b": b["fi"], "appeal_b": b["appeal"],
                          **delta})
    pr = pd.DataFrame(pairs)
    pr.to_csv(OUT / "mutation_pairs_design.csv", index=False)
    print("pairs:", len(pr), "| rel:", pr["relationship"].value_counts().to_dict(), flush=True)

    audit = pr.sample(min(30, len(pr)), random_state=7).merge(
        frame[["case_key", "DevelopmentDescription"]].rename(columns={"case_key": "case_key_a",
                                                                      "DevelopmentDescription": "desc_a"}),
        on="case_key_a", how="left").merge(
        frame[["case_key", "DevelopmentDescription"]].rename(columns={"case_key": "case_key_b",
                                                                      "DevelopmentDescription": "desc_b"}),
        on="case_key_b", how="left")
    audit.to_csv(OUT / "audit_pack_pairs.csv", index=False)
    print("audit pack rows:", len(audit), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
