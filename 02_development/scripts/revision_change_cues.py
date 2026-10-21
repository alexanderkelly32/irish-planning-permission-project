"""Conservative review cues from a refused/revised description pair; never causal labels."""
from __future__ import annotations

import re


THEME_TERMS = {
    "density_scale": ("density", "scale", "height", "overdevelopment", "units", "apartment"),
    "open_space_amenity": ("open space", "amenity", "overlooking", "daylight", "sunlight"),
    "access_parking": ("access", "traffic", "parking", "junction", "cycle"),
    "drainage_environment": ("drainage", "flood", "attenuation", "ecology", "natura", "water"),
    "policy_land_use": ("zoning", "policy", "development plan", "land use"),
}


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def extract_review_cues(original_description: object, revised_description: object, refusal_reason: object) -> list[str]:
    """Return only themes present in the refusal and newly/relevantly mentioned in revision text."""
    original = _clean(original_description)
    revised = _clean(revised_description)
    refusal = _clean(refusal_reason)
    cues: list[str] = []
    for theme, terms in THEME_TERMS.items():
        refusal_hits = [term for term in terms if term in refusal]
        revised_hits = [term for term in terms if term in revised]
        original_hits = [term for term in terms if term in original]
        if refusal_hits and revised_hits and (set(revised_hits) - set(original_hits) or revised != original):
            cues.append(theme)
    return cues
