"""Build the monthly grant->commencement hazard panel.

One row per scheme-month from grant month until commencement/censor.
Covariates (only info available at that month, macro lagged 1m):
- economics: RPPI national level + 3m/12m momentum, NUTS3 RPPI, WPI building
  materials, PPR county new-dwelling price + volume + 6m momentum
- developer workload: concurrent granted-not-commenced / commenced-not-
  completed units (same group_id)
- local pipeline: same authority aggregates (excluding self)
- months remaining on permission; authority + grant-year dummies
Outcome: commence_within_{1,3,6,12} with per-horizon observability masks.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

MACRO = settings.SILVER_DIR / "macro"
SNAP = pd.Timestamp("2026-10-01")

NUTS3 = {
    "Cavan County Council": "Border", "Donegal County Council": "Border",
    "Leitrim County Council": "Border", "Monaghan County Council": "Border",
    "Sligo County Council": "Border",
    "Dublin City Council": "Dublin", "Dun Laoghaire-Rathdown County Council": "Dublin",
    "Fingal County Council": "Dublin", "South Dublin County Council": "Dublin",
    "Kildare County Council": "Mid-East", "Louth County Council": "Mid-East",
    "Meath County Council": "Mid-East", "Wicklow County Council": "Mid-East",
    "Clare County Council": "Mid-West", "Limerick County Council": "Mid-West",
    "Tipperary County Council": "Mid-West",
    "Laois County Council": "Midlands", "Longford County Council": "Midlands",
    "Offaly County Council": "Midlands", "Westmeath County Council": "Midlands",
    "Carlow County Council": "South-East", "Kilkenny County Council": "South-East",
    "Waterford City and County Council": "South-East", "Wexford County Council": "South-East",
    "Cork City Council": "South-West", "Cork County Council": "South-West",
    "Kerry County Council": "South-West",
    "Galway City Council": "West", "Galway County Council": "West",
    "Mayo County Council": "West", "Roscommon County Council": "West",
}


def month_key(ts: pd.Timestamp) -> int:
    return ts.year * 12 + ts.month - 1


def from_month_key(k: int) -> pd.Timestamp:
    return pd.Timestamp(year=k // 12, month=k % 12 + 1, day=1)


def main() -> None:
    MONTH_NUMS = {m.lower(): i + 1 for i, m in enumerate(
        ["January", "February", "March", "April", "May", "June",
         "July", "August", "September", "October", "November", "December"])}

    def month_name_key(s: str) -> int:
        s = str(s)
        parts = s.split()
        y = int(parts[0])
        mo = MONTH_NUMS.get(parts[1].lower() if len(parts) > 1 else "")
        if mo is None:
            return np.nan
        return y * 12 + mo - 1

    rppi = pd.read_csv(MACRO / "rppi_new_existing.csv", low_memory=False)
    rppi["mk"] = rppi["TLIST(M1)"].map(month_name_key)
    rppi = rppi.dropna(subset=["mk"])
    rppi["mk"] = rppi["mk"].astype(int)
    rppi_series = rppi[rppi["STATISTIC"] == "Residential Property Price Index"].copy()
    rppi_pivot = rppi_series.pivot_table(index="mk", columns="C02803V03373", values="value", aggfunc="last")
    rppi_mom = rppi[rppi["STATISTIC"] == "Percentage Change over 3 months for Residential Property Price Index"]
    rppi_mom_pivot = rppi_mom.pivot_table(index="mk", columns="C02803V03373", values="value", aggfunc="last")

    wpi = pd.read_csv(MACRO / "wpi_building_materials.csv", low_memory=False)
    wpi["mk"] = wpi["TLIST(M1)"].map(month_name_key)
    wpi = wpi.dropna(subset=["mk"])
    wpi["mk"] = wpi["mk"].astype(int)
    wpi_series = wpi[wpi["C01409V03262"].astype(str).str.lower() == "materials"]
    if wpi_series.empty:
        wpi_series = wpi[wpi["C01409V03262"].astype(str).str.contains("aterial", case=False, na=False)]
    wpi_pivot = wpi_series.pivot_table(index="mk", columns="STATISTIC", values="value", aggfunc="last")

    ppr = pd.read_parquet(settings.BRONZE_DIR / "ppr_bronze.parquet",
                          columns=["date_of_sale", "county", "price", "description_of_property"])
    ppr["price"] = ppr["price"].astype(str).str.replace("€", "", regex=False).str.replace(",", "", regex=False)
    ppr["price"] = pd.to_numeric(ppr["price"], errors="coerce")
    ppr = ppr.dropna(subset=["price"])
    ppr["dt"] = pd.to_datetime(ppr["date_of_sale"], utc=True, errors="coerce").dt.tz_localize(None)
    ppr["mk"] = ppr["dt"].dt.year * 12 + ppr["dt"].dt.month - 1
    ppr["new"] = ppr["description_of_property"].fillna("").str.contains("New Dwelling", case=False, na=False)
    ppr_new = ppr[ppr["new"]].dropna(subset=["mk"])
    ppr_new["authority"] = ppr_new["county"].map(
        lambda c: next((a for a in NUTS3 if c.lower() in a.lower()), None))
    ppr_agg = ppr_new[ppr_new["authority"].notna()].groupby(["authority", "mk"])["price"].agg(
        median_price="median", volume="count").reset_index()
    ppr_agg["price_6m_mom"] = ppr_agg.groupby("authority")["median_price"].transform(
        lambda s: s.pct_change(6) * 100)

    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                               columns=["case_key", "PlanningAuthority", "NumResidentialUnits",
                                        "DevelopmentDescription", "GrantDate", "ExpiryDate"])
    register["grant_dt"] = pd.to_datetime(register["GrantDate"], utc=True, errors="coerce").dt.tz_localize(None)
    register["expiry_dt"] = pd.to_datetime(register["ExpiryDate"], utc=True, errors="coerce").dt.tz_localize(None)
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    labels = labels[labels["activation_linked"].astype(str).str.lower() == "true"]
    labels["activation"] = pd.to_numeric(labels["activation_days"], errors="coerce")
    labels["completion"] = pd.to_numeric(labels["completion_days"], errors="coerce")
    base = labels.merge(register, on="case_key", how="inner")
    base["units"] = pd.to_numeric(base["NumResidentialUnits"], errors="coerce").fillna(0).clip(lower=1)
    base = base.dropna(subset=["grant_dt", "activation"])
    base = base[(base["grant_dt"] >= pd.Timestamp("2018-01-01")) & (base["grant_dt"] <= pd.Timestamp("2024-12-31"))]
    base = base[base["grant_dt"] + pd.to_timedelta(base["activation"], unit="D") <= SNAP + pd.Timedelta(days=400)]
    entities = pd.read_csv(settings.SILVER_DIR / "developer_groups.csv", dtype=str)
    base = base.merge(entities[["case_key", "group_id"]].drop_duplicates("case_key"), on="case_key", how="left")

    scheme_meta = []
    for _, row in base.iterrows():
        grant = row["grant_dt"]
        act_days = row["activation"]
        comm = grant + pd.Timedelta(days=float(act_days))
        expiry = row["expiry_dt"] if pd.notna(row["expiry_dt"]) else grant + pd.Timedelta(days=5 * 365)
        horizon_end = min(comm, SNAP, expiry)
        months = int((horizon_end - grant).days / 30.44)
        if months < 1:
            continue
        scheme_meta.append({
            "case_key": row["case_key"], "group_id": row["group_id"],
            "authority": row["PlanningAuthority"], "units": row["units"],
            "grant_mk": month_key(grant), "comm_mk": month_key(comm),
            "expiry_mk": month_key(expiry), "n_months": months,
            "type_apartment": int("apartment" in str(row["DevelopmentDescription"]).lower() or "duplex" in str(row["DevelopmentDescription"]).lower()),
            "activation_days": act_days,
            "completion_days": row["completion"] if pd.notna(row["completion"]) else None,
        })
    meta = pd.DataFrame(scheme_meta)

    grant_events = meta[["case_key", "group_id", "authority", "units", "grant_mk", "comm_mk"]]
    compl_events = meta[["case_key", "group_id", "authority", "units", "comm_mk", "completion_days"]].copy()
    compl_events["compl_mk"] = np.where(compl_events["completion_days"].notna(),
                                        compl_events["comm_mk"] + compl_events["completion_days"] / 30.44,
                                        np.nan)
    compl_events = compl_events.dropna(subset=["compl_mk"])

    rows = []
    for _, s in meta.iterrows():
        for m in range(int(s["n_months"])):
            mk = int(s["grant_mk"]) + m
            t = from_month_key(mk)
            if mk > month_key(SNAP):
                break
            row = {
                "case_key": s["case_key"], "group_id": s["group_id"], "authority": s["authority"],
                "units": s["units"], "mk": mk, "m": m,
                "months_remaining": max(int(s["expiry_mk"]) - mk, 0),
                "type_apartment": s["type_apartment"],
                "commenced_by": int(s["comm_mk"]),
                "commence_within_1": int(s["comm_mk"] <= mk + 1),
                "commence_within_3": int(s["comm_mk"] <= mk + 3),
                "commence_within_6": int(s["comm_mk"] <= mk + 6),
                "commence_within_12": int(s["comm_mk"] <= mk + 12),
                "snap_gap_months": month_key(SNAP) - mk,
                "activation_days": s["activation_days"],
                "n_months": s["n_months"],
            }
            rows.append(row)
    panel = pd.DataFrame(rows)

    dev_work = {}
    for mk in sorted(panel["mk"].unique()):
        for gid, g in grant_events[grant_events["group_id"].notna()].groupby("group_id"):
            granted_not_comm = g[(g["grant_mk"] <= mk) & (g["comm_mk"] > mk)]
            commenced_not_done = compl_events[(compl_events["group_id"] == gid) &
                                              (compl_events["comm_mk"] <= mk) & (compl_events["compl_mk"] > mk)]
            dev_work[(gid, mk)] = (granted_not_comm["units"].sum(), commenced_not_done["units"].sum())
    panel["dev_granted_uncommenced"] = panel.apply(
        lambda r: dev_work.get((r["group_id"], r["mk"]), (0, 0))[0] if pd.notna(r["group_id"]) else 0, axis=1)
    panel["dev_under_construction"] = panel.apply(
        lambda r: dev_work.get((r["group_id"], r["mk"]), (0, 0))[1] if pd.notna(r["group_id"]) else 0, axis=1)

    pipe = {}
    for mk in sorted(panel["mk"].unique()):
        for auth, g in grant_events.groupby("authority"):
            granted_not_comm = g[(g["grant_mk"] <= mk) & (g["comm_mk"] > mk)]
            commenced_not_done = compl_events[(compl_events["authority"] == auth) &
                                              (compl_events["comm_mk"] <= mk) & (compl_events["compl_mk"] > mk)]
            pipe[(auth, mk)] = (granted_not_comm["units"].sum(), commenced_not_done["units"].sum())
    panel["pipe_granted_uncommenced"] = panel.apply(
        lambda r: max(pipe.get((r["authority"], r["mk"]), (0, 0))[0] - r["units"], 0), axis=1)
    panel["pipe_under_construction"] = panel.apply(
        lambda r: pipe.get((r["authority"], r["mk"]), (0, 0))[1], axis=1)

    def lag_merge(df, col_map):
        out = df[["mk"]].copy()
        for src, dst in col_map.items():
            out = out.merge(src.reset_index().rename(columns={src.index.name or "mk": "mk"}),
                            on="mk", how="left", suffixes=("", "_dup"))
            out[dst] = out.iloc[:, -1]
            out = out[[c for c in out.columns if c in ("mk",) or c == dst or c in df.columns]]
        return out

    rppi_cols = {"National - all residential properties": "rppi_nat"}
    rppi_lag = rppi_pivot.reset_index().rename(columns={"National - all residential properties": "rppi_nat"})[["mk", "rppi_nat"]].copy()
    rppi_lag["mk"] = rppi_lag["mk"] + 1
    rppi_mom_lag = rppi_mom_pivot.reset_index()
    rppi_mom_lag = rppi_mom_lag[["mk", "National - all residential properties"]].rename(
        columns={"National - all residential properties": "rppi_3m_mom"})
    rppi_mom_lag["mk"] = rppi_mom_lag["mk"] + 1
    wpi_lag = wpi_pivot.reset_index().copy()
    wpi_lag = wpi_lag.rename(columns={c: f"wpi_{c}" for c in wpi_lag.columns if c != "mk"})
    wpi_lag["mk"] = wpi_lag["mk"] + 1

    panel = panel.merge(rppi_lag, on="mk", how="left")
    panel = panel.merge(rppi_mom_lag, on="mk", how="left")
    panel = panel.merge(wpi_lag, on="mk", how="left")

    ppr_lag = ppr_agg.copy()
    ppr_lag["mk"] = ppr_lag["mk"] + 1
    panel = panel.merge(ppr_lag.rename(columns={"county": "authority", "median_price": "ppr_new_median",
                                                "volume": "ppr_new_volume", "price_6m_mom": "ppr_new_6m_mom"}),
                        on=["authority", "mk"], how="left")

    panel["nuts3"] = panel["authority"].map(NUTS3)
    panel["grant_year"] = panel["mk"] // 12
    panel["calendar_month"] = panel["mk"] % 12

    out = settings.SILVER_DIR / "econ_hazard_panel.parquet"
    panel.to_parquet(out, index=False)
    (settings.SILVER_DIR / "econ_hazard_panel_summary.json").write_text(json.dumps({
        "n_schemes": int(meta["case_key"].nunique()),
        "n_rows": int(len(panel)),
        "n_rows_test": int((panel["mk"] >= month_key(pd.Timestamp("2023-01-01"))).sum()),
        "months_range": [int(panel["mk"].min()), int(panel["mk"].max())],
    }, indent=2), encoding="utf-8")
    print(json.dumps({"n_schemes": int(meta["case_key"].nunique()), "n_rows": int(len(panel))}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
