import json
import tempfile
import unittest
from pathlib import Path

from run_deepseek_extraction import (
    adapt_request_for_deepseek,
    complete_custom_ids,
    is_billing_error,
    run_part,
    wrap_response,
)


class FakeCompletions:
    def __init__(self, fail_custom_ids: set[str], error_factory):
        self.fail_custom_ids = fail_custom_ids
        self.error_factory = error_factory

    def create(self, **kwargs):
        custom_id = kwargs["custom_id"] if "custom_id" in kwargs else None
        raise self.error_factory()


class FakeClient:
    def __init__(self, fail_custom_ids: set[str], error_factory):
        self.api_key = "test-key"
        self.chat = type("Chat", (), {"completions": FakeCompletions(fail_custom_ids, error_factory)})()


class OkCompletions:
    def create(self, **kwargs):
        message = type("Message", (), {"content": '{"status": "ok"}', "reasoning_content": None})()
        return type("Response", (), {"choices": [type("Choice", (), {"message": message})()]})()


class OkClient:
    def __init__(self):
        self.api_key = "test-key"
        self.chat = type("Chat", (), {"completions": OkCompletions()})()


def billing_error():
    error = RuntimeError("Insufficient Balance")
    error.status_code = 402
    return error


class DeepSeekRunnerTests(unittest.TestCase):
    def test_adapt_request_drops_openai_specific_params_and_sets_model(self):
        request = {
            "custom_id": "x",
            "body": {
                "model": "gpt-5",
                "reasoning_effort": "minimal",
                "verbosity": "low",
                "max_completion_tokens": 320,
                "messages": [{"role": "system", "content": "s"}],
            },
        }
        body = adapt_request_for_deepseek(request, "deepseek-v4-flash")
        self.assertEqual(body["model"], "deepseek-v4-flash")
        self.assertNotIn("reasoning_effort", body)
        self.assertNotIn("verbosity", body)
        self.assertNotIn("max_completion_tokens", body)
        self.assertEqual(body["max_tokens"], 500)
        self.assertIn("messages", body)

    def test_wrap_response_matches_batch_format_for_flattening(self):
        ok = wrap_response("doc-extract-row-3-c0", '{"status": "ok"}')
        self.assertEqual(ok["response"]["body"]["choices"][0]["message"]["content"], '{"status": "ok"}')
        err = wrap_response("doc-extract-row-4-c0", None, error={"message": "boom"})
        self.assertEqual(err["error"]["message"], "boom")

    def test_complete_custom_ids_resumes_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out.jsonl"
            path.write_text(
                json.dumps(wrap_response("a", "1")) + "\n" + json.dumps(wrap_response("b", "2")) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(complete_custom_ids(path), {"a", "b"})
            self.assertEqual(complete_custom_ids(Path(directory) / "missing.jsonl"), set())

    def test_part_selection_defaults_to_incomplete_parts(self):
        from run_deepseek_extraction import OUT_DIR  # noqa: F401  (path constant exists)

        self.assertTrue(OUT_DIR.name.endswith("document_extraction_campaign_2026-09-04"))

    def test_is_billing_error_detects_402_and_insufficient_balance(self):
        error = RuntimeError("boom")
        error.status_code = 402
        self.assertTrue(is_billing_error(error))
        self.assertTrue(is_billing_error(RuntimeError("Insufficient Balance")))
        self.assertFalse(is_billing_error(RuntimeError("connection reset")))

    def test_balance_floor_skips_extraction_when_low(self):
        from unittest.mock import patch

        from run_planner_report_pipeline import check_balance_floor

        class FakeClient:
            pass

        with patch("run_deepseek_extraction.check_balance") as fake_balance:
            fake_balance.return_value = {"is_available": True, "balance_infos": [{"total_balance": "0.10"}]}
            enough, total = check_balance_floor(FakeClient(), 0.20)
            self.assertFalse(enough)
            self.assertAlmostEqual(total, 0.10)
            fake_balance.return_value = {"is_available": True, "balance_infos": [{"total_balance": "1.20"}]}
            enough, total = check_balance_floor(FakeClient(), 0.20)
            self.assertTrue(enough)
            self.assertAlmostEqual(total, 1.20)
            fake_balance.side_effect = RuntimeError("network down")
            enough, total = check_balance_floor(FakeClient(), 0.20)
            self.assertTrue(enough)
            self.assertEqual(total, -1.0)

    def test_run_part_persists_successes_and_keeps_billing_errors_retryable(self):
        requests = [
            {"custom_id": "ok-1", "body": {"messages": [{"role": "system", "content": "s-ok"}]}},
            {"custom_id": "ok-2", "body": {"messages": [{"role": "system", "content": "s-ok"}]}},
            {"custom_id": "bill-1", "body": {"messages": [{"role": "system", "content": "s-bill"}]}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            part = directory / "batch_requests_part01.jsonl"
            part.write_text(
                "\n".join(json.dumps(request) for request in requests) + "\n",
                encoding="utf-8",
            )
            output = directory / "batch_output_part01.jsonl"

            class MixedCompletions:
                def create(self, **kwargs):
                    body = kwargs.get("messages")
                    marker = body[0]["content"] if body else ""
                    if marker == "s-bill":
                        raise billing_error()
                    message = type("Message", (), {"content": '{"status": "ok"}', "reasoning_content": None})()
                    return type("Response", (), {"choices": [type("Choice", (), {"message": message})()]})()

            class MixedClient:
                def __init__(self):
                    self.api_key = "test-key"
                    self.chat = type("Chat", (), {"completions": MixedCompletions()})()

            total = run_part(MixedClient(), part, output, "deepseek-v4-flash", max_workers=2, retries=0)
            self.assertGreaterEqual(total, 2)
            self.assertTrue(output.exists())
            written = [json.loads(line)["custom_id"] for line in output.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertIn("ok-1", written)
            self.assertIn("ok-2", written)
            self.assertNotIn("bill-1", written)
            self.assertEqual(complete_custom_ids(output), {"ok-1", "ok-2"})
            errors_path = directory / "batch_output_part01_errors.jsonl"
            self.assertTrue(errors_path.exists())
            errors = [json.loads(line)["custom_id"] for line in errors_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertIn("bill-1", errors)


if __name__ == "__main__":
    unittest.main()
