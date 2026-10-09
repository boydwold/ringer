"""Offline audition planning and runner tests; no providers or network calls."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import os
import shlex
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import ringer


def model(mid, price=1, **extra):
    return dict(id=mid, modality="text->text", context_length=32000,
                prompt_per_m=price, completion_per_m=price,
                supported_parameters=["tools"], **extra)


class AuditionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.task = ringer.AuditionTask("fix", self.root / "set" / "fix", "code-fix", "Fix it", ("out.txt",), 10000)
        self.env = patch.dict(os.environ, RINGER_HOME=str(self.root / "home"), RINGER_NO_SELF_UPDATE="1")
        self.env.start()
        self.addCleanup(self.env.stop)

    def plan(self, models, rows=(), tasks=None, budget="100", spent="0", max_models=5):
        return ringer.plan_auditions(tasks or [self.task], models, list(rows),
                                    budget=Decimal(budget), spent=Decimal(spent), max_models=max_models)

    def test_defaults_and_missing_optional_config(self):
        cfg = ringer.load_audition_config(None)
        self.assertIsNone(cfg.weekly_budget_usd)
        self.assertIsNone(cfg.credential_file)
        self.assertEqual((cfg.max_models, cfg.token_estimate, cfg.concurrency, cfg.engine, cfg.check_timeout_s),
                         (5, 40000, 2, "opencode", 120))
        path = self.root / "config.toml"
        path.write_text("")
        self.assertEqual(ringer.AppConfig.load(path).audition, cfg)

    def test_config_validation(self):
        for raw in ([], 1, "bad"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                ringer.load_audition_config(raw)
        for key in ("max_models", "token_estimate", "concurrency", "check_timeout_s"):
            for value in (0, -1, True, 1.2, "2"):
                with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, key):
                    ringer.load_audition_config({key: value})
        for value in (0, -1, True, float("nan"), float("inf"), "2"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "weekly_budget_usd"):
                ringer.load_audition_config({"weekly_budget_usd": value})
        for key in ("engine", "credential_file", "set_dir"):
            for value in ("", [], False):
                with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, key):
                    ringer.load_audition_config({key: value})

    def test_order_evidence_then_price_and_canonical_task_types(self):
        rows = [dict(model="openrouter/acme/seen", run_family="audition", task_type="code-review"),
                dict(model="acme/done", run_family="audition", task_type="code-fix"),
                dict(model="acme/work", run_family="work", task_type="code-fix")]
        models = [model("acme/seen", 0), model("acme/new", 2), model("acme/work", 1), model("acme/done")]
        planned, _ = self.plan(models, rows)
        self.assertEqual([entry.model for entry in planned], ["acme/work", "acme/new", "acme/seen"])
        self.assertEqual(len(self.plan(models, rows, max_models=2)[0]), 2)

    def test_all_tasks_of_missing_type_selected(self):
        other = replace(self.task, key="fix-two")
        review = replace(self.task, key="review", task_type="code-review")
        rows = [dict(model="acme/a", run_family="audition", task_type="code-review", failure_class="provider_error")]
        planned, _ = self.plan([model("acme/a")], rows, tasks=[self.task, other, review])
        self.assertEqual([entry.task.key for entry in planned], ["fix", "fix-two"])

    def test_filters_invalid_catalog_entries(self):
        good = model("good")
        invalid = [dict(good, id="bad-tools", supported_parameters=[]),
                   dict(good, id="bad-context", context_length=31999),
                   dict(good, id="bad-text", modality="text+image->text"),
                   dict(good, id="variable", variable_pricing=True),
                   dict(good, id="unknown", pricing_unknown=True),
                   dict(good, id="nan", prompt_per_m=float("nan")),
                   dict(good, id="missing-price", completion_per_m=None)]
        legacy = dict(good, id="legacy")
        legacy.pop("supported_parameters")
        self.assertEqual([entry.model for entry in self.plan(invalid + [good, legacy])[0]], ["good", "legacy"])

    def test_latest_recent_policy_row_and_canonical_prefix(self):
        now = datetime.now(timezone.utc)
        def row(mid, days, failure):
            return dict(model=mid, logged_at=(now - timedelta(days=days)).isoformat(), failure_class=failure)
        rows = [row("openrouter/blocked", 1, "provider_policy"), row("recovered", 2, "provider_policy"),
                row("openrouter/recovered", 1, None), row("expired", 8, "provider_policy")]
        self.assertEqual([entry.model for entry in self.plan([model(m) for m in ("blocked", "recovered", "expired")], rows)[0]],
                         ["expired", "recovered"])

    def test_median_cost_budget_boundary_and_free(self):
        rows = [dict(model="openrouter/paid", run_family="audition", task_type="other", cost_usd=cost)
                for cost in (None, 0.1, 0.3, 2, 0.5)]
        planned, skipped = self.plan([model("paid"), model("free", 10, free=True)], rows, budget="0.5", spent="0.1")
        self.assertEqual([(entry.model, entry.estimate) for entry in planned], [("free", Decimal(0)), ("paid", Decimal("0.4"))])
        self.assertEqual(skipped, [])
        self.assertEqual(len(self.plan([model("paid")], rows, budget="0.499", spent="0.1")[1]), 1)

    def test_token_split_and_per_task_fallback(self):
        planned, _ = self.plan([dict(model("paid", 0.5), completion_per_m=1.5)])
        self.assertEqual(planned[0].estimate, Decimal("0.0065"))
        config = self.make_config()
        task_path = self.task.directory / "task.toml"
        task_path.write_text('key="fix"\ntask_type="code-fix"\nexpect_files=["out.txt"]\n')
        self.assertEqual(ringer.load_audition_tasks(config.audition)[0].token_estimate, 40000)

    def test_ledger_week_and_corruption(self):
        path = self.root / "ledger"
        self.assertEqual(ringer.audition_spent(path, "2026-W41"), 0)
        path.write_text('\n'.join(json.dumps(dict(week=week, cost_usd=cost))
                                  for week, cost in (("2026-W40", 99), ("2026-W41", 0.2), ("2026-W41", 0.3))))
        self.assertEqual(ringer.audition_spent(path, "2026-W41"), Decimal("0.5"))
        path.write_text('{broken')
        with self.assertRaisesRegex(ValueError, "ledger"):
            ringer.audition_spent(path, "2026-W41")

    def test_manifest_absolute_python_and_quoted_paths(self):
        plan, _ = self.plan([model("Acme/A.v2")])
        config = replace(ringer.AuditionConfig(), set_dir=self.root / "private set")
        manifest = ringer.audition_manifest(plan, config, self.root / "work dir")
        task = manifest.tasks[0]
        self.assertEqual((manifest.run_name, manifest.family), ("audition", "audition"))
        self.assertEqual((task.key, task.model, task.max_attempts), ("fix--acme-a-v2", "openrouter/Acme/A.v2", 1))
        command = shlex.split(task.check)
        self.assertEqual(command[1:5], [str(manifest.workdir / task.key), "120", os.path.realpath(sys.executable), "-I"])
        self.assertGreater(task.check_timeout_s, config.check_timeout_s)

    def test_environment_merge_and_restore_even_on_failure(self):
        original = json.dumps({"provider": {"openrouter": {"options": {"baseURL": "local", "apiKey": "old"}}}, "theme": "dark"})
        with patch.dict(os.environ, RINGER_SANDBOX_HIDE="/old", OPENCODE_CONFIG_CONTENT=original):
            with self.assertRaises(RuntimeError):
                with ringer.audition_environment(replace(ringer.AuditionConfig(), set_dir=self.root), "test-secret"):
                    self.assertEqual(os.environ["RINGER_SANDBOX_HIDE"], f"/old:{self.root}")
                    content = json.loads(os.environ["OPENCODE_CONFIG_CONTENT"])
                    self.assertEqual(content["provider"]["openrouter"]["options"], {"baseURL": "local", "apiKey": "test-secret"})
                    self.assertEqual(content["theme"], "dark")
                    raise RuntimeError()
            self.assertEqual(os.environ["OPENCODE_CONFIG_CONTENT"], original)
            self.assertEqual(os.environ["RINGER_SANDBOX_HIDE"], "/old")

    def test_invalid_environment_does_not_disclose_secret(self):
        with patch.dict(os.environ, OPENCODE_CONFIG_CONTENT='{"secret":"test-secret", "provider": null}'):
            with self.assertRaises(ValueError) as error:
                with ringer.audition_environment(ringer.AuditionConfig(), "test-secret"):
                    self.fail("must reject invalid JSON structure")
            self.assertNotIn("test-secret", str(error.exception))

    def make_config(self):
        (self.task.directory / "fixture").mkdir(parents=True)
        (self.task.directory / "fixture" / "seed.txt").write_text("seed")
        (self.task.directory / "check.py").write_text("raise SystemExit(0)")
        (self.task.directory / "spec.md").write_text("Fix the bounded fixture.")
        (self.task.directory / "task.toml").write_text('key="fix"\ntask_type="code-fix"\nexpect_files=["out.txt"]\ntoken_estimate=10000\n')
        credential = self.root / "key"
        credential.write_text(" test-secret \n")
        path = self.root / "config.toml"
        path.write_text(f'state_dir="{self.root / "state"}"\n[artifact]\nenabled=false\n[eval]\nbackend="jsonl"\njsonl_path="{self.root / "rows.jsonl"}"\n')
        config = ringer.AppConfig.load(path)
        return replace(config, audition=ringer.AuditionConfig(weekly_budget_usd=10, credential_file=credential,
                       engine="codex", set_dir=self.task.directory.parent, concurrency=2))

    def args(self, **changes):
        return argparse.Namespace(dry_run=changes.get("dry_run", False), max_models=None,
                                  catalog_file=self.root / "catalog.json", no_refresh=changes.get("no_refresh", True))

    def test_refresh_failure_falls_back_and_dry_run_writes_no_ledger(self):
        config = self.make_config()
        args = self.args(dry_run=True, no_refresh=False)
        args.catalog_file.write_text(json.dumps([model("acme/a")]))
        out = io.StringIO()
        with patch.object(ringer, "refresh_openrouter_catalog", side_effect=OSError("offline")) as refresh, contextlib.redirect_stdout(out):
            self.assertEqual(ringer.run_audition_command(config, args), 0)
        refresh.assert_called_once()
        self.assertIn("falling back", out.getvalue())
        self.assertIn("PLAN fix--acme-a openrouter/acme/a est=$0.010000", out.getvalue())
        self.assertFalse((ringer.ringer_home() / "audition-spend.jsonl").exists())
        self.assertFalse((ringer.ringer_home() / "auditions").exists())
        self.assertNotIn("test-secret", out.getvalue())

    def test_missing_credential_refused(self):
        config = self.make_config()
        config.audition.credential_file.unlink()
        with self.assertRaisesRegex(ValueError, "credential_file"):
            ringer.run_audition_command(config, self.args())

    def test_real_runner_lifecycle_fixture_env_ledger_and_summary_without_network(self):
        config = self.make_config()
        args = self.args()
        args.catalog_file.write_text(json.dumps([model("acme/a")]))
        async def worker(runner, runtime, spec, attempt):
            self.assertTrue(ringer.read_active_runs())
            self.assertEqual(runtime.taskdir.joinpath("seed.txt").read_text(), "seed")
            self.assertEqual(json.loads(os.environ["OPENCODE_CONFIG_CONTENT"])["provider"]["openrouter"]["options"]["apiKey"], "test-secret")
            runtime.taskdir.joinpath("out.txt").write_text("done")
            return ringer.WorkerResult(0, False, 100, cost_usd=0.02)
        out = io.StringIO()
        with patch.object(ringer, "preflight_engine_bins"), patch.object(ringer.RingerRunner, "_run_worker", worker), \
             patch.object(ringer.Verifier, "verify", AsyncMock(return_value=ringer.VerifyResult(True, 0, False, "PASS", ()))), \
             contextlib.redirect_stdout(out):
            self.assertEqual(ringer.run_audition_command(config, args), 0)
        self.assertFalse(ringer.read_active_runs())
        rows, _ = ringer.read_model_log_rows(config.eval.jsonl_path)
        self.assertEqual((len(rows), rows[0]["run_family"]), (1, "audition"))
        ledger = json.loads((ringer.ringer_home() / "audition-spend.jsonl").read_text())
        self.assertEqual((ledger["cost_usd"], ledger["estimated"]), (0.02, False))
        self.assertIn("code-fix: PASS 1 FAIL 0", out.getvalue())
        self.assertNotIn("test-secret", out.getvalue())

    def test_batches_stop_on_quota_and_use_estimate_when_cost_missing(self):
        self.run_batches("quota_exhausted", None, expected_rows=2)

    def test_batches_stop_when_actual_cost_exceeds_budget(self):
        self.run_batches(None, 6, expected_rows=2)

    def test_batches_complete_and_record_each_task_once(self):
        self.run_batches(None, 0.02, expected_rows=3)

    def test_cancelled_batch_accounts_for_completed_tasks(self):
        config = self.make_config()
        plan, _ = self.plan([model(f"acme/{n}") for n in range(3)])
        manifest = ringer.audition_manifest(plan, config.audition, self.root / "work")
        ledger = self.root / "spend.jsonl"
        runner = ringer.AuditionRunner(manifest, config=config, identity="test", dashboard_enabled=False, plan=plan, ledger=ledger)
        async def fake_task(runtime):
            if runtime.task.key == plan[0].key:
                runner.logger.log_attempt(dict(run_id=runner.run_id, task_key=runtime.task.key, model=runtime.task.model,
                                              cost_usd=0.02, failure_class=None))
            else:
                raise asyncio.CancelledError()
        with patch.object(runner, "_run_task", fake_task), self.assertRaises(asyncio.CancelledError):
            asyncio.run(runner._run_tasks())
        runner.logger.close()
        rows = [json.loads(line) for line in ledger.read_text().splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["task_key"], plan[0].key)

    def test_summary_excludes_infrastructure_from_model_failures(self):
        rows = [dict(model="a", task_type="code-fix", verdict="FAIL", failure_class="provider_error"),
                dict(model="b", task_type="code-fix", verdict="FAIL", failure_class="model"),
                dict(model="c", task_type="code-fix", verdict="PASS", failure_class=None)]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            ringer.print_audition_summary(rows, self.root / "spend.jsonl", Decimal(10))
        self.assertIn("code-fix: PASS 1 FAIL 1", output.getvalue())
        self.assertIn("provider_error=1", output.getvalue())
        self.assertIn("models tried (3)", output.getvalue())

    def run_batches(self, failure, cost, expected_rows):
        config = self.make_config()
        plan, _ = self.plan([model(f"acme/{n}") for n in range(3)])
        manifest = ringer.audition_manifest(plan, config.audition, self.root / "work")
        ledger = self.root / "spend.jsonl"
        runner = ringer.AuditionRunner(manifest, config=config, identity="test", dashboard_enabled=False, plan=plan, ledger=ledger)
        active = 0
        peak = 0
        async def fake_task(runtime):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0)
            runner.logger.log_attempt(dict(run_id=runner.run_id, task_key=runtime.task.key, model=runtime.task.model,
                                          cost_usd=cost, failure_class=failure, task_type="code-fix", run_family="audition"))
            active -= 1
        with patch.object(runner, "_run_task", fake_task), contextlib.redirect_stdout(io.StringIO()):
            asyncio.run(runner._run_tasks())
        runner.logger.close()
        rows = [json.loads(line) for line in ledger.read_text().splitlines()]
        self.assertEqual(len(rows), expected_rows)
        self.assertEqual(peak, 2)
        self.assertEqual(len({row["task_key"] for row in rows}), expected_rows)
        self.assertTrue(all(row["estimated"] == (cost is None) for row in rows))
        self.assertEqual(rows[0]["cost_usd"], 0.01 if cost is None else cost)


if __name__ == "__main__":
    unittest.main()
