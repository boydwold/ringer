"""Focused regression tests for provider retry accounting and cancellation."""
import asyncio
import contextlib
import io
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import ringer


class RetryConfigTests(unittest.TestCase):
    def test_defaults_and_app_config_loading(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text("")
            self.assertEqual(ringer.AppConfig.load(path).retry, ringer.RetryConfig(3, 30, 300))
            path.write_text("[retry]\ninfra_max = 0\ninfra_base_delay_s = 0.25\ninfra_max_delay_s = 1\n")
            self.assertEqual(ringer.AppConfig.load(path).retry, ringer.RetryConfig(0, 0.25, 1))

    def test_invalid_config(self):
        for value in (False, [], "retry", 1):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "retry"):
                ringer.load_retry_config(value)
        for key, values in {
            "infra_max": [-1, 1.5, True, "3", None],
            "infra_base_delay_s": [-1, True, "30", None, float("nan"), float("inf")],
            "infra_max_delay_s": [-1, False, "300", None, float("nan"), float("inf")],
        }.items():
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, key):
                    ringer.load_retry_config({key: value})

    def test_family_survives_loading_and_parallel_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            data = {"run_name": "family", "workdir": tmp, "family": "audition",
                    "tasks": [{"key": "t", "spec": "Write an answer", "check": "test -s answer"}]}
            path.write_text(json.dumps(data))
            manifest = ringer.Manifest.from_path(path).with_max_parallel(3)
            self.assertEqual(manifest.family, "audition")
            self.assertEqual(manifest.source_path, path)
            for value in (None, [], {}, 1, "Work", ""):
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, "family"):
                    ringer.Manifest.from_obj(dict(data, family=value))


class RetryRunnerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        path = self.root / "config.toml"
        path.write_text(f'state_dir = "{self.root / "state"}"\n[eval]\nbackend = "jsonl"\n'
                        f'jsonl_path = "{self.root / "rows.jsonl"}"\n[artifact]\nenabled = false\n'
                        '[retry]\ninfra_base_delay_s = 0\ninfra_max_delay_s = 0\n')
        self.config = ringer.AppConfig.load(path)
        task = ringer.TaskSpec(key="t", spec="Write the correct answer to out.txt.",
                               check="test -s out.txt", expect_files=("out.txt",), max_attempts=2)
        self.manifest = ringer.Manifest("test", self.root / "work", 1, False, None, (task,))
        self.runner = ringer.RingerRunner(self.manifest, self.config, "test", dashboard_enabled=False)
        self.addCleanup(self.runner.logger.close)
        self.runtime = self.runner.runtimes[0]
        self.runner.state_writer.flush = Mock()
        self.runner._harvest_deliverables_on_pass = Mock()
        self.runner._cleanup_worktree_on_pass = AsyncMock()

    def rows(self):
        return [json.loads(line) for line in self.config.eval.jsonl_path.read_text().splitlines()]

    def attempts(self, outputs, *, passed=False):
        self.runner._run_worker = AsyncMock(side_effect=[
            ringer.WorkerResult(1, False, None, output_tail=output) for output in outputs
        ])
        results = [ringer.VerifyResult(False, 1, False, f"check {i}") for i in range(len(outputs))]
        if passed:
            results[-1] = ringer.VerifyResult(True, 0, False, "ok")
        self.runner.verifier.verify = AsyncMock(side_effect=results)

    async def test_backoff_caps_and_releases_slot(self):
        self.runner.config = replace(self.config, retry=ringer.RetryConfig(4, 2, 5))
        self.attempts(["ERROR: Selected model is at capacity."] * 5)
        waits = []

        async def sleep(delay):
            waits.append(delay)
            self.assertFalse(self.runner.semaphore.locked())
            self.assertEqual(self.runtime.status, "waiting_provider")
            self.assertEqual(self.runtime.wait_s, delay)
            self.assertIsNotNone(datetime.fromisoformat(self.runtime.wait_until).tzinfo)
            self.assertEqual(self.runtime.wait_reason, "rate_limited")

        with patch.object(ringer.asyncio, "sleep", sleep), contextlib.redirect_stdout(io.StringIO()):
            await self.runner._run_task(self.runtime)
        self.assertEqual(waits, [2, 4, 5, 5])
        self.assertEqual((self.runtime.attempts, self.runtime.model_attempts, self.runtime.infra_retries), (5, 0, 4))
        self.assertEqual(self.runtime.end_reason, "rate_limited")
        self.assertIsNone(self.runtime.wait_until)
        self.assertEqual(self.runner.semaphore._value, 1)
        self.assertTrue(all(row["model_attempt"] is None for row in self.rows()))

    async def test_zero_retries_stops_provider_failure(self):
        self.runner.config = replace(self.config, retry=ringer.RetryConfig(0, 0, 0))
        self.attempts(["ERROR: Reconnecting... 5/5"])
        await self.runner._run_task(self.runtime)
        self.assertEqual(self.runtime.end_reason, "provider_error")
        self.assertEqual(self.runtime.infra_retries, 0)
        self.assertEqual(len(self.rows()), 1)

    async def test_model_provider_model_keeps_retry_spec_after_wait(self):
        self.attempts(["model attempt output", "ERROR: Selected model is at capacity.", "done"], passed=True)
        with contextlib.redirect_stdout(io.StringIO()):
            await self.runner._run_task(self.runtime)
        specs = [call.args[1] for call in self.runner._run_worker.call_args_list]
        self.assertIn("model attempt output", specs[1])
        self.assertIn("check 0", specs[1])
        # The provider interrupted the model retry, so the rerun keeps its failure context.
        self.assertEqual(specs[2], specs[1])
        rows = self.rows()
        self.assertEqual([row["model_attempt"] for row in rows], [1, None, 2])
        self.assertEqual([row["retry"] for row in rows], [False, True, True])
        self.assertEqual(self.runtime.status, "pass")
        self.assertIsNone(self.runtime.end_reason)

    async def test_model_context_uses_only_latest_attempt(self):
        self.runtime.task = replace(self.runtime.task, max_attempts=3)
        self.attempts(["first model", "ERROR: Selected model is at capacity.", "last model", "done"], passed=True)
        self.runtime.log_path.parent.mkdir(parents=True)
        self.runtime.log_path.write_text("ERROR: Selected model is at capacity.\nold cumulative output")
        with contextlib.redirect_stdout(io.StringIO()):
            await self.runner._run_task(self.runtime)
        spec = self.runner._run_worker.call_args_list[-1].args[1]
        self.assertIn("last model", spec)
        self.assertIn("check 2", spec)
        for excluded in ("first model", "check 0", "capacity", "cumulative"):
            self.assertNotIn(excluded, spec)

    async def test_all_deterministic_classes_stop(self):
        for failure_class in ("quota_exhausted", "provider_policy", "sandbox_denied", "harness_error"):
            with self.subTest(failure_class=failure_class):
                runtime = ringer.TaskRuntime(self.runtime.task, self.runtime.taskdir, self.runtime.log_path)
                self.attempts(["deterministic failure"])
                with patch.object(ringer, "classify_failure", return_value=(failure_class, "evidence")):
                    await self.runner._run_task(runtime)
                self.assertEqual(runtime.attempts, 1)
                self.assertEqual(runtime.model_attempts, 0)
                self.assertEqual(runtime.end_reason, failure_class)
                self.assertEqual(runtime.final_verdict, "ERROR" if failure_class == "harness_error" else "FAIL")

    async def test_prepare_error_is_classified(self):
        self.runner._prepare_taskdir = AsyncMock(return_value=(False, "cannot create worktree"))
        await self.runner._run_task(self.runtime)
        row = self.rows()[0]
        self.assertEqual(row["failure_class"], "harness_error")
        self.assertIn("failure_class=harness_error", row["notes"])
        self.assertIsNone(row["model_attempt"])
        self.assertEqual(self.runtime.end_reason, "harness_error")

    async def test_cancel_wait_uses_normal_interruption_state(self):
        self.runner.config = replace(self.config, retry=ringer.RetryConfig(3, 60, 60))
        self.attempts(["ERROR: Selected model is at capacity."])
        waiting = asyncio.Event()
        self.runner.state_writer.start = Mock()
        self.runner.state_writer.stop = Mock()
        self.runner.state_writer.finish = Mock()
        self.runner.state_writer.flush = Mock(side_effect=waiting.set)
        with contextlib.redirect_stdout(io.StringIO()):
            task = asyncio.create_task(self.runner.run())
            await asyncio.wait_for(waiting.wait(), 2)
            self.assertEqual(self.runtime.status, "waiting_provider")
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2)
        self.assertEqual(self.runtime.status, "fail")
        self.assertEqual(self.runtime.final_verdict, "ERROR")
        self.assertIsNotNone(self.runtime.ended_at_monotonic)
        self.assertIsNone(self.runtime.wait_reason)
        self.assertIsNone(self.runtime.wait_until)
        self.assertEqual(self.runner.semaphore._value, 1)
        self.runner.state_writer.finish.assert_called_once()

    async def test_one_attempt_budget_still_waits_and_passes(self):
        self.runtime.task = replace(self.runtime.task, max_attempts=1)
        self.attempts(["ERROR: Selected model is at capacity.", "done"], passed=True)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            await self.runner._run_task(self.runtime)
        self.assertIn("waiting on the provider", stdout.getvalue())
        self.assertEqual(self.runtime.model_attempts, 1)
        self.assertEqual(self.runtime.status, "pass")

    async def test_steering_observations_include_both_counts(self):
        self.runner.config = replace(self.config, steering=ringer.SteeringConfig(dir=self.root / "steering"))
        self.attempts(["ERROR: Selected model is at capacity.", "done"], passed=True)
        with contextlib.redirect_stdout(io.StringIO()):
            await self.runner._run_task(self.runtime)
        rows = [json.loads(line) for path in (self.root / "steering/observations/ringer").glob("*.jsonl")
                for line in path.read_text().splitlines()]
        self.assertEqual([(row["attempt"], row["model_attempt"]) for row in rows], [(1, None), (2, 1)])

    def test_steering_omitted_accounting_differs_from_explicit_null(self):
        self.runner.config = replace(self.config, steering=ringer.SteeringConfig(dir=self.root / "steering"))
        self.runtime.attempts = 3
        for accounting in ({}, {"model_attempt": None}, {"model_attempt": 2}):
            self.runner._write_steering_observation(
                self.runtime,
                resolved_model="test-model",
                retrying=True,
                worker=ringer.WorkerResult(1, False, None),
                verify=ringer.VerifyResult(False, 1, False, "check failed"),
                verdict="FAIL",
                duration_ms=1,
                **accounting,
            )
        rows = [json.loads(line) for path in (self.root / "steering/observations/ringer").glob("*.jsonl")
                for line in path.read_text().splitlines()]
        self.assertNotIn("model_attempt", rows[0])
        self.assertIsNone(rows[1]["model_attempt"])
        self.assertEqual(rows[2]["model_attempt"], 2)
        self.assertEqual([row["attempt"] for row in rows], [3, 3, 3])
        self.assertEqual(set(rows[0]) | {"model_attempt"}, set(rows[1]))
        self.assertEqual(set(rows[1]), set(rows[2]))

    def test_timeout_with_passing_check_is_model_counted(self):
        worker = ringer.WorkerResult(0, True, None)
        verify = ringer.VerifyResult(True, 0, False, "ok")
        self.runner._log_attempt(self.runtime, "spec", False, worker, verify, "TIMEOUT", 1)
        self.assertEqual(self.rows()[0]["failure_class"], "model")
        self.assertEqual(self.rows()[0]["model_attempt"], 1)

    def test_summary_reports_total_model_and_infra_counts(self):
        self.runtime.attempts = 3
        self.runtime.model_attempts = 1
        self.runtime.infra_retries = 2
        self.runtime.status = "pass"
        self.runtime.final_verdict = "PASS"
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            ringer.print_summary("test", [self.runtime])
        self.assertIn("model attempts", stdout.getvalue())
        self.assertRegex(stdout.getvalue(), r"t\s+pass\s+PASS\s+3\s+1\s+")
        self.assertIn("(+2 infra retries)", stdout.getvalue())

    def test_evidence_is_sanitized_at_row_boundary(self):
        worker = ringer.WorkerResult(1, False, None)
        verify = ringer.VerifyResult(False, 1, False, "")
        for secret in ('headers: {"secret": "hidden"}', 'Set-Cookie: secret=hidden',
                       'responseHeaders": {"secret": "hidden"}', 'Authorization: Bearer hidden',
                       'Content-Type: hidden', '\nUnusual-Header: hidden'):
            with patch.object(ringer, "classify_failure", return_value=("provider_error", "API error\n  retry\tsoon " + secret)):
                self.runner._log_attempt(self.runtime, "spec", False, worker, verify, "FAIL", 1)
        for row in self.rows():
            self.assertEqual(row["failure_evidence"].rstrip('"'), "API error retry soon")
        self.assertEqual(len(ringer.failure_evidence_excerpt("x" * 400)), 300)


class WordingTests(unittest.TestCase):
    def test_old_states_keep_second_try_wording(self):
        event = ringer.plain_transition_event("t", "retrying", "pass", {"attempts": 2})
        self.assertIn("second try", event["line"])

    def test_waiting_provider_is_in_progress(self):
        self.assertEqual(ringer.task_state_bucket("waiting_provider"), "retry")
        self.assertIn("provider", ringer.task_state_word("waiting_provider"))


if __name__ == "__main__":
    unittest.main()
