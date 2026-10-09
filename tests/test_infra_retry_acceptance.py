#!/usr/bin/env python3
"""Acceptance tests for failure classes on attempt rows, infrastructure retries
and run status (openspec change trusted-multi-model-tracking, spec
failure-classification, design D4; tasks 1.4-1.6).

Contract under test:
  rows gain failure_class (absent/None on PASS), failure_evidence, model_attempt
  (int, None on infrastructure rows), run_family ("work" | "audition", from the
  manifest's top-level "family", default "work"); notes gain "failure_class=<c>".
  retry == "this attempt's spec was re-prompted with failure context".
  [retry] infra_max / infra_base_delay_s / infra_max_delay_s in config.
  Transient classes retry without using max_attempts and release the parallel
  slot while waiting; deterministic classes stop the task.
  State tasks gain model_attempts, infra_retries, end_reason; status
  "waiting_provider" while waiting. plain_transition_event uses model attempts.
"""
from __future__ import annotations

import importlib.util
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RINGER_PATH = ROOT / "ringer.py"
FX = ROOT / "tests" / "fixtures" / "provider-errors"
SPEC = importlib.util.spec_from_file_location("ringer_infra_acc", RINGER_PATH)
ringer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ringer
SPEC.loader.exec_module(ringer)

CAPACITY = "ERROR: Selected model is at capacity. Please try a different model."
POLICY = (FX / "opencode-policy-404.jsonl").read_text().strip()


def counter_script(first: str, then: str) -> str:
    """Shell body: run `first` on the 1st invocation in this task dir, `then` afterwards."""
    return (
        'n=$(cat .n 2>/dev/null || echo 0); n=$((n+1)); echo $n > .n; '
        f'if [ "$n" -eq 1 ]; then {first}; else {then}; fi'
    )


def sq(text: str) -> str:
    return "'" + text.replace("'", "'\"'\"'") + "'"


class InfraRetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ringer-infra-")
        self.root = Path(self.tmp.name)
        self.jsonl = self.root / "runs.jsonl"
        self.state_dir = self.root / "state"
        self.config = self.root / "config.toml"
        self.write_config(delay=0)

    def tearDown(self):
        self.tmp.cleanup()

    def write_config(self, *, delay: float, infra_max: int = 3):
        engines = {
            "cap_then_pass": ("codex", counter_script(f"echo {sq(CAPACITY)}; exit 1", "printf done > out.txt")),
            "always_cap": ("codex", f"echo {sq(CAPACITY)}; exit 1"),
            "policy": ("opencode", f"echo {sq(POLICY)}; exit 1"),
            "plain_fail": ("none", "printf wrong > out.txt"),
            "cap_then_model_fail": ("codex", counter_script(f"echo {sq(CAPACITY)}; exit 1", "printf wrong > out.txt")),
            "pass": ("none", "printf done > out.txt"),
        }
        lines = [f'state_dir = "{self.state_dir}"', "dashboard_port_base = 18987", "allow_full_access = false", "",
                 "[eval]", 'backend = "jsonl"', f'jsonl_path = "{self.jsonl}"', "",
                 "[retry]", f"infra_max = {infra_max}", f"infra_base_delay_s = {delay}", f"infra_max_delay_s = {max(delay, 0)}", ""]
        for name, (profile, body) in engines.items():
            lines += [f"[engines.{name}]", 'bin = "/bin/sh"', f"args_template = {json.dumps(['-c', body])}",
                      "sandbox_args = []", "full_access_args = []", f'failure_profile = "{profile}"', ""]
        self.config.write_text("\n".join(lines))

    def manifest(self, name, tasks, **extra):
        data = {"run_name": name, "workdir": str(self.root / f"work-{name}"), "max_parallel": 1, "tasks": tasks}
        data.update(extra)
        path = self.root / f"{name}.json"
        path.write_text(json.dumps(data))
        return path

    def task(self, key, engine, **extra):
        t = {"key": key, "engine": engine, "spec": "Write done to out.txt. " * 4, "expect_files": ["out.txt"],
             "check": 'test "$(cat out.txt 2>/dev/null)" = done || { echo "expected=done actual=$(cat out.txt 2>/dev/null)"; exit 1; }'}
        t.update(extra)
        return t

    def run_ringer(self, manifest, timeout=60):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", RINGER_NO_SELF_UPDATE="1")
        return subprocess.run([sys.executable, "-B", str(RINGER_PATH), "--config", str(self.config), "run", str(manifest),
                               "--identity", "acc", "--no-dashboard"], cwd=ROOT, env=env, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)

    def rows(self):
        return [json.loads(l) for l in self.jsonl.read_text().splitlines() if l.strip()] if self.jsonl.exists() else []

    def state_task(self, key):
        states = sorted((self.state_dir / "runs").glob("*.json"), key=lambda p: p.stat().st_mtime)
        data = json.loads(states[-1].read_text())
        tasks = data["tasks"]
        return tasks[key] if isinstance(tasks, dict) else next(t for t in tasks if t.get("key") == key)

    # --- rows -------------------------------------------------------------

    def test_rate_limit_then_pass_is_first_try(self):
        r = self.run_ringer(self.manifest("rl", [self.task("t", "cap_then_pass")]))
        self.assertEqual(r.returncode, 0, r.stdout)
        rows = self.rows()
        self.assertEqual([x["verdict"] for x in rows], ["FAIL", "PASS"])
        self.assertEqual(rows[0]["failure_class"], "rate_limited")
        self.assertIsNone(rows[0]["model_attempt"])
        self.assertIn("at capacity", rows[0]["failure_evidence"])
        self.assertIn("failure_class=rate_limited", rows[0]["notes"])
        self.assertFalse(rows[0]["retry"])
        self.assertIsNone(rows[1].get("failure_class"))
        self.assertEqual(rows[1]["model_attempt"], 1)
        self.assertFalse(rows[1]["retry"], "an infra retry is not a re-prompt")
        self.assertEqual({x["run_family"] for x in rows}, {"work"})
        st = self.state_task("t")
        self.assertEqual(st["model_attempts"], 1)
        self.assertEqual(st["infra_retries"], 1)
        line = ringer.plain_transition_event("t", "running", "pass", st)["line"]
        self.assertNotIn("second try", line)

    def test_policy_block_stops_without_retry(self):
        r = self.run_ringer(self.manifest("pol", [self.task("t", "policy")]))
        self.assertNotEqual(r.returncode, 0)
        rows = self.rows()
        self.assertEqual(len(rows), 1, "deterministic classes must not retry")
        self.assertEqual(rows[0]["failure_class"], "provider_policy")
        self.assertNotIn("\n", rows[0]["failure_evidence"])
        self.assertNotIn("cf_bm", json.dumps(rows[0]))
        self.assertEqual(self.state_task("t")["end_reason"], "provider_policy")

    def test_infra_retries_exhausted(self):
        r = self.run_ringer(self.manifest("ex", [self.task("t", "always_cap", max_attempts=2)]))
        self.assertNotEqual(r.returncode, 0)
        rows = self.rows()
        self.assertEqual(len(rows), 4, "1 attempt + infra_max (3) retries")
        self.assertTrue(all(x["failure_class"] == "rate_limited" for x in rows))
        self.assertTrue(all(x["model_attempt"] is None for x in rows))
        st = self.state_task("t")
        self.assertEqual(st["end_reason"], "rate_limited")
        self.assertEqual(st["model_attempts"], 0)

    def test_model_failures_use_max_attempts(self):
        self.run_ringer(self.manifest("mf", [self.task("t", "plain_fail", max_attempts=2)]))
        rows = self.rows()
        self.assertEqual([x["model_attempt"] for x in rows], [1, 2])
        self.assertEqual([x["retry"] for x in rows], [False, True])
        self.assertEqual({x["failure_class"] for x in rows}, {"model"})

    def test_failure_context_excludes_infra_attempt(self):
        self.run_ringer(self.manifest("ctx", [self.task("t", "cap_then_model_fail", max_attempts=2)]))
        rows = self.rows()
        self.assertEqual([x.get("failure_class") for x in rows], ["rate_limited", "model", "model"])
        self.assertNotIn("Previous attempt failed", rows[1]["spec"])
        self.assertIn("Previous attempt failed", rows[2]["spec"])
        self.assertIn("expected=done actual=wrong", rows[2]["spec"])
        self.assertNotIn("at capacity", rows[2]["spec"])

    def test_family_from_manifest(self):
        self.run_ringer(self.manifest("fam", [self.task("t", "pass")], family="audition"))
        self.assertEqual(self.rows()[0]["run_family"], "audition")

    def test_bad_family_rejected(self):
        r = self.run_ringer(self.manifest("badfam", [self.task("t", "pass")], family="weekend"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("family", r.stdout)
        self.assertEqual(self.rows(), [])

    # --- scheduling -------------------------------------------------------

    def test_slot_released_while_waiting(self):
        self.write_config(delay=2)
        r = self.run_ringer(self.manifest("slot", [self.task("a", "cap_then_pass"), self.task("b", "pass")]))
        self.assertEqual(r.returncode, 0, r.stdout)
        rows = self.rows()
        b_pass = next(x for x in rows if x["task_key"] == "b" and x["verdict"] == "PASS")
        a_pass = next(x for x in rows if x["task_key"] == "a" and x["verdict"] == "PASS")
        self.assertLess(b_pass["logged_at"], a_pass["logged_at"], "b should run while a waits for the provider")

    def test_cancel_during_wait(self):
        self.write_config(delay=60)
        manifest = self.manifest("cancel", [self.task("t", "always_cap")])
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", RINGER_NO_SELF_UPDATE="1")
        proc = subprocess.Popen([sys.executable, "-B", str(RINGER_PATH), "--config", str(self.config), "run", str(manifest),
                                 "--identity", "acc", "--no-dashboard"], cwd=ROOT, env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not self.rows():
            time.sleep(0.2)
        self.assertTrue(self.rows(), "first attempt never logged")
        time.sleep(0.5)
        status = self.state_task("t")["status"]
        self.assertEqual(status, "waiting_provider")
        start = time.monotonic()
        proc.send_signal(signal.SIGTERM)
        proc.communicate(timeout=20)
        self.assertLess(time.monotonic() - start, 15, "the wait must be cancellable")
        self.assertNotEqual(proc.returncode, 0)


class TransitionWordingTests(unittest.TestCase):
    def test_pass_after_infra_retry_is_not_second_try(self):
        task = {"attempts": 2, "model_attempts": 1, "infra_retries": 1, "elapsed_s": 12}
        self.assertNotIn("second try", ringer.plain_transition_event("t", "running", "pass", task)["line"])

    def test_pass_after_model_retry_is_second_try(self):
        task = {"attempts": 3, "model_attempts": 2, "infra_retries": 1, "elapsed_s": 12}
        self.assertIn("second try", ringer.plain_transition_event("t", "retrying", "pass", task)["line"])

    def test_waiting_provider_line(self):
        task = {"attempts": 1, "model_attempts": 0, "wait_reason": "rate_limited", "wait_s": 30}
        event = ringer.plain_transition_event("t", "running", "waiting_provider", task)
        self.assertIsNotNone(event)
        self.assertIn("rate_limited", event["line"])


if __name__ == "__main__":
    unittest.main()
