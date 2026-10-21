"""Runner: pull Social Housing Construction Status Reports (gov.ie PDFs).

Quarterly scheme-level reports (design/tender/on-site/complete stages, AHB
schemes). Downloads the latest PDFs to raw/shcsr/ with metadata sidecars;
parsing is a follow-up step once raw is in hand.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

OUT_DIR = settings.RAW_DIR / "shcsr"
USER_AGENT = "Mozilla/5.0 planning-risk-review/1.0 (local personal research)"
SEARCH_API = "https://www.gov.ie/api/gov-search/search?query={query}&page={page}"
KNOWN_TITLES = [
    "Social Housing Construction Status Report",
]


def fetch(url: str, timeout: int = 60):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = {"downloaded": [], "state_path": str(OUT_DIR)}
    state_path = OUT_DIR / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"urls": {}}

    for query in KNOWN_TITLES:
        for page in (0, 1):
            api_url = SEARCH_API.format(query=urllib.parse.quote(query), page=page)
            try:
                payload = json.loads(fetch(api_url).decode("utf-8"))
            except Exception as exc:
                report["error"] = f"search failed: {exc}"
                print(json.dumps(report, indent=2), flush=True)
                raise SystemExit(1)
            results = payload.get("results") or payload.get("hits") or []
            for item in results:
                title = str(item.get("title") or item.get("name") or "")
                href = str(item.get("url") or item.get("link") or "")
                if not href.lower().endswith(".pdf") or href in state["urls"]:
                    continue
                if "construction status report" not in title.lower() and "shcsr" not in title.lower():
                    continue
                content = fetch(href)
                name = re.sub(r"[^A-Za-z0-9._-]+", "_", title)[:80] + ".pdf"
                (OUT_DIR / name).write_bytes(content)
                state["urls"][href] = {"title": title, "bytes": len(content), "at": time.time()}
                report["downloaded"].append({"title": title, "bytes": len(content)})
                time.sleep(1.0)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    report["total_bytes"] = sum(f.stat().st_size for f in OUT_DIR.glob("*.pdf"))
    print(json.dumps(report, indent=2), flush=True)
