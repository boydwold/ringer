from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import ringer


CAPACITY = "ERROR: Selected model is at capacity. Please try again."


def opencode_error(name="APIError", message="unavailable", status=None, **extra):
    data = {"message": message, **extra}
    if status is not None:
        data["statusCode"] = status
    return json.dumps({"type": "error", "error": {"name": name, "data": data}})


class FailureConfigTests(unittest.TestCase):
    def engine(self, **section):
        return ringer.load_engines({"custom": {"args_template": ["{spec}"], **section}})["custom"]

    def test_builtin_profile_without_config(self):
        self.assertEqual(ringer.load_engines(None)["codex"].failure_profile, "codex")

    def test_invalid_profiles(self):
        for profile in ("invalid", "CODEX", "", None, [], {}):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                self.engine(failure_profile=profile)

    def test_invalid_pattern_tables(self):
        for patterns in (None, [], "rate_limited", 42):
            with self.subTest(patterns=patterns), self.assertRaises(ValueError):
                self.engine(failure_patterns=patterns)

    def test_patterns_require_lists_of_strings(self):
        for patterns in (None, "x", ("x",), [1], ["x", None]):
            with self.subTest(patterns=patterns), self.assertRaises(ValueError):
                self.engine(failure_patterns={"model": patterns})

    def test_patterns_are_immutable_and_detached_from_input(self):
        patterns = {"provider_error": ["first", "second"], "model": []}
        engine = self.engine(failure_patterns=patterns)
        patterns["provider_error"].append("third")
        self.assertEqual(engine.failure_patterns, (("provider_error", ("first", "second")), ("model", ())))
        self.assertIsInstance(hash(engine), int)

    def test_vocabulary(self):
        self.assertEqual(ringer.FAILURE_CLASSES, {
            "model", "rate_limited", "provider_error", "quota_exhausted",
            "provider_policy", "sandbox_denied", "harness_error",
        })
        self.assertEqual(ringer.INFRA_TRANSIENT_CLASSES, {"rate_limited", "provider_error"})


class FailureClassificationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.taskdir = self.root / "task"
        self.taskdir.mkdir()
        self.task = ringer.TaskSpec("task", "spec", "false", expect_files=("report.md",))
        self.manifest = ringer.Manifest("run", self.root, 1, False, None, (self.task,))
        self.engine = ringer.load_engines(None)["codex"]

    def classify(self, output="", *, missing=(), ok=False, error=None, check_timeout=False):
        worker = ringer.WorkerResult(1, False, None, error=error, output_tail=output)
        verify = ringer.VerifyResult(ok, 1, check_timeout, "", tuple(missing))
        return ringer.classify_failure(worker, verify, self.task, self.engine, self.manifest, self.taskdir)

    def opencode(self):
        self.engine = replace(self.engine, failure_profile="opencode", sandbox_args=())

    def test_output_defaults_empty(self):
        self.assertEqual(ringer.WorkerResult(1, False, None).output_tail, "")

    def test_explicit_none_disables_builtin_markers(self):
        self.engine = replace(self.engine, failure_profile="none")
        self.assertEqual(self.classify(CAPACITY), ("model", ""))

    def test_custom_rules_search_whole_lines_and_ignore_harness(self):
        self.engine = replace(self.engine, failure_profile="none", failure_patterns=(
            ("quota_exhausted", (r"^CUSTOM: credits$",)),
        ))
        for output in ("prefix CUSTOM: credits", "CUSTOM:\ncredits", "[ringer.py] CUSTOM: credits"):
            with self.subTest(output=output):
                self.assertEqual(self.classify(output), ("model", ""))
        self.assertEqual(self.classify("CUSTOM: credits"), ("quota_exhausted", "CUSTOM: credits"))

    def test_custom_rules_obey_decisiveness(self):
        self.engine = replace(self.engine, failure_patterns=(("provider_policy", ("capacity",)),))
        self.task = replace(self.task, expect_files=())
        self.assertEqual(self.classify(CAPACITY)[0], "provider_policy")
        cls, evidence = self.classify(CAPACITY + "\nrecovered")
        self.assertEqual(cls, "model")
        self.assertTrue(evidence.startswith("non-decisive marker: "))

    def test_config_model_override_wins(self):
        self.engine = replace(self.engine, failure_patterns=(("model", ("capacity",)),))
        self.assertEqual(self.classify(CAPACITY)[0], "model")

    def test_error_and_sandbox_precedence(self):
        outside = str(self.root / "outside.md")
        self.task = replace(self.task, expect_files=(outside,))
        self.assertEqual(self.classify(CAPACITY, missing=(outside,), error="spawn failed"), ("harness_error", "spawn failed"))
        self.assertEqual(self.classify("[ringer-sandbox] failed\n" + CAPACITY, missing=(outside,))[0], "harness_error")
        self.assertEqual(self.classify(CAPACITY, missing=(outside,))[0], "sandbox_denied")

    def test_passing_verify_ignores_markers_but_not_worker_error(self):
        self.assertEqual(self.classify("[ringer-sandbox] failed\n" + CAPACITY, ok=True), (None, ""))
        self.assertEqual(self.classify(ok=True, error="spawn failed"), ("harness_error", "spawn failed"))

    def test_tilde_missing_path_and_writable_root_evidence(self):
        outside = "~/ringer-failure-class-unit-missing/report.md"
        cls, evidence = self.classify(missing=(outside,))
        self.assertEqual(cls, "sandbox_denied")
        self.assertIn(outside, evidence)
        self.assertIn(str(self.taskdir), evidence)

    def test_tilde_is_expanded_when_checking_deliverable_existence(self):
        self.task = replace(self.task, expect_files=("~",))
        self.assertEqual(self.classify(CAPACITY + "\nrecovered")[0], "model")

    def test_relative_escape_is_never_sandbox_denied(self):
        self.assertEqual(self.classify(missing=("../outside.md",)), ("model", ""))

    def test_absolute_path_inside_root_is_not_sandbox_denied(self):
        self.assertEqual(self.classify(missing=(str(self.taskdir / "report.md"),)), ("model", ""))

    def test_worktree_and_unreadable_check_exemptions(self):
        outside = str(self.root / "outside.md")
        self.manifest = replace(self.manifest, worktrees=True)
        self.assertEqual(self.classify(missing=(outside,)), ("model", ""))
        self.manifest = replace(self.manifest, worktrees=False)
        self.task = replace(self.task, check=f"python3 {self.root / 'missing.py'}")
        self.assertEqual(self.classify(missing=(outside,)), ("model", ""))

    def test_any_existing_deliverable_prevents_early_marker_deciding(self):
        (self.taskdir / "report.md").touch()
        self.task = replace(self.task, expect_files=("report.md", "missing.md"))
        self.assertEqual(self.classify(CAPACITY + "\nrecovered")[0], "model")

    def test_absolute_deliverable_existence(self):
        output = self.root / "absolute.md"
        output.touch()
        self.task = replace(self.task, expect_files=(str(output),))
        self.assertEqual(self.classify(CAPACITY + "\nrecovered")[0], "model")

    def test_no_expected_files_requires_final_marker(self):
        self.task = replace(self.task, expect_files=())
        self.assertEqual(self.classify(CAPACITY + "\nrecovered")[0], "model")
        self.assertEqual(self.classify(CAPACITY + "\n \n[ringer.py] done")[0], "rate_limited")

    def test_last_decisive_marker_wins(self):
        self.assertEqual(self.classify(CAPACITY + "\nERROR: Reconnecting... 5/5")[0], "provider_error")

    def test_intermediate_reconnect_never_decides_provider_failure(self):
        self.assertEqual(self.classify("ERROR: Reconnecting... 2/5"), ("model", ""))
        cls, evidence = self.classify("ERROR: Reconnecting... 2/5\nrecovered")
        self.assertEqual(cls, "model")
        self.assertIn("Reconnecting", evidence)

    def test_opencode_non_json_and_non_error_events_are_not_markers(self):
        self.opencode()
        for line in ("APIError 429: rate limited", CAPACITY, "{bad json", "[]", "null", '"error"',
                     json.dumps({"type": "text", "error": {"name": "APIError"}}),
                     json.dumps({"type": "error", "error": None})):
            with self.subTest(line=line):
                self.assertEqual(self.classify(line), ("model", ""))

    def test_opencode_last_event_ignores_non_json_trailer(self):
        self.opencode()
        self.task = replace(self.task, expect_files=())
        self.assertEqual(self.classify(opencode_error() + "\nplain trailer")[0], "provider_error")
        self.assertEqual(self.classify(opencode_error() + '\n{"type":"step_finish"}')[0], "model")

    def test_opencode_additional_error_mappings(self):
        self.opencode()
        cases = [
            ("APIError", 402, "payment required", "quota_exhausted"),
            ("APIError", 400, "No CREDITS remain", "quota_exhausted"),
            ("APIError", 404, "missing endpoint", "provider_error"),
            ("OtherError", None, "unexpected", "provider_error"),
            ("UnknownError", 429, "credits", "provider_error"),
        ]
        for name, status, message, expected in cases:
            with self.subTest(name=name, status=status, message=message):
                self.assertEqual(self.classify(opencode_error(name, message, status))[0], expected)

    def test_opencode_missing_message_never_leaks_metadata(self):
        self.opencode()
        event = {"type": "error", "error": {"name": "APIError", "data": {
            "statusCode": 503, "responseBody": "SECRET", "responseHeaders": {"set-cookie": "SECRET"},
        }}}
        self.assertEqual(self.classify(json.dumps(event)), ("provider_error", "APIError 503"))

    def test_opencode_override_retains_safe_evidence(self):
        self.opencode()
        self.engine = replace(self.engine, failure_patterns=(("quota_exhausted", ("APIError",)),))
        cls, evidence = self.classify(opencode_error(status=503, responseBody="SECRET"))
        self.assertEqual(cls, "quota_exhausted")
        self.assertEqual(evidence, "APIError 503: unavailable")

    def test_evidence_is_truncated_to_300(self):
        long = "x" * 500
        for result in (self.classify(error=long), self.classify("[ringer-sandbox] " + long),
                       self.classify(CAPACITY + long)):
            self.assertEqual(len(result[1]), 300)
        self.task = replace(self.task, expect_files=())
        self.assertEqual(len(self.classify(CAPACITY + long + "\nrecovered")[1]), 300)
        self.opencode()
        self.assertEqual(len(self.classify(opencode_error(message=long))[1]), 300)


class WorkerCaptureTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_attempt_returns_only_its_captured_output(self):
        with tempfile.TemporaryDirectory() as directory:
            taskdir = Path(directory)
            engine = ringer.EngineConfig(
                "custom", sys.executable,
                ("-c", "import sys; print(sys.argv[1])", "{spec}"), (), (),
            )
            runner = ringer.RingerRunner.__new__(ringer.RingerRunner)
            runner.config = SimpleNamespace(engines={"custom": engine}, steering=SimpleNamespace(dir=None))
            runner.lock = threading.Lock()
            runner.active_processes = {}
            task = ringer.TaskSpec("task", "spec", "false", engine="custom")
            runtime = ringer.TaskRuntime(task, taskdir, taskdir / "worker.log")
            for attempt, text in enumerate(("first attempt", "second attempt"), 1):
                result = await runner._run_worker(runtime, text, attempt)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.output_tail, text + "\n")
            log = runtime.log_path.read_text()
            self.assertIn("first attempt", log)
            self.assertIn("second attempt", log)


if __name__ == "__main__":
    unittest.main()


class WrapperSandboxedEngineTests(unittest.TestCase):
    """An engine whose wrapper sandboxes by default (empty sandbox_args, a
    full_access switch) still yields sandbox_denied for an escaping path."""

    def test_opencode_wrapper_engine_is_sandboxed(self):
        engine = ringer.load_engines({"opencode": {"bin": "x", "args_template": ["{taskdir}", "{access_args}", "{spec}"],
                                            "sandbox_args": [], "full_access_args": ["--no-sandbox"]}})["opencode"]
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            (workdir / "t1").mkdir()
            outside = "/tmp/ringer-wrapper-not-here/report.md"
            task = ringer.TaskSpec(key="t1", spec="x" * 80, check="test -s report.md", engine="opencode", expect_files=(outside,))
            manifest = ringer.Manifest(run_name="r", workdir=workdir, max_parallel=1, worktrees=False, repo=None, tasks=(task,))
            worker = ringer.WorkerResult(returncode=1, timed_out=False, tokens=None, output_tail="")
            verify = ringer.VerifyResult(ok=False, check_returncode=1, check_timed_out=False, raw_output_excerpt="", missing_files=(outside,))
            cls, _ = ringer.classify_failure(worker, verify, task, engine, manifest, workdir / "t1")
            self.assertEqual(cls, "sandbox_denied")


class SandboxMarkerPositionTests(unittest.TestCase):
    """A [ringer-sandbox] line inside the engine's own output is tool output."""

    def _case(self, output):
        engine = ringer.load_engines({"codex": {"bin": "codex", "args_template": ["exec", "{spec}"]}})["codex"]
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            (workdir / "t1").mkdir()
            task = ringer.TaskSpec(key="t1", spec="x" * 80, check="test -s notes.md", engine="codex", expect_files=("notes.md",))
            manifest = ringer.Manifest(run_name="r", workdir=workdir, max_parallel=1, worktrees=False, repo=None, tasks=(task,))
            worker = ringer.WorkerResult(returncode=0, timed_out=False, tokens=None, output_tail=output)
            verify = ringer.VerifyResult(ok=False, check_returncode=1, check_timed_out=False, raw_output_excerpt="FAIL", missing_files=())
            return ringer.classify_failure(worker, verify, task, engine, manifest, workdir / "t1")

    def test_marker_after_engine_output_is_model(self):
        out = "[ringer.py] attempt 1 started\nOpenAI Codex v0.x\nmodel: gpt-6-astra\n[ringer-sandbox] bwrap check sandbox setup failed\n"
        self.assertEqual(self._case(out)[0], "model")

    def test_marker_first_is_harness_error(self):
        out = "[ringer.py] attempt 1 started\n[ringer-sandbox] bwrap not found\n"
        self.assertEqual(self._case(out)[0], "harness_error")
