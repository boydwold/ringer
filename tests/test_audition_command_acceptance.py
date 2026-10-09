#!/usr/bin/env python3
"""Acceptance tests for `ringer.py audition` (openspec change
trusted-multi-model-tracking, spec model-auditions, design D6; tasks 7.3-7.6).

Contract under test:
  config [audition]: weekly_budget_usd (required, > 0), credential_file
  (required, must exist), max_models (default 5), token_estimate (default
  40000), concurrency (default 2), engine (default "opencode"), set_dir
  (default <repo>/templates/audition), check_timeout_s (default 120).
  ringer.py audition [--dry-run] [--max-models N] [--catalog-file P] [--no-refresh]
  - missing budget/credential -> exit 2 naming the key; nothing runs
  - lock RINGER_HOME/audition.lock (non-blocking); if held -> exit 0,
    "another audition run is active", nothing runs
  - candidates: catalog models with tool support (entries listing
    supported_parameters without "tools" are excluded), text->text, fixed
    price, context >= 32000, not policy-blocked in the last 7 days; models
    with no audition rows for a task type first; at most max_models
  - each selected model gets the set's tasks for task types it has no
    audition evidence for; run_name "audition", family "audition",
    key "<task>--<slug>" with slug = model id lowercased, [^a-z0-9]+ -> "-",
    model "openrouter/<id>", max_attempts 1, check run through
    engines/check-sandboxed.sh with `python3 -I <set>/<task>/check.py`,
    task dir seeded from the task's fixture/
  - worker env: RINGER_SANDBOX_HIDE includes the set dir;
    OPENCODE_CONFIG_CONTENT carries the credential as
    provider.openrouter.options.apiKey
  - spend ledger RINGER_HOME/audition-spend.jsonl, ISO week in local time;
    a task is planned only if this week's spend + its estimate fits the budget
    (estimate = model's previous audition cost, else token_estimate priced
    85% input / 15% output); after each task the actual cost_usd is recorded
  - an attempt classed quota_exhausted stops the run (no further tasks)
  - nothing eligible -> exit 0 "nothing to do"
  - --dry-run prints one line per planned task "PLAN <task_key> <model> est=$<x>",
    one per skipped task "SKIP <task_key> <reason>" (reason "budget" when the
    budget stops it), a total estimated spend line, runs nothing, writes no ledger
  - summary names models tried, verdicts by task type, infrastructure
    failures, "spent" this week and budget left
"""
from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINUX_BWRAP = sys.platform.startswith("linux") and shutil.which("bwrap") is not None

CHECK = """import sys, pathlib
p = pathlib.Path('out.txt')
if p.is_file() and p.read_text().strip() == 'done':
    print('PASS: done'); sys.exit(0)
print('FAIL: out.txt must contain done'); sys.exit(1)
"""


def week_key(now=None):
    y, w, _ = (now or dt.datetime.now().astimezone()).isocalendar()
    return f"{y}-W{w:02d}"


def cm(mid, prompt=0.5, completion=1.5, tools=True, ctx=128000, free=False, variable=False):
    return {"id": mid, "name": mid, "context_length": ctx, "modality": "text->text", "variable_pricing": variable,
            "pricing_unknown": False, "free": free, "prompt_per_m": prompt, "completion_per_m": completion,
            "pricing": {}, "fetched_at": "2026-10-09T00:00:00+00:00",
            "supported_parameters": ["tools", "temperature"] if tools else ["temperature"]}


@unittest.skipUnless(LINUX_BWRAP, "audition checks run in the Linux check sandbox")
class AuditionCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.d = Path(self.tmp.name)
        self.home = d / "home"
        self.home.mkdir()
        self.log = d / "runs.jsonl"
        self.log.write_text("")
        # A one-task audition set with a trivial check.
        self.set_dir = d / "set"
        t = self.set_dir / "tiny-fix"
        (t / "fixture").mkdir(parents=True)
        (t / "reference").mkdir()
        (t / "fixture" / "start.txt").write_text("start\n")
        (t / "reference" / "out.txt").write_text("done\n")
        (t / "check.py").write_text(CHECK)
        (t / "spec.md").write_text("Write the word done into out.txt in the current directory. " * 5)
        (t / "task.toml").write_text('key = "tiny-fix"\ntitle = "Tiny"\ntask_type = "code-fix"\nexpect_files = ["out.txt"]\ntoken_estimate = 10000\n')
        self.cred = d / "audition.key"
        self.cred.write_text("sk-or-AUDITION-TEST-KEY\n")
        self.cred.chmod(0o600)
        self.catalog = d / "catalog.json"
        self.write_catalog([cm("acme/alpha"), cm("acme/beta"), cm("acme/no-tools", tools=False),
                            cm("acme/variable", variable=True), cm("acme/tiny-ctx", ctx=8000)])
        self.engine_body = ("env > env.txt; " "printf done > out.txt; "
                            "echo '{\"type\":\"step_finish\",\"part\":{\"tokens\":{\"total\":1000},\"cost\":0.01}}'")
        self.write_config()

    def tearDown(self):
        self.tmp.cleanup()

    def write_catalog(self, models):
        self.catalog.write_text(json.dumps({"fetched_at": "2026-10-09T00:00:00+00:00", "models": models}))

    def write_config(self, *, budget="10.0", cred=True, max_models=5, concurrency=1, body=None):
        lines = [f'state_dir = "{self.d}/state"', "dashboard_port_base = 19287", "", "[eval]", 'backend = "jsonl"',
                 f'jsonl_path = "{self.log}"', "", "[engines.fake]", 'bin = "/bin/sh"',
                 f"args_template = {json.dumps(['-c', body or self.engine_body])}", "sandbox_args = []",
                 "full_access_args = []", 'failure_profile = "opencode"', 'token_aggregate = "sum"',
                 "token_regex = '\"tokens\":\\{\"total\":([0-9]+)'", "cost_regex = '\"cost\":([0-9.]+)'", "",
                 "[audition]", 'engine = "fake"', f'set_dir = "{self.set_dir}"', f"max_models = {max_models}",
                 f"concurrency = {concurrency}"]
        if budget is not None:
            lines.append(f"weekly_budget_usd = {budget}")
        if cred:
            lines.append(f'credential_file = "{self.cred}"')
        (self.d / "config.toml").write_text("\n".join(lines) + "\n")

    def audition(self, *args, timeout=180):
        env = dict(os.environ, RINGER_HOME=str(self.home), RINGER_NO_SELF_UPDATE="1", PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, "-B", str(ROOT / "ringer.py"), "--config", str(self.d / "config.toml"),
                               "audition", "--catalog-file", str(self.catalog), "--no-refresh", *args],
                              cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout)

    def rows(self):
        return [json.loads(l) for l in self.log.read_text().splitlines() if l.strip()]

    @staticmethod
    def planned(out):
        return [l.split()[1] for l in out.splitlines() if l.startswith("PLAN ")]

    def ledger(self):
        p = self.home / "audition-spend.jsonl"
        return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []

    # --- refusals ---------------------------------------------------------

    def test_requires_budget(self):
        self.write_config(budget=None)
        r = self.audition()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("weekly_budget_usd", r.stdout + r.stderr)
        self.assertEqual(self.rows(), [])

    def test_requires_credential(self):
        self.write_config(cred=False)
        r = self.audition()
        self.assertEqual(r.returncode, 2)
        self.assertIn("credential_file", r.stdout + r.stderr)

    def test_lock_held(self):
        with open(self.home / "audition.lock", "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            r = self.audition()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("another audition run is active", r.stdout.lower())
        self.assertEqual(self.rows(), [])

    # --- planning ---------------------------------------------------------

    def test_dry_run_plan(self):
        r = self.audition("--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = r.stdout
        self.assertEqual(sorted(self.planned(out)), ["tiny-fix--acme-alpha", "tiny-fix--acme-beta"])
        self.assertIn("estimated", out.lower())
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.ledger(), [])

    def test_max_models_and_evidence_order(self):
        self.log.write_text(json.dumps({"run_id": "audition-x", "task_key": "tiny-fix--acme-alpha", "verdict": "PASS",
                                        "model": "openrouter/acme/alpha", "worker_engine": "fake", "task_type": "code-fix",
                                        "failure_class": None, "model_attempt": 1, "run_family": "audition",
                                        "retry": False, "logged_at": "2026-10-09T00:00:00+00:00", "notes": ""}) + "\n")
        self.write_catalog([cm("acme/alpha"), cm("acme/beta")])
        r = self.audition("--dry-run", "--max-models", "5")
        self.assertEqual(self.planned(r.stdout), ["tiny-fix--acme-beta"], "alpha already has code-fix audition evidence")
        self.write_catalog([cm("acme/beta"), cm("acme/gamma"), cm("acme/delta")])
        r = self.audition("--dry-run", "--max-models", "2")
        self.assertEqual(len(self.planned(r.stdout)), 2, "max_models caps the plan")

    def test_policy_blocked_excluded(self):
        yesterday = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat()
        self.log.write_text(json.dumps({"run_id": "w1", "task_key": "t", "verdict": "FAIL", "model": "openrouter/acme/beta",
                                        "worker_engine": "fake", "task_type": "code-fix", "failure_class": "provider_policy",
                                        "model_attempt": None, "run_family": "work", "retry": False,
                                        "logged_at": yesterday, "notes": ""}) + "\n")
        r = self.audition("--dry-run")
        self.assertEqual(self.planned(r.stdout), ["tiny-fix--acme-alpha"])

    def test_budget_reached(self):
        (self.home / "audition-spend.jsonl").write_text(json.dumps({"week": week_key(), "cost_usd": 9.80, "model": "x", "task_key": "y"}) + "\n")
        # token_estimate 10000 at 0.5/1.5 per M -> 85/15 split ~ $0.0065; raise prices so one task costs $0.40
        self.write_catalog([cm("acme/alpha", prompt=40.0, completion=40.0)])
        r = self.audition("--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.planned(r.stdout), [])
        self.assertTrue(any(l.startswith("SKIP tiny-fix--acme-alpha") and "budget" in l for l in r.stdout.splitlines()), r.stdout)

    def test_nothing_to_do(self):
        self.write_catalog([cm("acme/no-tools", tools=False)])
        r = self.audition()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("nothing to do", r.stdout.lower())

    # --- real runs ---------------------------------------------------------

    def test_run_records_audition_rows_ledger_env_and_summary(self):
        self.write_catalog([cm("acme/Alpha.v2")])
        r = self.audition()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rows = self.rows()
        self.assertEqual(len(rows), 1, "max_attempts 1: one row per task")
        row = rows[0]
        self.assertEqual(row["run_family"], "audition")
        self.assertEqual(row["task_key"], "tiny-fix--acme-alpha-v2")
        self.assertEqual(row["model"], "openrouter/acme/Alpha.v2")
        self.assertEqual(row["verdict"], "PASS")
        self.assertAlmostEqual(row["cost_usd"], 0.01)
        led = self.ledger()
        self.assertEqual(len(led), 1)
        self.assertEqual(led[0]["week"], week_key())
        self.assertAlmostEqual(led[0]["cost_usd"], 0.01)
        envs = list((self.home).rglob("env.txt"))
        self.assertEqual(len(envs), 1, "worker env captured once")
        env = envs[0].read_text()
        self.assertIn(str(self.set_dir), env.split("RINGER_SANDBOX_HIDE=", 1)[1].splitlines()[0])
        cfg_line = env.split("OPENCODE_CONFIG_CONTENT=", 1)[1].splitlines()[0]
        self.assertEqual(json.loads(cfg_line)["provider"]["openrouter"]["options"]["apiKey"], "sk-or-AUDITION-TEST-KEY")
        self.assertIn("spent", r.stdout.lower())
        self.assertIn("code-fix", r.stdout)

    def test_quota_exhausted_stops_run(self):
        body = ("echo '{\"type\":\"error\",\"error\":{\"name\":\"APIError\",\"data\":{\"message\":\"Insufficient credits\","
                "\"statusCode\":402}}}'; exit 1")
        self.write_config(body=body, concurrency=1)
        self.write_catalog([cm("acme/alpha"), cm("acme/beta"), cm("acme/gamma")])
        r = self.audition()
        rows = self.rows()
        self.assertEqual(len(rows), 1, "quota_exhausted must stop further tasks: " + r.stdout)
        self.assertEqual(rows[0]["failure_class"], "quota_exhausted")
        self.assertIn("quota", r.stdout.lower())


if __name__ == "__main__":
    unittest.main()
