#!/usr/bin/env python3
"""
Extract structured development details from planning descriptions.

Defaults:
- input:  ground_source_data.csv
- output: downloads/ground_source_extracted_wide.csv

Produces a wide CSV with extracted fields and an optional filter on total units.
"""
from __future__ import annotations

import argparse
import re
from typing import Dict, Iterable, List, Tuple

import pandas as pd


NUM_WORDS = {
    "zero": 0,
    "one": 1,
    "single": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}

STOREY_WORDS = {
    "single": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
}

UNIT_TYPES = {
    "houses": ["house", "houses", "dwelling house", "dwelling houses", "mews house", "mews houses"],
    "dwellings": [
        "dwelling",
        "dwellings",
        "residential unit",
        "residential units",
        "unit",
        "units",
    ],
    "apartments": ["apartment", "apartments", "flat", "flats"],
    "duplex": ["duplex", "duplexes", "duplex units"],
    "townhouses": ["townhouse", "town house", "townhouses", "town houses"],
    "bungalows": ["bungalow", "bungalows"],
}

NON_RES_USES = {
    "retail": ["retail", "shop", "shops"],
    "commercial": ["commercial", "office", "offices"],
    "mixed_use": ["mixed use", "mixed-use"],
    "creche": ["creche", "childcare", "child care"],
    "community": ["community", "community centre", "community center"],
    "hotel": ["hotel"],
    "industrial": ["industrial", "warehouse", "warehouses"],
}


def normalize_text(text: str) -> str:
    text = (text or "").replace(" ", " ")
    text = re.sub(r"\bno\s*'?\s*s\b", "nos", text, flags=re.IGNORECASE)
    text = re.sub(r"\bno\.?\s+of\b", "no of", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def word_to_num(word: str) -> int | None:
    return NUM_WORDS.get(word.lower())


NUM_WORD_PATTERN = "|".join(sorted(NUM_WORDS.keys(), key=len, reverse=True))


def extract_numbers_from_text(text: str) -> List[int]:
    return [int(x) for x in re.findall(r"\b\d{1,5}\b", text)]


def _is_measurement_context(text: str, match: re.Match) -> bool:
    snippet = text[match.start() : match.end() + 12]
    return re.search(r"\b\d{1,5}\s*(?:mm|cm|m2|sqm|sq\.?m|ha|hectare|hectares)\b", snippet, flags=re.IGNORECASE) is not None


def _is_storey_context(text: str, match: re.Match) -> bool:
    matched = match.group(0).lower()
    # If the matched phrase already states unit types, it is likely a unit count, not a storey count.
    if re.search(
        r"\b(dwelling|dwellings|unit|units|house|houses|apartment|apartments|flat|flats|duplex|duplexes|town ?house|town ?houses|bungalow|bungalows|mews)\b",
        matched,
        flags=re.IGNORECASE,
    ):
        return False
    snippet = text[max(0, match.start() - 10) : match.end() + 20]
    return (
        re.search(
            r"\b(?:\d{1,2}|single|one|two|three|four|five)\s*[- ]?storey\b",
            snippet,
            flags=re.IGNORECASE,
        )
        is not None
    )


def _is_plan_ref_context(text: str, match: re.Match) -> bool:
    snippet = text[max(0, match.start() - 20) : match.end() + 20]
    return re.search(r"\b(?:pl|ref|reg|planning)\b", snippet, flags=re.IGNORECASE) is not None


def _is_unit_fraction_context(text: str, match: re.Match) -> bool:
    snippet = text[max(0, match.start() - 5) : match.end() + 5]
    return re.search(r"\bunit(?:s)?\s*\d{1,5}\s*/\s*\d{1,5}\b", snippet, flags=re.IGNORECASE) is not None


def _is_non_res_unit_context(text: str, match: re.Match) -> bool:
    snippet = text[max(0, match.start() - 40) : match.end() + 40].lower()
    if "unit" in match.group(0).lower():
        if re.search(r"\b(retail|commercial|office|shop|cafe|restaurant|warehouse|industrial)\b", snippet) and not re.search(
            r"\b(residential|dwelling|apartment|house|housing)\b",
            snippet,
        ):
            return True
    return False


def _iter_unit_counts(text: str) -> Iterable[Tuple[str, int]]:
    seen: set[Tuple[str, int, int, int]] = set()

    def emit(unit_key: str, m: re.Match, value: int) -> Iterable[Tuple[str, int]]:
        sig = (unit_key, m.start(), m.end(), int(value))
        if sig in seen:
            return
        seen.add(sig)
        yield unit_key, int(value)

    for unit_key, variants in UNIT_TYPES.items():
        for v in variants:
            pattern = rf"\b(\d{{1,5}})\s*(?:\(\s*\d{{1,5}}\s*no(?:s|'s)?\.?\s*\)\s*)?(?:no(?:s|'s)?\.?\s*|no\s+of\s*|number\s+of\s*|number\s+)?(?:new\s*)?{re.escape(v)}\b"
            for m in re.finditer(pattern, text, flags=re.IGNORECASE):
                if _is_storey_context(text, m):
                    continue
                if _is_plan_ref_context(text, m):
                    continue
                if m.group(1).startswith("0") and len(m.group(1)) > 1:
                    continue
                yield from emit(unit_key, m, int(m.group(1)))
            # Variant with leading number words, e.g. "five dwellings" or "twenty (20 no) apartments".
            pattern_word = rf"\b({NUM_WORD_PATTERN})\b\s*(?:\(\s*\d{{1,5}}\s*no(?:s|'s)?\.?\s*\)\s*)?(?:no(?:s|'s)?\.?\s*|no\s+of\s*|number\s+of\s*|number\s+)?(?:new\s*)?{re.escape(v)}\b"
            for m in re.finditer(pattern_word, text, flags=re.IGNORECASE):
                if _is_storey_context(text, m):
                    continue
                if _is_plan_ref_context(text, m):
                    continue
                n = word_to_num(m.group(1))
                if n is not None:
                    yield from emit(unit_key, m, int(n))
            # Variant: "no. 5 houses"
            pattern_no = rf"\bno(?:s|'s)?\.?\s*(\d{{1,5}})\s*(?:new\s*)?{re.escape(v)}\b"
            for m in re.finditer(pattern_no, text, flags=re.IGNORECASE):
                if _is_storey_context(text, m):
                    continue
                if _is_plan_ref_context(text, m):
                    continue
                if m.group(1).startswith("0") and len(m.group(1)) > 1:
                    continue
                yield from emit(unit_key, m, int(m.group(1)))
            # Variant: "5 nos. houses" / "5 no's houses"
            pattern_nos = rf"\b(\d{{1,5}})\s*no(?:s|'s)?\.?\s*(?:new\s*)?{re.escape(v)}\b"
            for m in re.finditer(pattern_nos, text, flags=re.IGNORECASE):
                if _is_storey_context(text, m):
                    continue
                if _is_plan_ref_context(text, m):
                    continue
                if m.group(1).startswith("0") and len(m.group(1)) > 1:
                    continue
                yield from emit(unit_key, m, int(m.group(1)))


def _extract_explicit_total_units(text: str) -> List[int]:
    totals = []
    patterns = [
        r"\btotal\s*(\d{1,5})\b",
        r"\btotal\s*(?:no\.?\s*of\s*)?(?:dwelling|dwellings|dwelling unit|dwelling units|residential unit|residential units|unit|units|house|houses|dwelling house|dwelling houses|apartment|apartments|flat|flats|duplex(?:es)?|town ?house(?:s)?|bungalow(?:s)?|mews house(?:s)?)\s*(\d{1,5})\b",
        r"\b(?:units|dwellings|apartments|houses)\s*[:\-]?\s*(\d{1,5})\b(?!\s*/\s*\d)",
        r"\b(\d{1,5})\s*(?:no\.?\s*|no\s+of\s*|number\s+of\s*|number\s+)?(?:new\s*)?(?:dwelling|dwellings|dwelling unit|dwelling units|residential unit|residential units|unit|units)\b",
        r"\b(\d{1,5})\s*(?:no\.?\s*|no\s+of\s*|number\s+of\s*|number\s+)?(?:house|houses|dwelling house|dwelling houses|apartment|apartments|flat|flats|duplex(?:es)?|town ?house(?:s)?|bungalow(?:s)?|mews house(?:s)?)\b",
        r"\b(\d{1,5})\s*[- ]?unit\b",
        r"\bno\.?\s*(\d{1,5})\s*(?:dwelling|dwellings|dwelling unit|dwelling units|residential unit|residential units|unit|units)\b",
        r"\bno\.?\s*(\d{1,5})\s*(?:house|houses|dwelling house|dwelling houses|apartment|apartments|flat|flats|duplex(?:es)?|town ?house(?:s)?|bungalow(?:s)?|mews house(?:s)?)\b",
        r"\bno\s+of\s*(\d{1,5})\s*(?:dwelling|dwellings|dwelling unit|dwelling units|residential unit|residential units|unit|units)\b",
        r"\bno\s+of\s*(\d{1,5})\s*(?:house|houses|dwelling house|dwelling houses|apartment|apartments|flat|flats|duplex(?:es)?|town ?house(?:s)?|bungalow(?:s)?|mews house(?:s)?)\b",
        r"\b(\d{1,5})\s*no(?:s|'s)?\.?\s*(?:dwelling|dwellings|dwelling unit|dwelling units|residential unit|residential units|unit|units)\b",
        r"\b(\d{1,5})\s*no(?:s|'s)?\.?\s*(?:house|houses|dwelling house|dwelling houses|apartment|apartments|flat|flats|duplex(?:es)?|town ?house(?:s)?|bungalow(?:s)?|mews house(?:s)?)\b",
        # "No. 5 ... apartments" (number before unit within short span)
        r"\bno\.?\s*(\d{1,5})\b(?:(?!\n).){0,30}\b(?:dwellings|dwelling units|residential units|units|houses|dwelling houses|apartments|flats|duplex(?:es)?|town ?house(?:s)?|bungalow(?:s)?|mews house(?:s)?)\b",
        # "(5 no) dwellings" style
        r"\(\s*(\d{1,5})\s*no(?:s|'s)?\.?\s*\)\s*(?:dwelling|dwellings|dwelling unit|dwelling units|residential unit|residential units|unit|units|house|houses|dwelling house|dwelling houses|apartment|apartments|flat|flats|duplex(?:es)?|town ?house(?:s)?|bungalow(?:s)?|mews house(?:s)?)\b",
        # "2 number detached dwellings"
        r"\b(\d{1,5})\s*number\s*(?:detached|semi-?detached|terraced|new)?\s*(?:dwelling|dwellings|unit|units|house|houses|apartment|apartments)\b",
    ]
    for p in patterns:
        for m in re.finditer(p, text, flags=re.IGNORECASE):
            if m.lastindex:
                if _is_storey_context(text, m):
                    continue
                if _is_plan_ref_context(text, m):
                    continue
                if _is_measurement_context(text, m):
                    continue
                if _is_unit_fraction_context(text, m):
                    continue
                if _is_non_res_unit_context(text, m):
                    continue
                if m.group(m.lastindex).startswith("0") and len(m.group(m.lastindex)) > 1:
                    continue
                totals.append(int(m.group(m.lastindex)))
    # Word-number totals, e.g. "twenty apartments", "fifteen dwellings".
    for m in re.finditer(
        rf"\b({NUM_WORD_PATTERN})\b\s*(?:dwelling|dwellings|dwelling unit|dwelling units|residential unit|residential units|unit|units|house|houses|dwelling house|dwelling houses|apartment|apartments|flat|flats|duplex(?:es)?|town ?house(?:s)?|bungalow(?:s)?|mews house(?:s)?)\b",
        text,
        flags=re.IGNORECASE,
    ):
        if _is_storey_context(text, m):
            continue
        if _is_plan_ref_context(text, m):
            continue
        if _is_non_res_unit_context(text, m):
            continue
        n = word_to_num(m.group(1))
        if n is not None:
            totals.append(int(n))
    return totals


def _extract_bed_counts(text: str) -> Dict[str, int]:
    bed_counts: Dict[str, int] = {}
    # Pattern: "24 no. 3 bed" or "24 x 3 bed"
    for m in re.finditer(r"\b(\d{1,5})\s*(?:no\.?|number\s+of|x)?\s*(\d)\s*bed", text, flags=re.IGNORECASE):
        count = int(m.group(1))
        beds = m.group(2)
        key = f"bed_{beds}"
        bed_counts[key] = bed_counts.get(key, 0) + count
    return bed_counts


def _extract_parking_spaces(text: str) -> List[int]:
    spaces = []
    for m in re.finditer(
        r"\b(\d{1,5})\s*(?:no\.?\s*)?(?:car\s*)?parking\s*(?:spaces|space|bays|bay)\b",
        text,
        flags=re.IGNORECASE,
    ):
        spaces.append(int(m.group(1)))
    return spaces


def _extract_cycle_parking_spaces(text: str) -> List[int]:
    spaces = []
    for m in re.finditer(
        r"\b(\d{1,5})\s*(?:no\.?\s*)?(?:cycle|bicycle|bike)\s*parking\s*(?:spaces|space|bays|bay)\b",
        text,
        flags=re.IGNORECASE,
    ):
        spaces.append(int(m.group(1)))
    return spaces


def _extract_site_area(text: str) -> Tuple[float | None, float | None]:
    # hectares
    ha_vals = []
    for m in re.finditer(r"\b(?:c\.?\s*|circa\s*)?(\d+(?:\.\d+)?)\s*(?:ha|hectare|hectares)\b", text, flags=re.IGNORECASE):
        ha_vals.append(float(m.group(1)))
    # sqm - attempt to detect site area vs floor area based on nearby words
    sqm_vals = []
    for m in re.finditer(r"\b(\d+(?:\.\d+)?)\s*(?:sq\.?m|sqm|m2)\b", text, flags=re.IGNORECASE):
        start = max(0, m.start() - 20)
        context = text[start:m.end() + 20].lower()
        if "site" in context or "area" in context:
            sqm_vals.append(float(m.group(1)))
    return (max(ha_vals) if ha_vals else None, max(sqm_vals) if sqm_vals else None)


def _extract_floor_area(text: str) -> float | None:
    candidates = []
    for m in re.finditer(r"\b(\d+(?:\.\d+)?)\s*(?:sq\.?m|sqm|m2)\b", text, flags=re.IGNORECASE):
        start = max(0, m.start() - 20)
        context = text[start:m.end() + 20].lower()
        if "floor" in context or "gfa" in context or "gross" in context:
            candidates.append(float(m.group(1)))
    return max(candidates) if candidates else None


def _extract_use_floor_area(text: str, keywords: List[str]) -> float | None:
    candidates = []
    for m in re.finditer(r"\b(\d+(?:\.\d+)?)\s*(?:sq\.?m|sqm|m2)\b", text, flags=re.IGNORECASE):
        start = max(0, m.start() - 25)
        end = min(len(text), m.end() + 25)
        context = text[start:end].lower()
        if any(k in context for k in keywords):
            candidates.append(float(m.group(1)))
    return max(candidates) if candidates else None


def _extract_open_space_area(text: str) -> float | None:
    candidates = []
    for m in re.finditer(r"\b(\d+(?:\.\d+)?)\s*(?:sq\.?m|sqm|m2|ha|hectare|hectares)\b", text, flags=re.IGNORECASE):
        start = max(0, m.start() - 25)
        end = min(len(text), m.end() + 25)
        context = text[start:end].lower()
        if "open space" in context or "public open space" in context or "private open space" in context:
            val = float(m.group(1))
            if "ha" in m.group(0).lower() or "hectare" in m.group(0).lower():
                val = val * 10000
            candidates.append(val)
    return max(candidates) if candidates else None


def _extract_serviced_sites(text: str) -> List[int]:
    counts = []
    for m in re.finditer(r"\b(\d{1,5})\s*(?:no\.?\s*)?(?:serviced sites|serviced site)\b", text, flags=re.IGNORECASE):
        counts.append(int(m.group(1)))
    return counts


def _extract_phase(text: str) -> int | None:
    m = re.search(r"\bphase\s*(\d{1,2})\b", text, flags=re.IGNORECASE)
    return int(m.group(1)) if m else None


def _extract_non_res_uses(text: str) -> Dict[str, int | None]:
    found: Dict[str, int | None] = {}
    for key, variants in NON_RES_USES.items():
        found[key] = 1 if any(v in text.lower() for v in variants) else None
    return found


def _extract_storeys(text: str) -> float | None:
    storey_vals = []
    # numeric storey
    for m in re.finditer(r"\b(\d)\s*storey\b", text, flags=re.IGNORECASE):
        storey_vals.append(float(m.group(1)))
    # word storey
    for word, val in STOREY_WORDS.items():
        if re.search(rf"\b{word}\s*storey\b", text, flags=re.IGNORECASE):
            storey_vals.append(float(val))
    # storey and a half
    if re.search(r"\bstorey\s+and\s+a\s+half\b", text, flags=re.IGNORECASE):
        storey_vals.append(1.5)
    return max(storey_vals) if storey_vals else None


def extract_details(text: str) -> Dict[str, float | int | None]:
    text = normalize_text(text)

    unit_counts: Dict[str, int] = {}
    for unit_key, count in _iter_unit_counts(text):
        unit_counts[unit_key] = unit_counts.get(unit_key, 0) + count

    explicit_totals = _extract_explicit_total_units(text)
    total_from_explicit = max(explicit_totals) if explicit_totals else None
    total_from_types = sum(unit_counts.values()) if unit_counts else None

    bed_counts = _extract_bed_counts(text)
    parking_spaces = _extract_parking_spaces(text)
    cycle_parking_spaces = _extract_cycle_parking_spaces(text)
    site_area_ha, site_area_sqm = _extract_site_area(text)
    floor_area_sqm = _extract_floor_area(text)
    retail_area_sqm = _extract_use_floor_area(text, ["retail", "shop"])
    commercial_area_sqm = _extract_use_floor_area(text, ["commercial", "office"])
    creche_area_sqm = _extract_use_floor_area(text, ["creche", "childcare", "child care"])
    open_space_sqm = _extract_open_space_area(text)
    serviced_sites = _extract_serviced_sites(text)
    phase = _extract_phase(text)
    non_res_flags = _extract_non_res_uses(text)
    max_storeys = _extract_storeys(text)

    units_total_text = total_from_explicit if total_from_explicit is not None else (total_from_types if total_from_types else None)

    out: Dict[str, float | int | None] = {
        "units_total_text": units_total_text,
        "units_total_explicit": total_from_explicit,
        "units_total_from_types": total_from_types,
        "units_houses": unit_counts.get("houses"),
        "units_dwellings": unit_counts.get("dwellings"),
        "units_apartments": unit_counts.get("apartments"),
        "units_duplex": unit_counts.get("duplex"),
        "units_townhouses": unit_counts.get("townhouses"),
        "units_bungalows": unit_counts.get("bungalows"),
        "parking_spaces": max(parking_spaces) if parking_spaces else None,
        "cycle_parking_spaces": max(cycle_parking_spaces) if cycle_parking_spaces else None,
        "site_area_ha": site_area_ha,
        "site_area_sqm": site_area_sqm,
        "floor_area_sqm": floor_area_sqm,
        "retail_area_sqm": retail_area_sqm,
        "commercial_area_sqm": commercial_area_sqm,
        "creche_area_sqm": creche_area_sqm,
        "open_space_sqm": open_space_sqm,
        "serviced_sites": max(serviced_sites) if serviced_sites else None,
        "phase": phase,
        "max_storeys": max_storeys,
    }
    out.update(bed_counts)
    out.update({f"has_{k}": v for k, v in non_res_flags.items()})
    return out


def process_file(
    input_path: str,
    output_path: str,
    chunksize: int,
    min_units: int | None,
    summary_output: str | None,
    qa_output: str | None,
    qa_sample_size: int,
) -> None:
    keep_cols = [
        "PlanningAuthority",
        "ApplicationNumber",
        "Decision",
        "DevelopmentDescription",
        "NumResidentialUnits",
        "ReceivedDate",
        "DecisionDate",
    ]

    reader = pd.read_csv(input_path, chunksize=chunksize, low_memory=False)
    first = True
    summary_counts: Dict[str, int] = {}
    summary_total = 0
    qa_rows: List[Dict[str, object]] = []
    qa_counts: Dict[str, int] = {
        "missed_units": 0,
        "missed_parking": 0,
        "missed_area": 0,
        "missed_storeys": 0,
        "missed_beds": 0,
    }

    for chunk in reader:
        # ensure columns exist
        for col in keep_cols:
            if col not in chunk.columns:
                chunk[col] = pd.NA

        details = chunk["DevelopmentDescription"].fillna("").map(extract_details)
        details_df = pd.DataFrame(list(details))

        out = pd.concat([chunk[keep_cols], details_df], axis=1)
        # prefer text-extracted total, otherwise fall back to NumResidentialUnits
        out["units_total_final"] = out["units_total_text"].fillna(out["NumResidentialUnits"])

        if min_units is not None:
            out = out[out["units_total_final"].fillna(0) >= min_units]

        out.to_csv(output_path, mode="w" if first else "a", index=False, header=first)
        summary_total += len(out)
        for col in out.columns:
            if col in keep_cols or col == "DevelopmentDescription":
                continue
            non_null = out[col].notna().sum()
            summary_counts[col] = summary_counts.get(col, 0) + int(non_null)
        first = False

        if qa_output and qa_sample_size > 0 and len(qa_rows) < qa_sample_size:
            for _, row in out.iterrows():
                text = str(row.get("DevelopmentDescription") or "").lower()
                if not text:
                    continue
                missed_units = (
                    ("dwelling" in text or "unit" in text or "house" in text or "apartment" in text)
                    and pd.isna(row.get("units_total_text"))
                )
                missed_parking = ("parking" in text) and pd.isna(row.get("parking_spaces"))
                missed_area = (
                    (re.search(r"\b(?:sqm|sq\.?m|m2|ha|hectare|hectares)\b", text) is not None)
                    and pd.isna(row.get("floor_area_sqm"))
                    and pd.isna(row.get("site_area_sqm"))
                    and pd.isna(row.get("site_area_ha"))
                    and pd.isna(row.get("open_space_sqm"))
                )
                missed_storeys = ("storey" in text) and pd.isna(row.get("max_storeys"))
                missed_beds = ("bed" in text) and (row.filter(regex=r"^bed_").notna().sum() == 0)

                if missed_units:
                    qa_counts["missed_units"] += 1
                if missed_parking:
                    qa_counts["missed_parking"] += 1
                if missed_area:
                    qa_counts["missed_area"] += 1
                if missed_storeys:
                    qa_counts["missed_storeys"] += 1
                if missed_beds:
                    qa_counts["missed_beds"] += 1

                if any([missed_units, missed_parking, missed_area, missed_storeys, missed_beds]):
                    qa_rows.append(
                        {
                            "PlanningAuthority": row.get("PlanningAuthority"),
                            "ApplicationNumber": row.get("ApplicationNumber"),
                            "Decision": row.get("Decision"),
                            "units_total_text": row.get("units_total_text"),
                            "parking_spaces": row.get("parking_spaces"),
                            "site_area_ha": row.get("site_area_ha"),
                            "site_area_sqm": row.get("site_area_sqm"),
                            "floor_area_sqm": row.get("floor_area_sqm"),
                            "open_space_sqm": row.get("open_space_sqm"),
                            "max_storeys": row.get("max_storeys"),
                            "beds_found": int(row.filter(regex=r"^bed_").notna().sum()),
                            "missed_units": missed_units,
                            "missed_parking": missed_parking,
                            "missed_area": missed_area,
                            "missed_storeys": missed_storeys,
                            "missed_beds": missed_beds,
                            "DevelopmentDescription": row.get("DevelopmentDescription"),
                        }
                    )
                if len(qa_rows) >= qa_sample_size:
                    break

    if summary_output and summary_total > 0:
        summary_rows = []
        for col, count in summary_counts.items():
            summary_rows.append(
                {
                    "field": col,
                    "non_null_count": count,
                    "non_null_pct": round((count / summary_total) * 100, 2),
                }
            )
        pd.DataFrame(summary_rows).sort_values("non_null_pct", ascending=False).to_csv(summary_output, index=False)

    if qa_output and qa_rows:
        qa_df = pd.DataFrame(qa_rows)
        qa_df.to_csv(qa_output, index=False)
        qa_summary_path = qa_output.replace(".csv", "_summary.csv")
        pd.DataFrame([qa_counts]).to_csv(qa_summary_path, index=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="ground_source_data.csv")
    parser.add_argument("--output", default="downloads/ground_source_extracted_wide.csv")
    parser.add_argument("--chunksize", type=int, default=50000)
    parser.add_argument("--min-units", type=int, default=None, dest="min_units")
    parser.add_argument("--summary-output", default=None)
    parser.add_argument("--qa-output", default=None)
    parser.add_argument("--qa-sample-size", type=int, default=200)
    args = parser.parse_args()

    process_file(
        args.input,
        args.output,
        args.chunksize,
        args.min_units,
        args.summary_output,
        args.qa_output,
        args.qa_sample_size,
    )


if __name__ == "__main__":
    main()
