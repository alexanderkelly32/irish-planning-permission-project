#!/usr/bin/env python3
"""Run extraction parts through the DeepSeek chat API (no batch endpoint).

Billing-safe behaviour:
- responses are appended to the output file as they complete, so a killed or
  budget-exhausted run keeps every response already paid for;
- error responses go to a sidecar `_errors.jsonl` file and are NOT counted as
  complete, so they are retried on the next resume;
- a billing error (HTTP 402 / "insufficient balance") stops new submissions and
  exits with a resumable summary.
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from openai_batch_utils import make_deepseek_client

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "02_development" / "current" / "document_extraction_campaign_2026-09-04"

DEEPSEEK_MODELS = {"deepseek-v4-flash", "deepseek-v4-pro"}


def adapt_request_for_deepseek(request: dict, model: str) -> dict:
    """Convert an OpenAI batch request body to a DeepSeek chat request body."""
    body = dict(request.get("body") or {})
    body["model"] = model
    body.pop("reasoning_effort", None)
    body.pop("verbosity", None)
    body.pop("max_completion_tokens", None)
    body.setdefault("max_tokens", 500)
    return body


def complete_custom_ids(output_path: Path) -> set[str]:
    if not output_path.exists():
        return set()
    completed: set[str] = set()
    for line in output_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            completed.add(json.loads(line)["custom_id"])
        except (json.JSONDecodeError, KeyError):
            continue
    return completed


def wrap_response(custom_id: str, content: str | None, error: dict | None = None) -> dict:
    if error is not None:
        return {"custom_id": custom_id, "error": error}
    return {
        "custom_id": custom_id,
        "response": {"body": {"choices": [{"message": {"content": content}}]}},
    }


def is_billing_error(exc: Exception) -> bool:
    """True when the API refused to serve the request for billing reasons."""
    status = getattr(exc, "status_code", None)
    if status == 402:
        return True
    message = str(exc).lower()
    return "insufficient" in message or "balance" in message or "not enough money" in message


def check_balance(client) -> dict:
    """Read the DeepSeek account balance endpoint (informational only)."""
    import httpx

    key = client.api_key
    response = httpx.get("https://api.deepseek.com/user/balance", headers={
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }, timeout=30)
    response.raise_for_status()
    return response.json()


def _call_with_retries(client, request: dict, model: str, retries: int, stop_event: threading.Event) -> dict:
    custom_id = request["custom_id"]
    body = adapt_request_for_deepseek(request, model)
    messages = body["messages"]
    max_tokens = body.pop("max_tokens")
    attempt = 0
    while True:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                timeout=180,
                response_format={"type": "json_object"},
                extra_body={"thinking": {"type": "disabled"}},
            )
            message = response.choices[0].message
            content = message.content
            if not content:
                content = getattr(message, "reasoning_content", None)
            if not content:
                content = ""
            return wrap_response(custom_id, content)
        except Exception as exc:
            if is_billing_error(exc):
                stop_event.set()
                return wrap_response(custom_id, None, error={"message": str(exc), "kind": "billing"})
            attempt += 1
            if attempt > retries or stop_event.is_set():
                return wrap_response(custom_id, None, error={"message": str(exc), "kind": "transient"})
            time.sleep(min(2 ** attempt, 60))


def run_part(client, part_file: Path, output_file: Path, model: str, max_workers: int = 12, retries: int = 6) -> int:
    requests = [
        json.loads(line)
        for line in part_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    completed = complete_custom_ids(output_file)
    pending = [request for request in requests if request["custom_id"] not in completed]
    if not pending:
        print(f"{part_file.name}: already complete ({len(requests)} responses)", flush=True)
        return len(requests)
    print(f"{part_file.name}: {len(pending)} pending of {len(requests)}", flush=True)

    error_file = part_file.parent / (output_file.stem + "_errors.jsonl")
    write_lock = threading.Lock()
    stop_event = threading.Event()
    deferred: list[dict] = []
    finished = 0
    errors = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures: dict = {}
        for request in pending:
            if stop_event.is_set():
                deferred.append(request)
                continue
            futures[executor.submit(_call_with_retries, client, request, model, retries, stop_event)] = request["custom_id"]
        for future in as_completed(futures):
            custom_id = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = wrap_response(custom_id, None, error={"message": str(exc), "kind": "transient"})
            with write_lock:
                if result.get("error") is None:
                    with output_file.open("a", encoding="utf-8", newline="\n") as handle:
                        handle.write(json.dumps(result, ensure_ascii=True) + "\n")
                    finished += 1
                else:
                    with error_file.open("a", encoding="utf-8", newline="\n") as handle:
                        handle.write(json.dumps(result, ensure_ascii=True) + "\n")
                    errors += 1
                    if result["error"].get("kind") == "billing":
                        stop_event.set()

    print(
        f"{part_file.name}: wrote {finished} new responses, {errors} errors, "
        f"{len(deferred)} deferred (billing stop) - resume-safe.",
        flush=True,
    )
    return len(completed) + finished


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parts", type=str, default=None, help="comma-separated part numbers, e.g. 9,10,11")
    parser.add_argument("--model", default="deepseek-v4-flash", choices=sorted(DEEPSEEK_MODELS))
    parser.add_argument("--max-workers", type=int, default=12)
    parser.add_argument("--out-dir", type=Path, default=None, help="override the campaign output directory")
    parser.add_argument("--check-balance", action="store_true", help="print the DeepSeek account balance and exit")
    args = parser.parse_args()

    client = make_deepseek_client()
    if args.check_balance:
        try:
            print(json.dumps(check_balance(client), indent=2))
        except Exception as exc:
            print(f"balance check failed: {exc}")
        return

    out_dir = args.out_dir or OUT_DIR
    if args.parts:
        part_numbers = [int(part) for part in args.parts.split(",") if part.strip()]
    else:
        part_numbers = []
        for part_file in sorted(out_dir.glob("batch_requests_part*.jsonl")):
            number = int(part_file.stem.rsplit("part", 1)[1])
            output = out_dir / f"batch_output_part{number:02d}.jsonl"
            if not output.exists() or len(complete_custom_ids(output)) < sum(1 for line in part_file.read_text(encoding="utf-8").splitlines() if line.strip()):
                part_numbers.append(number)
    if not part_numbers:
        print("all parts complete")
        return

    total = 0
    for number in part_numbers:
        part_file = out_dir / f"batch_requests_part{number:02d}.jsonl"
        output_file = out_dir / f"batch_output_part{number:02d}.jsonl"
        total += run_part(client, part_file, output_file, args.model, max_workers=args.max_workers)
    print(json.dumps({"parts_processed": part_numbers, "responses_total": total}))


if __name__ == "__main__":
    main()
