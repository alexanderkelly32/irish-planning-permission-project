"""Phase 1: discover each cohort scheme's iDocs host + app id (scrapling only)."""
from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scrapling import StealthyFetcher  # noqa: E402

from devrisk import settings  # noqa: E402

OUT = settings.SILVER_DIR / "idocs"
OUT.mkdir(parents=True, exist_ok=True)
HOSTS_PATH = OUT / "hosts.json"

fetcher = StealthyFetcher()


def main() -> None:
    hosts = {}
    if HOSTS_PATH.exists():
        hosts = json.loads(HOSTS_PATH.read_text(encoding="utf-8"))
    with zipfile.ZipFile(settings.SILVER_DIR / "audit_packs" / "PACK_24_residual_forensics.zip") as z:
        df = pd.read_csv(z.open("residual_forensics_cohort.csv"))
    for _, row in df.iterrows():
        key = row["case_key"]
        if key in hosts:
            continue
        link = row["LinkAppDetails"]
        if not isinstance(link, str) or not link.startswith("http"):
            hosts[key] = None
            print(key, "-> no link", flush=True)
            continue
        try:
            page = fetcher.fetch(link, timeout=90000)
            html = page.html_content
            m = re.search(r"https://([A-Za-z0-9.\-]+)/idocswebDPSS/copyright\.aspx\?catalog=planning&(?:amp;)?id=(\d+)", html, re.I)
            if m:
                hosts[key] = [m.group(1), m.group(2)]
                print(key, "->", m.group(1), m.group(2), flush=True)
            else:
                hosts[key] = None
                print(key, "-> no idocs host in page", flush=True)
        except Exception as exc:
            hosts[key] = None
            print(key, "-> error", str(exc)[:80], flush=True)
        HOSTS_PATH.write_text(json.dumps(hosts, indent=2), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
