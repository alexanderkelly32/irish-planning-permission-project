"""Sprint 3: Experiment 1 (latent site difficulty) + 2 (risk-adjusted alpha).

E1: shrunk site residuals over the observable-difficulty baseline; hold
out later apps on known sites AND unseen sites; test whether site effects
predict future outcomes beyond observables; report identifiability.
E2: shrunk developer-group residuals (time-safe); prospective test on
2021+ apps of groups with prior history; stability checks.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "sprint3"


def shrunk_mean(res: pd.Series, n: pd.Series, k: float) -> pd.Series:
    return res * (n / (n + k))


def main() -> None:
    frame = pd.read_csv(OUT / "site_apps_scored.csv")
    frame = frame.dropna(subset=["expected_p"])
    frame["residual"] = frame["y"] - frame["expected_p"]

    # TIME-SAFE site effects: computed on train (year < 2021) only.
    train = frame[frame["year"] < 2021]
    test = frame[frame["year"] >= 2021]
    site_stats = train.groupby("site_id").agg(n=("y", "size"), resid=("residual", "mean"),
                                              min_year=("year", "min"))
    site_stats["site_effect"] = shrunk_mean(site_stats["resid"], site_stats["n"], 5.0)
    frame = frame.merge(site_stats[["site_effect", "n", "min_year"]], on="site_id", how="left")

    test = frame[frame["year"] >= 2021]
    known = test[test["min_year"] < 2021]
    unseen = test[test["min_year"] >= 2021]
    e1 = {"n_sites_train": int(site_stats.index.nunique()), "n_train": int(len(train)),
          "n_test": int(len(test)), "n_known_sites_test": int(len(known)),
          "n_unseen_test": int(len(unseen))}
    if len(known) >= 200:
        base_auc = roc_auc_score(known["y"], known["expected_p"])
        aug_auc = roc_auc_score(known["y"], np.clip(known["expected_p"] + known["site_effect"], 0, 1))
        e1["known_sites_auc"] = {"observable_only": round(float(base_auc), 3),
                                 "with_site_effect": round(float(aug_auc), 3),
                                 "lift": round(float(aug_auc - base_auc), 3)}
    if len(unseen) >= 200:
        e1["unseen_sites_auc"] = round(float(roc_auc_score(unseen["y"], unseen["expected_p"])), 3)
    obs_corr = frame.groupby("site_id")["expected_p"].mean().rename("obs").reset_index().merge(
        site_stats[["site_effect"]].reset_index(), on="site_id")
    e1["identifiability"] = {
        "corr_site_effect_vs_observables": round(float(obs_corr["site_effect"].corr(obs_corr["obs"])), 3),
        "site_effect_sd": round(float(site_stats["site_effect"].std()), 4),
        "residual_sd": round(float(frame["residual"].std()), 4),
    }

    dev = pd.read_csv(SILVER / "developer_groups.csv", dtype=str)
    dev = dev.dropna(subset=["group_id", "case_key"])
    print("dev rows:", len(dev), "overlap with frame:", frame["case_key"].isin(set(dev["case_key"])).sum(), flush=True)
    dev_map = dev.drop_duplicates("case_key").set_index("case_key")["group_id"]
    frame["group_id"] = frame["case_key"].map(dev_map)
    gstats = frame.dropna(subset=["group_id"]).groupby("group_id").agg(
        n=("y", "size"), resid=("residual", "mean"), min_year=("year", "min"))
    gstats["dev_effect"] = shrunk_mean(gstats["resid"], gstats["n"], 8.0)
    frame = frame.merge(gstats[["dev_effect", "min_year"]].rename(columns={"min_year": "dev_min_year"}),
                        left_on="group_id", right_index=True, how="left")
    test = frame[frame["year"] >= 2021]
    dev_known = test[test["dev_min_year"].notna() & (test["dev_min_year"] < 2021)]
    e2 = {"n_groups": int(gstats.index.nunique()),
          "n_apps_with_group": int(frame["group_id"].notna().sum()),
          "n_prospective_apps": int(len(dev_known))}
    if len(dev_known) >= 150:
        base_auc = roc_auc_score(dev_known["y"], dev_known["expected_p"])
        aug_auc = roc_auc_score(dev_known["y"], np.clip(dev_known["expected_p"] + dev_known["dev_effect"], 0, 1))
        e2["prospective_auc"] = {"observable_only": round(float(base_auc), 3),
                                 "with_dev_effect": round(float(aug_auc), 3),
                                 "lift": round(float(aug_auc - base_auc), 3)}
        e2["out_of_time_residual_correlation"] = round(
            float(dev_known["dev_effect"].corr(dev_known["residual"])), 3)
    e2["stability"] = {
        "split_half_rank_corr": round(float(
            gstats["dev_effect"].sample(frac=0.5, random_state=1)
            .corr(gstats["dev_effect"].sample(frac=0.5, random_state=2))), 3),
    }

    report = {"e1_site_difficulty": e1, "e2_developer_alpha": e2}
    (OUT / "sprint3_e1_e2_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
