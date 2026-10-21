"""Description quality checks for the v4 playground.

- number cross-check: numbers (digits or words) in the description vs the
  structured fields (units / site area / floor area)
- model-vocabulary check: flags words the model's TF-IDF vocabulary doesn't
  know (typos and out-of-vocabulary words) with closest in-vocab suggestions
"""
from __future__ import annotations

import re

WORD_NUMBERS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100, "thousand": 1000, "dozen": 12,
}

UNIT_CONTEXT = re.compile(
    r"(?:no\.?|number of|units?|apartments?|dwellings?|houses?|homes?|residential units?|residential)",
    re.IGNORECASE,
)
AREA_CONTEXT = re.compile(r"(?:sq\.?\s?m|m2|m\u00b2|square metres|hectares?|ha\b|acres?)", re.IGNORECASE)


def _words_to_number(words: list[str]) -> int | None:
    total = 0
    current = 0
    for word in words:
        if word not in WORD_NUMBERS:
            return None
        value = WORD_NUMBERS[word]
        if value >= 1000:
            total = (total + current) * value
            current = 0
        elif value == 100:
            current = (current or 1) * 100
        else:
            current += value
    result = total + current
    return result if result > 0 else None


def extract_numbers(description: str) -> list[dict]:
    """Returns numbers found in the description with unit/area context flags."""
    found: list[dict] = []
    text = description or ""

    for match in re.finditer(r"\b(\d{1,4}(?:\.\d+)?)\b", text):
        after = text[match.end():match.end() + 25]
        before = text[max(0, match.start() - 10):match.start()]
        found.append({
            "value": float(match.group(1)),
            "source": match.group(1),
            "is_units": bool(UNIT_CONTEXT.search(after)) or bool(re.search(r"no\.?$", before)),
            "is_area": bool(AREA_CONTEXT.search(after)),
        })

    for match in re.finditer(
        r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand))*\b",
        text,
        re.IGNORECASE,
    ):
        phrase = match.group(0).lower()
        words = re.split(r"[-\s]+", phrase)
        value = _words_to_number(words)
        if value is None or value > 10000:
            continue
        after = text[match.end():match.end() + 25]
        before = text[max(0, match.start() - 10):match.start()]
        found.append({
            "value": float(value),
            "source": match.group(0),
            "is_units": bool(UNIT_CONTEXT.search(after)) or bool(re.search(r"no\.?$", before)),
            "is_area": bool(AREA_CONTEXT.search(after)),
        })
    return found


def cross_check_numbers(description: str, units: int, site_area_sqm: float, floor_area_sqm: float) -> list[str]:
    warnings: list[str] = []
    numbers = extract_numbers(description)
    if not numbers:
        return warnings
    fields = {"units": float(units), "site area (m\u00b2)": float(site_area_sqm), "floor area (m\u00b2)": float(floor_area_sqm)}
    seen_values: set[float] = set()
    for item in numbers:
        if item["value"] in seen_values:
            continue
        seen_values.add(item["value"])
        if item["is_units"] and item["value"] != fields["units"]:
            warnings.append(
                f"Description says \u2018{item['source']}\u2019 units but the Units field is {int(fields['units'])} \u2013 check they agree."
            )
        elif not item["is_units"] and item["is_area"] and item["value"] not in (fields["site area (m\u00b2)"], fields["floor area (m\u00b2)"]):
            if 0.01 <= item["value"] <= 2000:
                warnings.append(
                    f"Description mentions an area of \u2018{item['source']}\u2019 that matches neither the site area nor the floor area field."
                )
    return warnings


def check_vocabulary(description: str, vocabulary: set[str], max_suggestions: int = 6) -> list[dict]:
    """Flags single words not in the model's TF-IDF vocabulary (typos / OOV)."""
    from difflib import get_close_matches

    flagged: list[dict] = []
    words = re.findall(r"[a-z\u00e9\u00ed\u00fa\u00e1\u00f3]+", (description or "").lower())
    for word in words:
        if word in vocabulary or len(word) <= 2 or word.isdigit():
            continue
        if word.endswith("s") and word[:-1] in vocabulary:
            continue
        suggestions = get_close_matches(word, vocabulary, n=1, cutoff=0.86)
        flagged.append({"word": word, "suggestion": suggestions[0] if suggestions else None})
    return flagged[:max_suggestions]
