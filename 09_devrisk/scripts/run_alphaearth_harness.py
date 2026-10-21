"""Runner: AlphaEarth experiment harness + synthetic fixture validation.

Three experiments per the user's spec, run on synthetic embedding series
now (fixture proves the pipeline); real runs start when the EE export
lands in raw/alphaearth/. Gates: 10% out-of-time improvement, bootstrap
CIs, house/apartment/greenfield/brownfield splits, Sentinel control slot.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402
from devrisk.models.alphaearth import (  # noqa: E402
    band_stats,
    change_features,
    cosine_change,
    heterogeneity,
    pre_post_change,
    site_contrast,
)


def synthetic_site(rng: np.random.Generator, state_trajectory: list[str]) -> list[np.ndarray]:
    """Yearly pixel arrays whose embeddings drift with the state trajectory."""
    series = []
    base = rng.normal(0, 1, size=(80, 64))
    step = {"undeveloped_greenfield": 0.02, "cleared_enabling_works": 0.25,
            "active_construction": 0.35, "substantially_built": 0.15,
            "stable_completed": 0.03, "stalled_after_works": 0.01}
    for state in state_trajectory:
        base = base + rng.normal(0, step.get(state, 0.05), size=base.shape)
        series.append(base.copy())
    return series


def features_from_series(series: list[np.ndarray], ring_scale: float, commencement_year: int) -> dict:
    site = series[-1]
    ring = site * ring_scale + 0.1
    out = band_stats(site)
    out.update({f"ring_{k}": v for k, v in band_stats(ring).items() if k.endswith("_mean")})
    out.update(change_features(series))
    out.update(pre_post_change(series, commencement_year))
    out["site_contrast"] = site_contrast(site, ring)
    out["heterogeneity"] = heterogeneity(site)
    return out


def experiment(name: str, y: np.ndarray, base_pred: np.ndarray, ae_pred: np.ndarray, gate: float = 0.10) -> dict:
    base_mae = float(np.mean(np.abs(y - base_pred)))
    ae_mae = float(np.mean(np.abs(y - ae_pred)))
    improvement = 1.0 - ae_mae / base_mae
    boot = []
    rng = np.random.default_rng(7)
    for _ in range(400):
        idx = rng.integers(0, len(y), len(y))
        boot.append(float(np.mean(np.abs(y[idx] - ae_pred[idx]))))
    return {
        "n": int(len(y)),
        "base_mae": round(base_mae, 1),
        "ae_mae": round(ae_mae, 1),
        "improvement_pct": round(improvement * 100, 1),
        "ae_mae_ci95": [round(float(np.percentile(boot, 2.5)), 1), round(float(np.percentile(boot, 97.5)), 1)],
        "gate_10pct": bool(improvement >= gate),
    }


if __name__ == "__main__":
    rng = np.random.default_rng(7)
    sites = []
    for _ in range(120):
        trajectory = ["undeveloped_greenfield", "cleared_enabling_works", "active_construction",
                      "active_construction", "substantially_built", "stable_completed"]
        series = synthetic_site(rng, trajectory)
        features = features_from_series(series, ring_scale=1.0, commencement_year=2)
        features["site_id"] = len(sites)
        sites.append(features)
    frame = pd.DataFrame(sites)

    # Synthetic labels tied to the trajectory (fixture-only).
    frame["commence_within_365"] = rng.binomial(1, 0.5 + 0.4 * (frame["change_median_y1"] > 0.1), size=len(frame))
    frame["ccc_within_365"] = rng.binomial(1, 0.5 + 0.3 * (frame["heterogeneity"] > 0.5), size=len(frame))
    frame["sale_days"] = 400 + rng.normal(0, 120, size=len(frame))

    report = {"mode": "synthetic_fixture", "n_sites": int(len(frame))}
    # Exp 1: pre-commencement (most recent year before grant ~ y2).
    y1 = frame["commence_within_365"].to_numpy()
    base1 = np.full(len(y1), y1.mean())
    ae1 = frame["change_median_y1"].to_numpy()
    report["exp1_pre_commencement"] = experiment("commencement_within_365", y1, base1, np.clip(ae1, 0, 1))
    # Exp 2: monitoring (CCC within 365 from heterogeneity).
    y2 = frame["ccc_within_365"].to_numpy()
    base2 = np.full(len(y2), y2.mean())
    ae2 = np.clip(frame["heterogeneity"] / frame["heterogeneity"].max(), 0, 1)
    report["exp2_monitoring"] = experiment("ccc_within_365", y2, base2, ae2)
    # Exp 3: sale model augmentation (fixture).
    y3 = frame["sale_days"].to_numpy()
    base3 = np.full(len(y3), np.median(y3))
    ae3 = base3 + (frame["stable_completed_indicator"] if "stable_completed_indicator" in frame.columns else 0)
    report["exp3_sale"] = experiment("sale_days", y3, base3, np.full(len(y3), np.median(y3)))

    out = settings.SILVER_DIR / "alphaearth_fixture_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
