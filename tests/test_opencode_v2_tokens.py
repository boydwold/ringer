#!/usr/bin/env python3
"""Token counts from OpenCode 2.x `run --format json` output.

OpenCode 1.x put a total on every step_finish event:
  "tokens":{"total":20904,"input":20691,"output":15,"reasoning":134,"cache":{"write":0,"read":64}}
where total = input + output + reasoning + cache.read + cache.write.
OpenCode 2.x (2.2.0) sends the same parts with no total, so every
`"tokens":\\{"total":` token_regex matches nothing and the tokens column is
empty. When the configured regex finds nothing, Ringer adds the parts of each
step_finish event instead, with the engine's aggregate (last or sum).

tests/fixtures/opencode/v2-run-steps.jsonl is real output from opencode 2.2.0
with GLM 5.2 (2026-11-01, three steps). Only the task path was replaced.
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

V2 = (ROOT / "tests" / "fixtures" / "opencode" / "v2-run-steps.jsonl").read_text()
V1 = (ROOT / "tests" / "fixtures" / "provider-errors" / "opencode-step-finish.jsonl").read_text()
SAMPLE_RE = r'"type":"step_finish".*?"tokens":\{"total":([0-9]+)'  # config.sample.toml
LIVE_RE = r'"tokens":\{"total":([0-9]+)'  # older configs
COST_RE = r'"type":"step_finish".*?"cost":([0-9.eE+-]+)'

# Per step: input + output + reasoning + cache.read + cache.write
STEP_TOTALS = [13771 + 31 + 12, 128 + 29 + 13696, 129 + 36 + 13760]


class V2Parsing(unittest.TestCase):
    def test_fixture_matches_expected_steps(self):
        steps = [json.loads(line)["part"]["tokens"] for line in V2.splitlines()
                 if json.loads(line)["type"] == "step_finish"]
        self.assertEqual(len(steps), 3)
        self.assertTrue(all("total" not in s for s in steps), "fixture must be 2.x output (no total)")

    def test_sum(self):
        for regex in (SAMPLE_RE, LIVE_RE):
            with self.subTest(regex=regex):
                self.assertEqual(ringer.parse_token_count(V2, regex, aggregate="sum"), sum(STEP_TOTALS))

    def test_last(self):
        for regex in (SAMPLE_RE, LIVE_RE):
            with self.subTest(regex=regex):
                self.assertEqual(ringer.parse_token_count(V2, regex, aggregate="last"), STEP_TOTALS[-1])

    def test_v1_total_still_wins(self):
        self.assertEqual(ringer.parse_token_count(V1, SAMPLE_RE, aggregate="sum"), 20904)
        self.assertEqual(ringer.parse_token_count(V1, LIVE_RE), 20904)

    def test_cost_still_parses(self):
        self.assertAlmostEqual(ringer.parse_cost(V2, COST_RE), 0.00864208 + 0.00206698 + 0.0020935, places=9)

    def test_no_step_events_stays_none(self):
        self.assertIsNone(ringer.parse_token_count('{"type":"text","part":{"text":"hi"}}', SAMPLE_RE))
        self.assertIsNone(ringer.parse_token_count("no tokens here", SAMPLE_RE, aggregate="sum"))

    def test_malformed_step_is_skipped(self):
        bad = '{"type":"step_finish","part":{"tokens":{"input":"x"}}}\n{"type":"step_finish" not json'
        self.assertIsNone(ringer.parse_token_count(bad, SAMPLE_RE, aggregate="sum"))
        mixed = bad + "\n" + V2
        self.assertEqual(ringer.parse_token_count(mixed, SAMPLE_RE, aggregate="sum"), sum(STEP_TOTALS))


def step(tokens):
    return json.dumps({"type": "step_finish", "part": {"type": "step-finish", "tokens": tokens}})


class StepValidation(unittest.TestCase):
    def count(self, *steps, aggregate="sum"):
        return ringer.parse_token_count("\n".join(steps), SAMPLE_RE, aggregate=aggregate)

    def test_cache_write_counts(self):
        self.assertEqual(self.count(step({"input": 10, "output": 2, "reasoning": 1,
                                          "cache": {"read": 100, "write": 40}})), 153)

    def test_last_is_last_step_not_largest(self):
        big = step({"input": 900, "output": 1, "reasoning": 0, "cache": {"read": 0, "write": 0}})
        small = step({"input": 50, "output": 1, "reasoning": 0, "cache": {"read": 0, "write": 0}})
        self.assertEqual(self.count(big, small, aggregate="last"), 51)

    def test_bad_values_skip_the_step(self):
        for tokens in ({"input": 5, "output": 5.0}, {"input": 1, "output": True},
                       {"input": -500, "output": 10}, {"input": 100, "cache": {"read": 100.0}},
                       {"input": 5, "cache": 7}, {}):
            with self.subTest(tokens=tokens):
                self.assertIsNone(self.count(step(tokens)))

    def test_missing_cache_counts_as_zero(self):
        self.assertEqual(self.count(step({"input": 100, "output": 10})), 110)

    def test_other_event_naming_step_finish_is_ignored(self):
        line = json.dumps({"type": "text", "part": {"type": "text", "text": "step_finish",
                                                    "tokens": {"input": 999}}})
        self.assertIsNone(self.count(line))
        not_step_part = json.dumps({"type": "step_finish", "part": {"type": "text", "tokens": {"input": 999}}})
        self.assertIsNone(self.count(not_step_part))
        not_step_event = json.dumps({"type": "text", "part": {"type": "step-finish", "text": "step_finish",
                                                              "tokens": {"input": 999}}})
        self.assertIsNone(self.count(not_step_event))

    def test_other_engines_do_not_use_the_fallback(self):
        # A codex or claude worker that prints raw step_finish JSON (e.g. cat of a
        # fixture) keeps the old result: no token count.
        self.assertIsNone(ringer.parse_token_count(V2, ringer.DEFAULT_TOKEN_REGEX))
        self.assertIsNone(ringer.parse_token_count(V2, None))
        self.assertIsNone(ringer.parse_token_count(V2, r"total_tokens=([0-9]+)", aggregate="sum"))

class V2RowsCarryTokens(unittest.TestCase):
    """End to end: a fake worker prints the real 2.x output; the eval row gets tokens."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.jsonl, self.cfg = d / "runs.jsonl", d / "config.toml"
        body = "printf done > out.txt; cat <<'EOF'\n" + V2.strip() + "\nEOF"
        self.cfg.write_text("\n".join([
            f'state_dir = "{d}/state"', "dashboard_port_base = 19287", "",
            "[eval]", 'backend = "jsonl"', f'jsonl_path = "{self.jsonl}"', "",
            "[engines.oc2]", 'bin = "/bin/sh"', f"args_template = {json.dumps(['-c', body])}",
            "sandbox_args = []", "full_access_args = []", 'token_aggregate = "sum"',
            f"token_regex = '{SAMPLE_RE}'", f"cost_regex = '{COST_RE}'", ""]))
        self.manifest = d / "m.json"
        self.manifest.write_text(json.dumps({"run_name": "oc2-tokens", "workdir": str(d / "w"), "max_parallel": 1, "tasks": [
            {"key": "t", "engine": "oc2", "spec": "Write done to out.txt. " * 4, "expect_files": ["out.txt"],
             "check": "grep -qx done out.txt || { echo 'FAIL: out.txt'; exit 1; }"}]}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_row_has_tokens(self):
        env = dict(os.environ, RINGER_NO_SELF_UPDATE="1", PYTHONDONTWRITEBYTECODE="1")
        r = subprocess.run([sys.executable, "-B", str(ROOT / "ringer.py"), "--config", str(self.cfg), "run",
                            str(self.manifest), "--identity", "acc", "--no-dashboard"],
                           cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rows = [json.loads(line) for line in self.jsonl.read_text().splitlines() if line.strip()]
        self.assertEqual(rows[-1]["worker_tokens"], sum(STEP_TOTALS))


if __name__ == "__main__":
    unittest.main()
