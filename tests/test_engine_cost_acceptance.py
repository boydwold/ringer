#!/usr/bin/env python3
"""Acceptance tests for engine-reported cost and summed tokens (openspec change
trusted-multi-model-tracking, spec model-auditions "Budget with a hard
backstop", design D6 Cost; task 7.2).

Contract under test:
  [engines.X] token_aggregate = "last" (default, today's behaviour) | "sum"
  [engines.X] cost_regex = '<regex with one capture group>'  (summed over matches)
  parse_token_count(text, token_regex, aggregate="last") and
  parse_cost(text, cost_regex) -> float | None
  Attempt rows gain cost_usd (float, or None when the engine has no
  cost_regex or nothing matched). Sums come only from this attempt's output.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ringer  # noqa: E402

TOKEN_RE = r'"type":"step_finish".*?"tokens":\{"total":([0-9]+)'
COST_RE = r'"type":"step_finish".*?"cost":([0-9.eE+-]+)'


def step(total, cost):
    return json.dumps({"type": "step_finish", "part": {"type": "step-finish", "tokens": {"total": total, "input": total - 5, "output": 5},
                                                        "cost": cost}}, separators=(",", ":"))


STEPS = "\n".join([json.dumps({"type": "text", "part": {"text": "cost 99 tokens 99"}}), step(100, 0.001), step(200, 0.002), step(300, 0.003)])


class Parsing(unittest.TestCase):
    def test_sum_and_last(self):
        self.assertEqual(ringer.parse_token_count(STEPS, TOKEN_RE, aggregate="sum"), 600)
        self.assertEqual(ringer.parse_token_count(STEPS, TOKEN_RE, aggregate="last"), 300)
        self.assertEqual(ringer.parse_token_count(STEPS, TOKEN_RE), 300, "default stays last")

    def test_cost_sum(self):
        self.assertAlmostEqual(ringer.parse_cost(STEPS, COST_RE), 0.006, places=9)
        self.assertIsNone(ringer.parse_cost("no steps here", COST_RE))
        self.assertIsNone(ringer.parse_cost(STEPS, None))

    def test_real_fixture(self):
        line = (ROOT / "tests" / "fixtures" / "provider-errors" / "opencode-step-finish.jsonl").read_text()
        self.assertAlmostEqual(ringer.parse_cost(line, COST_RE), 0.0204522348, places=9)
        self.assertEqual(ringer.parse_token_count(line, TOKEN_RE, aggregate="sum"), 20904)

    def test_config_validation(self):
        base = {"bin": "x", "args_template": ["{spec}"]}
        e = ringer.load_engines({"oc": dict(base, token_aggregate="sum", cost_regex=COST_RE)})["oc"]
        self.assertEqual(e.token_aggregate, "sum")
        self.assertEqual(e.cost_regex, COST_RE)
        self.assertEqual(ringer.load_engines({"oc": dict(base)})["oc"].token_aggregate, "last")
        for bad in ({"token_aggregate": "median"}, {"cost_regex": "(unclosed"}, {"cost_regex": "no group"}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                ringer.load_engines({"oc": dict(base, **bad)})


class RowsCarryCost(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.jsonl, self.cfg = d / "runs.jsonl", d / "config.toml"
        body = "printf done > out.txt; cat <<'EOF'\n" + STEPS + "\nEOF"
        self.cfg.write_text("\n".join([
            f'state_dir = "{d}/state"', "dashboard_port_base = 19187", "",
            "[eval]", 'backend = "jsonl"', f'jsonl_path = "{self.jsonl}"', "",
            "[engines.priced]", 'bin = "/bin/sh"', f"args_template = {json.dumps(['-c', body])}",
            "sandbox_args = []", "full_access_args = []", 'token_aggregate = "sum"',
            f"token_regex = '{TOKEN_RE}'", f"cost_regex = '{COST_RE}'", "",
            "[engines.unpriced]", 'bin = "/bin/sh"', f"args_template = {json.dumps(['-c', 'printf done > out.txt'])}",
            "sandbox_args = []", "full_access_args = []", ""]))
        self.manifest = d / "m.json"
        self.manifest.write_text(json.dumps({"run_name": "cost", "workdir": str(d / "w"), "max_parallel": 2, "tasks": [
            {"key": k, "engine": k, "spec": "Write done to out.txt. " * 4, "expect_files": ["out.txt"],
             "check": "grep -qx done out.txt || { echo 'FAIL: out.txt'; exit 1; }"} for k in ("priced", "unpriced")]}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_rows(self):
        env = dict(os.environ, RINGER_NO_SELF_UPDATE="1", PYTHONDONTWRITEBYTECODE="1")
        r = subprocess.run([sys.executable, "-B", str(ROOT / "ringer.py"), "--config", str(self.cfg), "run", str(self.manifest),
                            "--identity", "acc", "--no-dashboard"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rows = {x["task_key"]: x for x in (json.loads(l) for l in self.jsonl.read_text().splitlines() if l.strip())}
        self.assertEqual(rows["priced"]["worker_tokens"], 600)
        self.assertAlmostEqual(rows["priced"]["cost_usd"], 0.006, places=9)
        self.assertIsNone(rows["unpriced"]["cost_usd"])


if __name__ == "__main__":
    unittest.main()
