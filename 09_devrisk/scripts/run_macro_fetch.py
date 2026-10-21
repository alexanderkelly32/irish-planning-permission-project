"""Fetch free macro series for the economic-state hazard model.

- CSO RPPI monthly (national + NUTS3 regions + new/existing) via PxStat JSON-stat
- CSO Wholesale Price Index building materials via PxStat
- ECB MIR lending rates to NFCs via SDMX
Saves silver/macro/*.csv with [year, month, value...].
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

OUT = settings.SILVER_DIR / "macro"
OUT.mkdir(parents=True, exist_ok=True)


def fetch_json(url: str, retries: int = 2):
    for i in range(retries + 1):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0 research"})
            with urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            if i == retries:
                raise
            time.sleep(2)


def pxstat(table: str):
    url = f"https://ws.cso.ie/public/api.restful/PxStat.Data.Cube_API.ReadDataset/{table}/JSON-stat/2.0/en"
    return fetch_json(url)


def df_from_pxstat(table: str):
    data = pxstat(table)
    dims = data["id"]
    size = data["size"]
    labels = data["dimension"]
    values = data["value"]
    idx_names = [dims[i] for i in range(len(size))]
    # build index tuples
    import itertools
    combos = list(itertools.product(*[range(s) for s in size]))
    rows = []
    for combo in combos:
        row = {}
        flat = 0
        for i, c in enumerate(combo):
            row[dims[i]] = labels[dims[i]]["category"]["index"].get(str(c), c)
        if values is not None:
            flat = combo
        rows.append(row)
    df = pd.DataFrame(rows)
    flat_index = pd.MultiIndex.from_tuples([tuple(r) for r in rows[:0]], names=dims)
    return data, df


def pxstat_simple(table: str) -> pd.DataFrame:
    data = pxstat(table)
    dims = data["id"]
    labels = data["dimension"]
    values = data["value"]
    import itertools
    sizes = list(data["size"])
    strides = [1] * len(sizes)
    for i in range(len(sizes) - 2, -1, -1):
        strides[i] = strides[i + 1] * sizes[i + 1]
    combos = list(itertools.product(*[range(s) for s in sizes]))
    rows = []
    for combo in combos:
        flat = sum(combo[i] * strides[i] for i in range(len(combo)))
        row = {}
        for i in range(len(combo)):
            dim = labels[dims[i]]
            idx_list = dim["category"]["index"]
            lab_map = dim["category"].get("label", {})
            key = idx_list[combo[i]]
            row[dims[i]] = lab_map.get(key, key)
        row["value"] = values[flat]
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    report = {}
    for table, name in [("HPM01", "rppi_national"), ("HPM04", "rppi_nuts3"),
                        ("HPM09", "rppi_new_existing"), ("WPM28", "wpi_building_materials")]:
        try:
            df = pxstat_simple(table)
            df.to_csv(OUT / f"{name}.csv", index=False)
            report[name] = {"ok": True, "rows": int(len(df)), "columns": list(df.columns)[:8]}
            print(name, "ok", len(df), df.columns.tolist()[:8], flush=True)
        except Exception as exc:
            report[name] = {"ok": False, "error": str(exc)[:120]}
            print(name, "FAILED", str(exc)[:120], flush=True)

    for key, name in [("MIR.M.IE.B.A22.A.R.A.2240.EUR.N", "ecb_nfc_loan_rate"),
                      ("MIR.M.IE.B.A2A.A.R.A.2240.EUR.N", "ecb_sme_small_loan_rate")]:
        try:
            url = (f"https://sdw-wsrest.ecb.europa.eu/service/data/MIR/{key}"
                   f"?startPeriod=2018&format=jsondata")
            data = fetch_json(url)
            series = data["dataSets"][0]["series"]
            months = data["structure"]["dimensions"]["observation"][0]["values"]
            out_rows = []
            for sidx, obs in series.items():
                obs_vals = obs["observations"]
                for oidx, vals in obs_vals.items():
                    out_rows.append({"month": months[int(oidx)]["id"], "value": vals[0]})
            df = pd.DataFrame(out_rows).dropna()
            df = df[df["month"].str.contains("-")].copy()
            df.to_csv(OUT / f"{name}.csv", index=False)
            report[name] = {"ok": True, "rows": int(len(df))}
            print(name, "ok", len(df), flush=True)
        except Exception as exc:
            report[name] = {"ok": False, "error": str(exc)[:120]}
            print(name, "FAILED", str(exc)[:120], flush=True)
    (OUT / "fetch_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
