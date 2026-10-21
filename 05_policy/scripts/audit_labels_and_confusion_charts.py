#!/usr/bin/env python3
"""Label-quality audit + confusion-rate-by-units charts for the v3 holdout."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "05_policy" / "current"
sys.path.insert(0, str(ROOT / "05_policy" / "scripts"))

PRED = OUT / "raw_planning_v3_2025_predictions.csv"

norm = lambda s: re.sub(r"[^a-z0-9]+", "", str(s).lower())


def load_units(pred: pd.DataFrame) -> pd.Series:
    corrected = pd.read_csv(ROOT / "02_development" / "current" / "ground_source_units_corrected.csv", low_memory=False)
    corrected_map = {norm(k): v for k, v in zip(corrected["case_key"].astype(str), pd.to_numeric(corrected["units_corrected"], errors="coerce")) if pd.notna(v)}
    holdout_units = pd.read_csv(ROOT / "02_development" / "current" / "holdout_units_extracted.csv", low_memory=False)
    holdout_map = {norm(k): v for k, v in zip(holdout_units["case_key"].astype(str), pd.to_numeric(holdout_units["units_final"], errors="coerce")) if pd.notna(v)}
    key_norm = pred["case_key"].astype(str).map(norm)
    units = key_norm.map(corrected_map)
    units = units.fillna(key_norm.map(holdout_map))
    return units


def main() -> None:
    pred = pd.read_csv(PRED, low_memory=False)
    pred["units"] = load_units(pred)

    from build_prospective_calibration_backtest import prepare  # noqa: E402

    reg = prepare()[["case_key", "ApplicationStatus", "Decision", "AppealStatus", "AppealDecision", "DevelopmentDescription"]]
    joined = pred.merge(reg, on="case_key", how="left")

    refused = joined[joined["target_refused"] == 1]
    granted = joined[joined["target_refused"] == 0]
    print("holdout refused:", len(refused), "granted:", len(granted), flush=True)

    appeal_decision = refused["AppealDecision"].fillna("").astype(str).str.upper()
    appeal_overturned = appeal_decision.str.contains(r"GRANT|MODIFIED|CONDITIONAL", regex=True)
    appeal_upheld = appeal_decision.str.contains(r"REFUS", regex=True)
    n_overturned = int(appeal_overturned.sum())
    n_appealed = int((appeal_overturned | appeal_upheld).sum())
    audit = {
        "holdout_refused": int(len(refused)),
        "appealed": n_appealed,
        "appeal_overturned_refusal": n_overturned,
        "appeal_overturn_rate_of_appealed": round(float(n_overturned / n_appealed), 4) if n_appealed else None,
        "appeal_overturn_share_of_all_refused": round(float(n_overturned / len(refused)), 4),
        "refused_appeal_status_counts": refused["AppealStatus"].fillna("").astype(str).value_counts().head(8).to_dict(),
        "refused_appeal_decision_counts": refused["AppealDecision"].fillna("").astype(str).value_counts().head(8).to_dict(),
        "refused_application_status_counts": refused["ApplicationStatus"].fillna("").astype(str).value_counts().head(8).to_dict(),
    }
    print("audit:", audit, flush=True)

    audit_pack = refused.sample(150, random_state=42)[["case_key", "PlanningAuthority", "application_bucket", "DevelopmentDescription", "Decision", "AppealStatus", "AppealDecision", "v3_platt_risk"]].copy()
    audit_pack.to_csv(OUT / "holdout_refusal_label_audit_pack.csv", index=False)

    geo = joined[joined["units"] >= 10].copy()
    bins = [10, 15, 20, 25, 30, 40, 60, 100, np.inf]
    labels = ["10-14", "15-19", "20-24", "25-29", "30-39", "40-59", "60-99", "100+"]
    geo["bucket"] = pd.cut(geo["units"], bins=bins, labels=labels, right=False)
    rng = np.random.default_rng(7)
    rows = []
    for bucket, group in geo.groupby("bucket", observed=True):
        r = group[group["target_refused"] == 1]
        g = group[group["target_refused"] == 0]
        n_r, n_g = len(r), len(g)
        if n_r < 2 or n_g < 2:
            continue
        ri = r.sample(min(n_r, 600), random_state=1)["v3_platt_risk"].to_numpy()
        gi = rng.choice(g["v3_platt_risk"].to_numpy(), size=min(n_g, 3000), replace=False)
        pairs_r = np.repeat(ri, len(gi))
        pairs_g = np.tile(gi, len(ri))
        discordant = pairs_r < pairs_g
        gaps = np.abs(pairs_r - pairs_g)[discordant]
        rows.append({
            "bucket": bucket,
            "n_refused": n_r,
            "n_granted": n_g,
            "refusal_rate": round(float(n_r / (n_r + n_g)), 3),
            "confusion_rate": round(float(discordant.mean()), 4),
            "confused_median_gap_pp": round(float(np.median(gaps)) * 100, 1) if len(gaps) else None,
            "confused_p90_gap_pp": round(float(np.quantile(gaps, 0.9)) * 100, 1) if len(gaps) else None,
        })
    table = pd.DataFrame(rows)
    print(table.to_string(index=False), flush=True)

    fig, axes = plt.subplots(1, 3, figsize=(19, 5.5))
    axes[0].plot(table["bucket"].astype(str), table["confusion_rate"] * 100, marker="o", color="#c0392b")
    axes[0].set_title("Model confusion rate by scheme size (v3 holdout, units >= 10)")
    axes[0].set_xlabel("units")
    axes[0].set_ylabel("% of refused/granted pairs misordered")
    axes[0].grid(alpha=0.3)
    axes[1].plot(table["bucket"].astype(str), table["confused_median_gap_pp"], marker="s", color="#2471a3", label="median gap")
    axes[1].plot(table["bucket"].astype(str), table["confused_p90_gap_pp"], marker="^", color="#7f8c8d", label="p90 gap")
    axes[1].set_title("How far apart are the confused pairs? (risk pp)")
    axes[1].set_xlabel("units")
    axes[1].set_ylabel("calibrated risk gap (pp)")
    axes[1].legend()
    axes[1].grid(alpha=0.3)
    axes[2].plot(table["bucket"].astype(str), table["refusal_rate"] * 100, marker="d", color="#1e8449")
    axes[2].set_title("Refusal rate by scheme size")
    axes[2].set_xlabel("units")
    axes[2].set_ylabel("% refused")
    axes[2].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "confusion_by_units.png", dpi=110)
    print("saved confusion_by_units.png", flush=True)

    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

    gap_bands = [(0, 0.05, "<5pp"), (0.05, 0.10, "5-10pp"), (0.10, 0.20, "10-20pp"), (0.20, 9.9, ">20pp")]
    surface = []
    for bucket, group in geo.groupby("bucket", observed=True):
        r = group[group["target_refused"] == 1]
        g = group[group["target_refused"] == 0]
        if len(r) < 2 or len(g) < 2:
            continue
        ri = r.sample(min(len(r), 400), random_state=1)["v3_platt_risk"].to_numpy()
        gi = rng.choice(g["v3_platt_risk"].to_numpy(), size=min(len(g), 1500), replace=False)
        pairs_r = np.repeat(ri, len(gi))
        pairs_g = np.tile(gi, len(ri))
        discordant = pairs_r < pairs_g
        gaps = np.abs(pairs_r - pairs_g)
        for lo, hi, name in gap_bands:
            sel = discordant & (gaps >= lo) & (gaps < hi)
            surface.append({"bucket": str(bucket), "band": name, "share_of_confusions": round(float(sel.sum() / discordant.sum()), 4) if discordant.sum() else 0.0})
    surf = pd.DataFrame(surface)
    pivot = surf.pivot(index="band", columns="bucket", values="share_of_confusions")
    fig3 = plt.figure(figsize=(11, 7))
    ax3 = fig3.add_subplot(111, projection="3d")
    xs = np.arange(len(pivot.columns))
    ys = np.arange(len(pivot.index))
    xpos, ypos = np.meshgrid(xs + 0.5, ys + 0.5)
    xpos = xpos.ravel()
    ypos = ypos.ravel()
    zpos = np.zeros_like(xpos)
    dz = pivot.to_numpy().T.ravel()
    dx = dy = 0.7 * np.ones_like(dz)
    colors = plt.cm.viridis(np.clip(dz * 2.5, 0, 1))
    ax3.bar3d(xpos, ypos, zpos, dx, dy, dz, color=colors, shade=True)
    ax3.set_xticks(xs + 0.85)
    ax3.set_xticklabels(pivot.columns, rotation=30)
    ax3.set_yticks(ys + 0.85)
    ax3.set_yticklabels(pivot.index)
    ax3.set_zlim(0, 0.6)
    ax3.set_xlabel("units")
    ax3.set_ylabel("risk gap band of the confusion")
    ax3.set_zlabel("share of confusions")
    ax3.set_title("Where do confusions land? share by units x risk-gap band")
    fig3.tight_layout()
    fig3.savefig(OUT / "confusion_3d_by_units.png", dpi=110)
    print("saved confusion_3d_by_units.png", flush=True)

    audit_path = OUT / "holdout_refusal_label_audit.json"
    import json  # noqa: E402

    audit_path.write_text(json.dumps({"audit": audit, "confusion_table": table.to_dict("records")}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
