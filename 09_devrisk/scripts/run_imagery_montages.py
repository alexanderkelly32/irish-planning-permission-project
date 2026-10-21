"""Stage 1 feasibility: per-site montages + admin-event alignment.

Montages: S1 VH, S2 NDVI, S2 NDBI monthly series with markers for grant,
commencement, first CCC, first sale. Then: does a sustained NDBI/VH change
align with BCMS commencement? (first-pass change baseline)
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SILVER = settings.SILVER_DIR
OUT = SILVER / "imagery" / "montages"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    import json
    frame = pd.read_csv(SILVER / "imagery" / "sentinel_monthly.csv")
    frame["ym_dt"] = pd.to_datetime(frame["ym"] + "-01")
    cohort = pd.read_csv(SILVER / "imagery" / "feasibility_50.csv", dtype=str)
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["case_key", "GrantDate"])
    reg = reg.drop_duplicates("case_key")
    reg["grant"] = pd.to_datetime(reg["GrantDate"], utc=True, errors="coerce").dt.tz_localize(None)
    labels = pd.read_csv(SILVER / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    labels = labels[labels["activation_linked"].astype(str).str.lower() == "true"]
    labels["comm"] = reg["case_key"].map(reg.set_index("case_key")["grant"]) + pd.to_timedelta(
        pd.to_numeric(labels["activation_days"], errors="coerce"), unit="D")
    ccc = pd.read_csv(SILVER / "ccc_blocks.csv", dtype=str)
    ccc["first_ccc"] = pd.to_datetime(ccc["first_ccc"], utc=True, errors="coerce").dt.tz_localize(None)
    sales = pd.read_csv(SILVER / "scheme_sales_bcms_notice_auto.csv", dtype=str)
    sales["sale_date"] = pd.to_datetime(sales["sale_date"], utc=True, errors="coerce").dt.tz_localize(None)

    align = []
    for pid, g in frame.groupby("development_id"):
        g = g.sort_values("ym_dt")
        events = {}
        if (reg["case_key"] == pid).any():
            g0 = reg.loc[reg["case_key"] == pid, "grant"].iloc[0]
            if pd.notna(g0):
                events["grant"] = g0
        if (labels["case_key"] == pid).any():
            c0 = labels.loc[labels["case_key"] == pid, "comm"].iloc[0]
            if pd.notna(c0):
                events["comm"] = c0
        if (ccc["scheme_id"] == pid).any():
            f0 = ccc.loc[ccc["scheme_id"] == pid, "first_ccc"].min()
            if pd.notna(f0):
                events["ccc"] = f0
        if (sales["scheme_id"] == pid).any():
            s0 = sales.loc[sales["scheme_id"] == pid, "sale_date"].min()
            if pd.notna(s0):
                events["sale"] = s0

        fig, axes = plt.subplots(3, 1, figsize=(14, 8), sharex=True)
        for ax, col, name in [(axes[0], "s1_vh", "S1 VH (dB)"), (axes[1], "s2_ndvi", "S2 NDVI"),
                              (axes[2], "s2_ndbi", "S2 NDBI")]:
            ax.plot(g["ym_dt"], g[col], lw=1)
            ax.set_ylabel(name)
            ax.grid(alpha=0.3)
            for label, dt in events.items():
                ax.axvline(dt, color={"grant": "green", "comm": "orange", "ccc": "red",
                                      "sale": "purple"}[label], alpha=0.7, lw=1.5,
                           label=label if col == "s1_vh" else None)
        axes[0].legend(loc="upper right", fontsize=8)
        axes[0].set_title(pid[:70])
        fig.tight_layout()
        fig.savefig(OUT / f"{pid.replace('/', '_').replace(' ', '_')[:70]}.png", dpi=100)
        plt.close(fig)

        # first-pass change baseline: mean NDBI + VH shift in the 6m after
        # commencement vs 6m before
        if "comm" in events:
            pre = g[(g["ym_dt"] >= events["comm"] - pd.Timedelta(days=180)) &
                    (g["ym_dt"] < events["comm"])]
            post = g[(g["ym_dt"] >= events["comm"]) &
                     (g["ym_dt"] <= events["comm"] + pd.Timedelta(days=180))]
            if len(pre) >= 2 and len(post) >= 2:
                align.append({"development_id": pid,
                              "d_vh": float(post["s1_vh"].mean() - pre["s1_vh"].mean()),
                              "d_ndbi": float(post["s2_ndbi"].mean() - pre["s2_ndbi"].mean()),
                              "d_ndvi": float(post["s2_ndvi"].mean() - pre["s2_ndvi"].mean())})
    al = pd.DataFrame(align)
    al.to_csv(SILVER / "imagery" / "commencement_alignment.csv", index=False)
    print(json.dumps({"n_montages": len(list(OUT.glob('*.png'))),
                      "n_aligned": int(len(al)),
                      "mean_d_vh": round(float(al['d_vh'].mean()), 2) if len(al) else None,
                      "mean_d_ndbi": round(float(al['d_ndbi'].mean()), 3) if len(al) else None,
                      "mean_d_ndvi": round(float(al['d_ndvi'].mean()), 3) if len(al) else None,
                      "pct_vh_positive": round(float((al['d_vh'] > 0).mean() * 100), 1) if len(al) else None,
                      "pct_ndbi_positive": round(float((al['d_ndbi'] > 0).mean() * 100), 1) if len(al) else None},
                     indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
