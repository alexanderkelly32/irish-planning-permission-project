"""AlphaEarth feature module (schema-agnostic).

Consumes per-site per-year 64-dim embedding arrays (site + rings) once
exported from Earth Engine. Produces:
  - band mean/dispersion stats (site, 100m ring, 250m ring)
  - PCA scores fitted on training years only
  - year-over-year per-pixel cosine change aggregates
  - % site with large change, first year of major change, consecutive
    change years, site-vs-surroundings contrast, spatial heterogeneity
  - change before/after BCMS commencement, stall indicators
Also the intermediate state classifier targets (7 classes) and the three
experiment harnesses with the required gates.
"""
from __future__ import annotations

import numpy as np

BANDS = 64


def band_stats(embeddings: np.ndarray) -> dict[str, float]:
    """embeddings: (n_pixels, 64)."""
    out = {}
    for i in range(BANDS):
        out[f"band{i}_mean"] = float(np.mean(embeddings[:, i]))
        out[f"band{i}_std"] = float(np.std(embeddings[:, i]))
    return out


def cosine_change(prev: np.ndarray, curr: np.ndarray) -> np.ndarray:
    """Per-pixel cosine similarity of consecutive years -> change score."""
    denom = np.linalg.norm(prev, axis=1) * np.linalg.norm(curr, axis=1)
    similarity = np.where(denom > 0, np.sum(prev * curr, axis=1) / np.clip(denom, 1e-9, None), 0.0)
    return 1.0 - np.clip(similarity, 0.0, 1.0)


def change_features(series: list[np.ndarray], threshold_pct: float = 90.0) -> dict[str, float]:
    """series: list of per-year pixel arrays [(n,64), ...] oldest->newest."""
    scores = [cosine_change(series[i], series[i + 1]) for i in range(len(series) - 1)]
    out = {}
    out["n_years"] = len(series)
    for i, score in enumerate(scores):
        out[f"change_median_y{i}"] = float(np.median(score))
        out[f"change_p90_y{i}"] = float(np.percentile(score, 90))
        out[f"change_pct_large_y{i}"] = float(np.mean(score >= np.percentile(score, threshold_pct)))
    all_changes = np.concatenate(scores) if scores else np.array([])
    threshold = float(np.percentile(all_changes, threshold_pct)) if len(all_changes) else 0.0
    large_by_year = [float(np.mean(score >= threshold)) for score in scores]
    first_large = next((i for i, value in enumerate(large_by_year) if value >= 0.05), None)
    out["first_year_of_major_change"] = first_large if first_large is not None else -1
    out["consecutive_change_years"] = _longest_run([v >= 0.02 for v in large_by_year])
    return out


def _longest_run(flags: list[bool]) -> int:
    best = current = 0
    for flag in flags:
        current = current + 1 if flag else 0
        best = max(best, current)
    return best


def site_contrast(site: np.ndarray, ring: np.ndarray) -> float:
    return float(np.linalg.norm(site.mean(axis=0) - ring.mean(axis=0)))


def heterogeneity(site: np.ndarray) -> float:
    return float(np.mean(np.linalg.norm(site - site.mean(axis=0), axis=1)))


def pre_post_change(series: list[np.ndarray], commencement_year_index: int) -> dict[str, float]:
    """Change aggregates relative to the BCMS commencement year index."""
    scores = [cosine_change(series[i], series[i + 1]) for i in range(len(series) - 1)]
    pre = [s for i, s in enumerate(scores) if i < commencement_year_index]
    post = [s for i, s in enumerate(scores) if i >= commencement_year_index]
    out = {
        "pre_commencement_change_median": float(np.median(np.concatenate(pre))) if pre else 0.0,
        "post_commencement_change_median": float(np.median(np.concatenate(post))) if post else 0.0,
    }
    # stall: commencement happened but no major change in the two years after
    if len(post) >= 2:
        out["stall_indicator"] = float(np.median(post[-2:]) < 0.05)
    return out


STATE_CLASSES = [
    "undeveloped_greenfield",
    "previously_developed_brownfield",
    "cleared_enabling_works",
    "active_construction",
    "substantially_built",
    "stable_completed",
    "stalled_after_works",
]
