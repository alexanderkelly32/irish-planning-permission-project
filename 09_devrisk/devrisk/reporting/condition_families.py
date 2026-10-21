"""Grant-condition family taxonomy and rule-based classifier.

Product brief 6.7: P(condition_family | ultimate_grant). Families follow the
brief's list. The v1 classifier is deterministic regex over granted planner
reports; an LLM extraction contract (condition_families_v1) upgrades it once
a pilot authority corpus is rebuilt. Never presented as imposed conditions.
"""
from __future__ import annotations

import re
from typing import Any

FAMILIES = [
    "roads_access_transport",
    "drainage_wastewater_water",
    "construction_environmental_management",
    "archaeology_ecology_conservation",
    "flood_mitigation",
    "landscaping_open_space_public_realm",
    "design_material_changes",
    "part_v_bonds_contributions",
    "phasing_occupancy_tenure",
    "precommencement_submissions",
    "preoccupation_certification_infrastructure",
]

RULES: list[tuple[str, re.Pattern[str]]] = [
    ("roads_access_transport", re.compile(r"road|access|junction|traffic|sightline|turning|carpark|car park|footpath|pedestrian", re.I)),
    ("drainage_wastewater_water", re.compile(r"drain|sewer|wastewater|waste water|water main|watermain|suDS|foul|surface water|percolation|treatment system", re.I)),
    ("construction_environmental_management", re.compile(r"construction (management|environmental)|c&d|noise|dust|hours of (work|construction)|wheel wash", re.I)),
    ("archaeology_ecology_conservation", re.compile(r"archaeolog|monitoring of (the )?arch|ecolog|bat|bird|hedgerow|tree survey|protected species|natura", re.I)),
    ("flood_mitigation", re.compile(r"flood|attenuation|opw|benching", re.I)),
    ("landscaping_open_space_public_realm", re.compile(r"landscap|open space|amenity|planting|boundary treatment|public realm", re.I)),
    ("design_material_changes", re.compile(r"material|finish|render|roof tile|elevation|storey height|fenestration|colour", re.I)),
    ("part_v_bonds_contributions", re.compile(r"part v|contribution|bond|levy|development contribution|special contribution", re.I)),
    ("phasing_occupancy_tenure", re.compile(r"phase|occupancy|occupation|phased", re.I)),
    ("precommencement_submissions", re.compile(r"prior to (the )?commencement|before (the )?commencement|pre-commencement|before works|prior to works|shall be submitted.*commence", re.I)),
    ("preoccupation_certification_infrastructure", re.compile(r"prior to (the )?occup|before (the )?occup|shall be completed|commissioned|taking in charge|snag|road safety audit", re.I)),
]


def classify_condition_text(text: str) -> dict[str, bool]:
    """Family presence flags for one condition/document text chunk."""
    return {family: bool(pattern.search(text)) for family, pattern in RULES}


def classify_document(text: str) -> dict[str, Any]:
    """One document: family presence + sentence-level evidence snippets."""
    sentences = [s.strip() for s in re.split(r"(?<=[.;])\s+", text) if len(s.strip()) > 40]
    families = {family: [] for family, _ in RULES}
    for sentence in sentences:
        for family, pattern in RULES:
            if pattern.search(sentence) and len(families[family]) < 3:
                families[family].append(sentence[:240])
    return {
        "families": {family: bool(snippets) for family, snippets in families.items()},
        "evidence_snippets": {family: snippets for family, snippets in families.items() if snippets},
        "sentence_count": len(sentences),
    }


def families_to_record(case_key: str, result: dict[str, Any], *, granted: bool) -> dict[str, Any]:
    record: dict[str, Any] = {
        "case_key": case_key,
        "granted": granted,
        "extraction_method": "regex_condition_families_v1",
    }
    for family, _ in RULES:
        record[f"condition_{family}"] = int(bool(result["families"].get(family)))
    record["condition_family_count"] = int(sum(result["families"].values()))
    record["evidence_snippet"] = "; ".join(snippets[0] for snippets in result["evidence_snippets"].values() if snippets)[:500]
    return record
