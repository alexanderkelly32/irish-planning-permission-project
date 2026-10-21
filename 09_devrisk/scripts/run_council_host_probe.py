"""Probe every planning authority for an iDocsWebDPSS host (one scheme each).

Uses the register's LinkAppDetails. Saves idocs/council_hosts.json:
{authority: host} for iDocs-capable councils.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scrapling import StealthyFetcher  # noqa: E402

from devrisk import settings  # noqa: E402

OUT = settings.SILVER_DIR / "idocs"
OUT.mkdir(parents=True, exist_ok=True)
HOSTS_PATH = OUT / "council_hosts.json"

fetcher = StealthyFetcher()


def main() -> None:
    hosts = {}
    if HOSTS_PATH.exists():
        hosts = json.loads(HOSTS_PATH.read_text(encoding="utf-8"))
    reg = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet",
                          columns=["PlanningAuthority", "LinkAppDetails", "GrantDate"])
    reg = reg[reg["LinkAppDetails"].notna()]
    for authority, group in reg.groupby("PlanningAuthority"):
        if authority in hosts:
            continue
        links = group["LinkAppDetails"].dropna().unique()[:2]
        found = None
        for link in links:
            if not isinstance(link, str) or not link.startswith("http"):
                continue
            try:
                page = fetcher.fetch(link, timeout=90000)
                m = re.search(r"https://([A-Za-z0-9.\-]+)/idocswebDPSS/copyright\.aspx\?catalog=planning&(?:amp;)?id=", page.html_content, re.I)
                if m:
                    found = m.group(1)
                    break
                m2 = re.search(r"([A-Za-z0-9.\-]+)/i[Dd]ocs[Ww]eb[^'\"]*id=\d+", page.html_content)
                if m2:
                    found = m2.group(1)
                    break
            except Exception:
                continue
        hosts[authority] = found
        print(authority, "->", found or "no idocs", flush=True)
        HOSTS_PATH.write_text(json.dumps(hosts, indent=2), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
