#!/usr/bin/env python3
"""Acceptance tests: the scoreboard counts model evidence on work runs only, the
same way through JSONL and the ringer.db read model (openspec change
trusted-multi-model-tracking, spec model-scoreboard, design D5; tasks 3.1-3.3).

Contract under test:
  aggregate_model_log_rows(rows, *, task_type=None, model=None, family="work")
  aggregate_model_scoreboard_rows(rows, *, task_type=None, model=None, family="work")
      family: "work" | "audition" | "all"; groups gain "run_family" and
      "infra" ({class: count}); rates/attempts/retries/medians/last_seen come
      from model-counted rows only (PASS or failure_class model; legacy rows
      without failure_class count as model).
  infra_only_models(rows, *, task_type=None, model=None, family="work")
      -> [{"engine", "model", "infra": {class: count}}] for models with no
      model-counted task.
  model_scoreboard_tier(tasks, first_try_rate) is the single rule;
  proven_model_group(group) delegates to it.
  ringer.db schema 4 carries failure_class, failure_evidence, model_attempt,
  run_family, cost_usd; a sync over an older schema rebuilds.
  `ringer.py models --family audition|work|all`.
"""
from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ringer  # noqa: E402

_clock = [0]


def row(run, key, verdict, *, cls=None, ma=None, retry=False, model="openrouter/z-ai/glm-5.2", engine="opencode",
        task_type="code-fix", family="work", tokens=1000, duration=1000, legacy=False):
    _clock[0] += 1
    r = {"run_id": run, "task_key": key, "verdict": verdict, "retry": retry, "model": model, "worker_engine": engine,
         "task_type": task_type, "worker_tokens": tokens, "duration_ms": duration,
         "logged_at": f"2026-10-09T00:00:{_clock[0]:02d}+00:00", "notes": ""}
    if not legacy:
        r.update({"failure_class": cls, "model_attempt": ma, "run_family": family, "failure_evidence": "" if cls in (None, "model") else "evidence"})
    return r


def only(groups, **match):
    hits = [g for g in groups if all(g.get(k) == v for k, v in match.items())]
    assert len(hits) == 1, (match, groups)
    return hits[0]


class ModelCountedRates(unittest.TestCase):
    def test_rate_limited_first_row_then_pass_is_first_try(self):
        rows = [row("r1", "t", "FAIL", cls="rate_limited"), row("r1", "t", "PASS", ma=1)]
        g = only(ringer.aggregate_model_log_rows(rows))
        self.assertEqual((g["tasks"], g["first_try_pass_rate"], g["pass_rate"], g["attempts"]), (1, 1.0, 1.0, 1))
        self.assertEqual(g["infra"], {"rate_limited": 1})

    def test_infra_only_task_not_counted(self):
        rows = [row("r1", "t", "FAIL", cls="provider_error"), row("r1", "t", "FAIL", cls="provider_error"),
                row("r2", "u", "PASS", ma=1, model="openrouter/x/other")]
        groups = ringer.aggregate_model_log_rows(rows)
        self.assertEqual([g["model"] for g in groups], ["openrouter/x/other"])
        infra = ringer.infra_only_models(rows)
        self.assertEqual(len(infra), 1)
        self.assertEqual(infra[0]["model"], "openrouter/z-ai/glm-5.2")
        self.assertEqual(infra[0]["infra"], {"provider_error": 2})

    def test_infra_between_model_attempts(self):
        rows = [row("r1", "t", "FAIL", cls="model", ma=1), row("r1", "t", "FAIL", cls="rate_limited", retry=True),
                row("r1", "t", "PASS", ma=2, retry=True)]
        g = only(ringer.aggregate_model_log_rows(rows))
        self.assertEqual((g["tasks"], g["first_try_pass_rate"], g["pass_rate"], g["attempts"]), (1, 0.0, 1.0, 2))
        self.assertEqual(g["infra"], {"rate_limited": 1})

    def test_tokens_and_duration_from_model_rows_only(self):
        rows = [row("r1", "t", "FAIL", cls="provider_error", tokens=0, duration=1),
                row("r1", "t", "PASS", ma=1, tokens=5000, duration=9000)]
        g = only(ringer.aggregate_model_log_rows(rows))
        self.assertEqual(g["median_tokens"], 5000)
        self.assertEqual(g["median_duration_ms"], 9000)

    def test_legacy_rows_unchanged(self):
        rows = [row("r1", "t", "FAIL", legacy=True), row("r1", "t", "PASS", retry=True, legacy=True),
                row("r2", "u", "PASS", legacy=True)]
        g = only(ringer.aggregate_model_log_rows(rows))
        self.assertEqual((g["tasks"], g["passed"], g["first_try_pass_rate"], g["attempts"]), (2, 2, 0.5, 3))
        self.assertEqual(g.get("infra"), {})

    def test_scoreboard_rollup_uses_same_rules(self):
        rows = [row("r1", "t", "FAIL", cls="rate_limited"), row("r1", "t", "PASS", ma=1),
                row("r2", "u", "FAIL", cls="model", ma=1), row("r2", "u", "PASS", ma=2, retry=True)]
        m = only(ringer.aggregate_model_scoreboard_rows(rows), model="openrouter/z-ai/glm-5.2")
        self.assertEqual(m["tasks"], 2)
        self.assertAlmostEqual(m["first_try_pass_rate"], 0.5)
        self.assertEqual(m["infra"], {"rate_limited": 1})


class FamiliesAndTiers(unittest.TestCase):
    def rows(self):
        out = [row(f"w{i}", "t", "PASS", ma=1) for i in range(2)]
        out += [row(f"a{i}", "t", "PASS", ma=1, family="audition") for i in range(4)]
        return out

    def test_audition_passes_do_not_promote(self):
        g = only(ringer.aggregate_model_log_rows(self.rows()))
        self.assertEqual(g["tasks"], 2)
        self.assertEqual(g["run_family"], "work")
        self.assertFalse(ringer.proven_model_group(g))
        self.assertEqual(ringer.model_scoreboard_tier(g["tasks"], g["first_try_pass_rate"]), "probation")

    def test_audition_family_view(self):
        g = only(ringer.aggregate_model_log_rows(self.rows(), family="audition"))
        self.assertEqual((g["tasks"], g["run_family"]), (4, "audition"))

    def test_all_family_keeps_families_apart(self):
        groups = ringer.aggregate_model_log_rows(self.rows(), family="all")
        self.assertEqual(sorted((g["run_family"], g["tasks"]) for g in groups), [("audition", 4), ("work", 2)])

    def test_bad_family_rejected(self):
        with self.assertRaises(ValueError):
            ringer.aggregate_model_log_rows(self.rows(), family="weekend")

    def test_outages_do_not_block_promotion(self):
        rows = []
        for i in range(3):
            rows += [row(f"r{i}", "t", "FAIL", cls="rate_limited"), row(f"r{i}", "t", "FAIL", cls="rate_limited"),
                     row(f"r{i}", "t", "PASS", ma=1)]
        g = only(ringer.aggregate_model_log_rows(rows))
        self.assertEqual((g["tasks"], g["first_try_pass_rate"]), (3, 1.0))
        self.assertTrue(ringer.proven_model_group(g))
        self.assertEqual(g["infra"], {"rate_limited": 6})

    def test_single_tier_rule(self):
        for tasks, rate in [(3, 2 / 3), (3, 0.66), (2, 1.0), (10, 0.9)]:
            g = {"tasks": tasks, "first_try_pass_rate": rate}
            self.assertEqual(ringer.proven_model_group(g), ringer.model_scoreboard_tier(tasks, rate) == "proven")


class ReadModelDb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.log = self.dir / "runs.jsonl"
        self.db = self.dir / "ringer.db"
        rows = [row("r1", "t", "FAIL", cls="rate_limited"), row("r1", "t", "PASS", ma=1),
                row("r2", "u", "FAIL", cls="provider_policy", model="openrouter/x/free:free"),
                row("a1", "v", "PASS", ma=1, family="audition"),
                row("r3", "w", "FAIL", legacy=True)]
        rows[1]["cost_usd"] = 0.0123
        self.rows = rows
        self.log.write_text("".join(json.dumps(r) + "\n" for r in rows))

    def tearDown(self):
        self.tmp.cleanup()

    def test_db_rows_carry_new_fields(self):
        ringer.rebuild_read_model_db(self.db, self.log)
        db_rows, _ = ringer.db_attempt_rows(self.db)
        by_key = {(r["run_id"], r["verdict"]): r for r in db_rows}
        self.assertEqual(by_key[("r1", "FAIL")]["failure_class"], "rate_limited")
        self.assertIsNone(by_key[("r1", "FAIL")]["model_attempt"])
        self.assertEqual(by_key[("r1", "PASS")]["model_attempt"], 1)
        self.assertAlmostEqual(by_key[("r1", "PASS")]["cost_usd"], 0.0123)
        self.assertEqual(by_key[("a1", "PASS")]["run_family"], "audition")
        self.assertEqual(by_key[("r3", "FAIL")]["run_family"], "work", "legacy rows read as work")

    def test_db_path_equals_jsonl_path(self):
        ringer.rebuild_read_model_db(self.db, self.log)
        db_rows, _ = ringer.db_attempt_rows(self.db)
        jsonl_rows, _ = ringer.read_model_log_rows(self.log)
        for family in ("work", "audition", "all"):
            strip = lambda gs: sorted((json.dumps(g, sort_keys=True, default=str) for g in gs))
            self.assertEqual(strip(ringer.aggregate_model_log_rows(db_rows, family=family)),
                             strip(ringer.aggregate_model_log_rows(jsonl_rows, family=family)), family)
            self.assertEqual(strip(ringer.infra_only_models(db_rows, family=family)),
                             strip(ringer.infra_only_models(jsonl_rows, family=family)), family)

    def test_old_schema_rebuilds_on_sync(self):
        ringer.rebuild_read_model_db(self.db, self.log)
        with contextlib.closing(sqlite3.connect(self.db)) as conn:
            conn.execute("PRAGMA user_version = 3")
            conn.execute("UPDATE schema_version SET version = 3")
            conn.execute("UPDATE attempts SET failure_class = NULL")
            conn.commit()
        result = ringer.sync_read_model_db(self.db, self.log)
        self.assertTrue(result.rebuilt, "a sync over schema 3 must rebuild")
        with contextlib.closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 4)
            self.assertEqual(conn.execute("SELECT count(*) FROM attempts WHERE failure_class = 'rate_limited'").fetchone()[0], 1)


class ModelsCliFamily(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.log = self.dir / "runs.jsonl"
        self.log.write_text(json.dumps(row("a1", "v", "PASS", ma=1, family="audition", model="openrouter/acme/auditioned-1")) + "\n"
                            + json.dumps(row("w1", "t", "PASS", ma=1, model="openrouter/acme/worker-1")) + "\n")
        self.cfg = self.dir / "config.toml"
        self.cfg.write_text(f'state_dir = "{self.dir}/state"\n[eval]\nbackend = "jsonl"\njsonl_path = "{self.log}"\n')

    def tearDown(self):
        self.tmp.cleanup()

    def models(self, *args):
        env = dict(os.environ, RINGER_NO_SELF_UPDATE="1", RINGER_HOME=str(self.dir / "home"))
        return subprocess.run([sys.executable, "-B", str(ROOT / "ringer.py"), "--config", str(self.cfg), "models",
                               "--log", str(self.log), *args], capture_output=True, text=True, env=env, timeout=60)

    def test_default_is_work(self):
        r = self.models()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("worker-1", r.stdout)
        self.assertNotIn("auditioned-1", r.stdout)

    def test_audition_family(self):
        r = self.models("--family", "audition")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("auditioned-1", r.stdout)
        self.assertNotIn("worker-1", r.stdout)

    def test_bad_family(self):
        self.assertNotEqual(self.models("--family", "weekend").returncode, 0)


if __name__ == "__main__":
    unittest.main()
