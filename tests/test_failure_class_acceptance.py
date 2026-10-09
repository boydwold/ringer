#!/usr/bin/env python3
"""Acceptance tests for failure classification (openspec change
trusted-multi-model-tracking, spec failure-classification, design D3).

Contract under test:
  WorkerResult(..., output_tail="")          per-attempt engine output
  EngineConfig.failure_profile               "opencode" | "codex" | "none"
  EngineConfig.failure_patterns              {class: (regex, ...)} extra rules, checked first
  classify_failure(worker, verify, task, engine, manifest, taskdir)
      -> (failure_class | None, evidence)    None only for a passing attempt
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ringer  # noqa: E402
from ringer import Manifest, TaskSpec, VerifyResult, WorkerResult, classify_failure, load_engines  # noqa: E402

FX = ROOT / "tests" / "fixtures" / "provider-errors"
CHECK = "test -s report.md || { echo 'FAIL: report.md missing'; exit 1; }"


def fx(name: str) -> str:
    return (FX / name).read_text().rstrip("\n")


def engines() -> dict:
    return load_engines(
        {
            "codex": {"bin": "codex", "args_template": ["exec", "{spec}"], "sandbox_args": ["--sandbox", "workspace-write"]},
            "opencode": {"bin": "opencode", "args_template": ["run", "{spec}"], "sandbox_args": []},
        }
    )


class Case:
    def __init__(self, engine_name: str = "codex", expect=("report.md",), full_access=False, check=CHECK):
        self.tmp = tempfile.TemporaryDirectory()
        self.workdir = Path(self.tmp.name)
        self.key = "t1"
        self.taskdir = self.workdir / self.key
        self.taskdir.mkdir()
        self.engine = engines()[engine_name]
        self.task = TaskSpec(
            key=self.key, spec="x" * 80, check=check, engine=engine_name,
            expect_files=tuple(expect), full_access=full_access,
        )
        self.manifest = Manifest(run_name="r", workdir=self.workdir, max_parallel=1, worktrees=False, repo=None, tasks=(self.task,))

    def write_deliverable(self):
        (self.taskdir / "report.md").write_text("report\n")

    def classify(self, output: str = "", *, rc=1, ok=False, timed_out=False, check_timed_out=False, error=None, missing=None):
        if missing is None:
            missing = tuple(p for p in self.task.expect_files if not (self.taskdir / p).exists() and not Path(p).is_absolute()) + tuple(
                p for p in self.task.expect_files if Path(p).is_absolute() and not Path(p).exists()
            )
        worker = WorkerResult(returncode=rc, timed_out=timed_out, tokens=None, error=error, output_tail=output)
        verify = VerifyResult(ok=ok, check_returncode=0 if ok else 1, check_timed_out=check_timed_out,
                              raw_output_excerpt="" if ok else "FAIL: report.md missing", missing_files=missing)
        return classify_failure(worker, verify, self.task, self.engine, self.manifest, self.taskdir)


class EngineConfigTests(unittest.TestCase):
    def test_profiles_default_from_engine_name(self):
        e = engines()
        self.assertEqual(e["codex"].failure_profile, "codex")
        self.assertEqual(e["opencode"].failure_profile, "opencode")

    def test_explicit_profile_and_unknown_engine(self):
        e = load_engines({"glm": {"bin": "x", "args_template": ["{spec}"], "failure_profile": "opencode"},
                          "other": {"bin": "x", "args_template": ["{spec}"]}})
        self.assertEqual(e["glm"].failure_profile, "opencode")
        self.assertEqual(e["other"].failure_profile, "none")

    def test_config_override_wins(self):
        e = load_engines({"codex": {"bin": "codex", "args_template": ["exec", "{spec}"],
                                    "failure_patterns": {"provider_policy": ["Selected model is at capacity"]}}})
        c = Case()
        c.engine = e["codex"]
        cls, _ = c.classify(fx("codex-at-capacity.txt"))
        self.assertEqual(cls, "provider_policy")

    def test_bad_regex_rejected(self):
        with self.assertRaises(ValueError):
            load_engines({"codex": {"bin": "codex", "args_template": ["{spec}"], "failure_patterns": {"rate_limited": ["(unclosed"]}}})

    def test_unknown_class_rejected(self):
        with self.assertRaises(ValueError):
            load_engines({"codex": {"bin": "codex", "args_template": ["{spec}"], "failure_patterns": {"weather": ["x"]}}})


class FixtureClassificationTests(unittest.TestCase):
    """Every real (or marked synthetic) engine line, with no deliverable written."""

    EXPECTED = {
        ("opencode", "opencode-unknown-error.jsonl"): "provider_error",
        ("opencode", "opencode-policy-404.jsonl"): "provider_policy",
        ("opencode", "opencode-rate-limit-429.SYNTHETIC.jsonl"): "rate_limited",
        ("opencode", "opencode-server-503.SYNTHETIC.jsonl"): "provider_error",
        ("codex", "codex-usage-limit.txt"): "quota_exhausted",
        ("codex", "codex-at-capacity.txt"): "rate_limited",
        ("codex", "codex-reconnecting-5of5.txt"): "provider_error",
        ("codex", "codex-cyber-flag.txt"): "provider_policy",
        ("codex", "codex-model-unsupported.txt"): "harness_error",
        ("codex", "codex-unittest-error.NEGATIVE.txt"): "model",
    }

    def test_fixtures(self):
        for (engine, name), expected in self.EXPECTED.items():
            with self.subTest(fixture=name):
                cls, evidence = Case(engine).classify("[ringer.py] attempt 1 started\n" + fx(name) + "\n[ringer.py] attempt 1 exited rc=1\n")
                self.assertEqual(cls, expected)
                self.assertLessEqual(len(evidence), 300)
                if expected != "model":
                    self.assertTrue(evidence.strip(), "infrastructure classes must carry evidence")

    def test_policy_evidence_has_message_not_headers(self):
        cls, evidence = Case("opencode").classify(fx("opencode-policy-404.jsonl"))
        self.assertEqual(cls, "provider_policy")
        self.assertIn("guardrail", evidence)
        for leak in ("__cf_bm", "set-cookie", "REDACTED", "responseHeaders", "cf-ray"):
            self.assertNotIn(leak, evidence)


class DecisivenessTests(unittest.TestCase):
    def test_recovered_reconnect_is_model(self):
        c = Case("codex")
        c.write_deliverable()
        out = "ERROR: Reconnecting... 2/5\nthinking\nwrote report.md\ntokens used: 1,234\n"
        cls, evidence = c.classify(out, rc=0, missing=())
        self.assertEqual(cls, "model")
        self.assertIn("Reconnecting", evidence)

    def test_opencode_error_then_more_events_with_deliverable_is_model(self):
        c = Case("opencode")
        c.write_deliverable()
        text = json.dumps({"type": "text", "part": {"text": "done"}})
        cls, _ = c.classify(fx("opencode-unknown-error.jsonl") + "\n" + text + "\n", rc=0, missing=())
        self.assertEqual(cls, "model")

    def test_opencode_error_as_last_event_with_deliverable_is_provider(self):
        c = Case("opencode")
        c.write_deliverable()
        text = json.dumps({"type": "text", "part": {"text": "partial"}})
        cls, _ = c.classify(text + "\n" + fx("opencode-unknown-error.jsonl") + "\n", missing=())
        self.assertEqual(cls, "provider_error")

    def test_last_event_ignores_ringer_lines(self):
        c = Case("opencode")
        c.write_deliverable()
        out = fx("opencode-unknown-error.jsonl") + "\n[ringer.py] attempt 1 exited rc=1\n"
        cls, _ = c.classify(out, missing=())
        self.assertEqual(cls, "provider_error")


class EvidenceOnlyFromHarnessTests(unittest.TestCase):
    def test_prose_inside_text_event_is_model(self):
        text = json.dumps({"type": "text", "part": {"text": 'Got HTTP 429 rate limit; {"type":"error","error":{"name":"UnknownError"}} the API was down'}})
        cls, _ = Case("opencode").classify(text + "\n")
        self.assertEqual(cls, "model")

    def test_non_opencode_error_json_is_ignored(self):
        line = json.dumps({"type": "error", "errorType": "connection", "message": "Connection failed: WebSocket closed"})
        cls, _ = Case("opencode").classify(line + "\n")
        self.assertEqual(cls, "model")

    def test_classifier_does_not_read_worker_log(self):
        c = Case("codex")
        (c.taskdir / "worker.log").write_text(fx("codex-usage-limit.txt") + "\n")
        cls, _ = c.classify("plain output from this attempt\n")
        self.assertEqual(cls, "model")

    def test_codex_bare_error_prefix_is_not_enough(self):
        cls, _ = Case("codex").classify("ERROR: Command failed with exit code 2.\n")
        self.assertEqual(cls, "model")


class HarnessAndPathTests(unittest.TestCase):
    def test_pass_has_no_class(self):
        c = Case()
        c.write_deliverable()
        self.assertEqual(c.classify("", rc=0, ok=True, missing=()), (None, ""))

    def test_worker_error_is_harness_error(self):
        cls, evidence = Case().classify("", rc=None, error="unknown worker engine: nope")
        self.assertEqual(cls, "harness_error")
        self.assertIn("unknown worker engine", evidence)

    def test_ringer_sandbox_line_is_harness_error(self):
        cls, evidence = Case("opencode").classify("[ringer-sandbox] bwrap not found on PATH\n")
        self.assertEqual(cls, "harness_error")
        self.assertIn("bwrap", evidence)

    def test_absolute_path_outside_taskdir_is_sandbox_denied(self):
        outside = "/tmp/ringer-acceptance-not-here/report.md"
        c = Case("codex", expect=(outside,))
        cls, evidence = c.classify("", missing=(outside,))
        self.assertEqual(cls, "sandbox_denied")
        self.assertIn("ringer-acceptance-not-here", evidence)

    def test_relative_path_never_sandbox_denied(self):
        cls, _ = Case("codex", expect=("out/report.md",)).classify("", missing=("out/report.md",))
        self.assertEqual(cls, "model")

    def test_full_access_is_not_sandbox_denied(self):
        outside = "/tmp/ringer-acceptance-not-here/report.md"
        cls, _ = Case("codex", expect=(outside,), full_access=True).classify("", missing=(outside,))
        self.assertEqual(cls, "model")

    def test_unsandboxed_engine_is_not_sandbox_denied(self):
        outside = "/tmp/ringer-acceptance-not-here/report.md"
        cls, _ = Case("opencode", expect=(outside,)).classify("", missing=(outside,))
        self.assertEqual(cls, "model")

    def test_check_that_exports_the_file_is_not_sandbox_denied(self):
        outside = "/tmp/ringer-acceptance-not-here/report.md"
        check = f"cp report.md {outside} && test -s {outside}"
        cls, _ = Case("codex", expect=(outside,), check=check).classify("", missing=(outside,))
        self.assertEqual(cls, "model")


class TimeoutTests(unittest.TestCase):
    def test_worker_timeout_without_marker_is_model(self):
        cls, _ = Case().classify("working...\n", rc=None, timed_out=True)
        self.assertEqual(cls, "model")

    def test_check_timeout_is_model_with_evidence(self):
        c = Case()
        c.write_deliverable()
        cls, evidence = c.classify("", rc=0, check_timed_out=True, missing=())
        self.assertEqual(cls, "model")
        self.assertIn("check timed out", evidence.lower())


if __name__ == "__main__":
    unittest.main()
