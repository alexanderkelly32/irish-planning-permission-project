"""Background orchestrator: waits for the eplanning scrape + CRO download,
then runs the dependent pipelines (applicant features -> timing v3; CRO
lookup -> entity resolution). Writes chain_done.json when finished.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devrisk import settings  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
STATE_PATH = settings.SILVER_DIR / "eplanning_scrape_state.json"
ZIP_PATH = settings.RAW_DIR / "companies.csv.zip"
DONE_PATH = settings.SILVER_DIR / "background_chain_done.json"


def wait_for(predicate, timeout_s: int, label: str) -> bool:
    start = time.time()
    while time.time() - start < timeout_s:
        if predicate():
            print(f"{label}: ready", flush=True)
            return True
        time.sleep(30)
    print(f"{label}: TIMEOUT", flush=True)
    return False


def run_script(name: str) -> None:
    print(f"running {name}...", flush=True)
    result = subprocess.run([sys.executable, "-u", "-X", "utf8", str(SCRIPTS / name)],
                            capture_output=True, text=True, encoding="utf-8", errors="ignore")
    print(result.stdout[-2000:] if result.stdout else result.stderr[-2000:], flush=True)


if __name__ == "__main__":
    report = {"started": time.time()}

    def scrape_done() -> bool:
        if not STATE_PATH.exists():
            return False
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if len(state.get("done", {})) < 50:
            return False
        time.sleep(60)  # re-check after a minute to confirm no further progress
        state2 = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return len(state2.get("done", {})) == len(state.get("done", {}))

    if wait_for(scrape_done, 4 * 3600, "eplanning scrape"):
        run_script("run_applicant_features.py")
        report["applicant_features"] = "done"
        run_script("run_applicant_timing_v3.py")
        report["applicant_timing_v3"] = "done"

    if wait_for(lambda: ZIP_PATH.exists() and ZIP_PATH.stat().st_size > 10_000_000, 4 * 3600, "cro download"):
        run_script("run_cro_entity_resolution.py")
        report["cro_resolution"] = "done"

    report["finished"] = time.time()
    DONE_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
