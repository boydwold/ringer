"""Provider reconciliation coverage; every HTTP request is mocked."""
from __future__ import annotations

import argparse
import contextlib
import http.client
import io
import json
import os
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import ringer


class UsageTests(unittest.TestCase):
    def test_config_default_override_disabled_and_validation(self):
        for raw in (None, {}):
            self.assertEqual(ringer.load_audition_config(raw).usage_url,
                             "https://openrouter.ai/api/v1/key")
        for url in ("", "http://localhost/usage"):
            self.assertEqual(ringer.load_audition_config({"usage_url": url}).usage_url, url)
        for value in (None, False, 2, [], {}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "usage_url"):
                ringer.load_audition_config({"usage_url": value})

    def test_request_and_numeric_usage(self):
        for value in (0, 2, 1.038, -1):
            with self.subTest(value=value), patch.object(ringer.urllib.request.OpenerDirector, "open",
                    return_value=io.BytesIO(json.dumps({"data": {"usage": value}}).encode())) as request:
                self.assertEqual(ringer.read_audition_usage("https://provider.invalid/key", "secret"),
                                 Decimal(str(value)))
                req = request.call_args.args[0]
                self.assertEqual(req.full_url, "https://provider.invalid/key")
                self.assertEqual(req.get_method(), "GET")
                self.assertEqual(req.get_header("Authorization"), "Bearer secret")
                self.assertEqual(request.call_args.kwargs, {"timeout": 15})

    def test_invalid_response_and_errors_are_unavailable_without_disclosure(self):
        bodies = [b"broken", b"[]", b"{}", b'{"data":null}']
        bodies += [json.dumps({"data": {"usage": value}}).encode()
                   for value in (None, True, "1.25", [], {}, float("nan"), float("inf"))]
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            for body in bodies:
                with self.subTest(body=body), patch.object(ringer.urllib.request.OpenerDirector, "open",
                                                          return_value=io.BytesIO(body)):
                    self.assertIsNone(ringer.read_audition_usage("https://provider.invalid/key", "secret"))
            for error in (TimeoutError("secret"), OSError("secret"), ValueError("secret")):
                with patch.object(ringer.urllib.request.OpenerDirector, "open", side_effect=error):
                    self.assertIsNone(ringer.read_audition_usage("https://provider.invalid/key", "secret"))
        self.assertEqual(output.getvalue(), "")

    def test_disabled_does_not_request(self):
        with patch.object(ringer.urllib.request.OpenerDirector, "open") as request:
            self.assertIsNone(ringer.read_audition_usage("", "secret"))
        request.assert_not_called()

    def test_authorization_on_http_wire(self):
        # Exercise urllib and HTTP serialization; mocking urlopen alone cannot
        # detect a dropped/replaced header between Request and the server.
        body = b'{"data":{"usage":1.05}}'
        sock = MagicMock()
        sock.makefile.return_value = io.BytesIO(
            b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode()
            + b"\r\n\r\n" + body)
        with patch.object(ringer.socket, "create_connection", return_value=sock):
            usage = ringer.read_audition_usage("http://127.0.0.1:34567/api/v1/key", "test-secret")
        self.assertEqual(usage, Decimal("1.05"))
        wire = b"".join(call.args[0] for call in sock.sendall.call_args_list)
        request_line, headers = wire.split(b"\r\n", 1)
        self.assertEqual(request_line, b"GET /api/v1/key HTTP/1.1")
        parsed = http.client.parse_headers(io.BytesIO(headers))
        self.assertEqual(parsed.get_all("Authorization"), ["Bearer test-secret"])

    def test_usage_does_not_inherit_global_opener_authentication(self):
        class AmbientAuth(ringer.urllib.request.BaseHandler):
            def http_request(self, request):
                request.add_header("Authorization", "Bearer other-key")
                return request

        body = b'{"data":{"usage":1.05}}'
        sock = MagicMock()
        sock.makefile.return_value = io.BytesIO(
            b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode()
            + b"\r\n\r\n" + body)
        ambient = ringer.urllib.request.build_opener(AmbientAuth())
        with patch.object(ringer.urllib.request, "_opener", ambient), \
             patch.object(ringer.socket, "create_connection", return_value=sock):
            usage = ringer.read_audition_usage("http://127.0.0.1:34567/api/v1/key", "test-secret")
        self.assertEqual(usage, Decimal("1.05"))
        wire = b"".join(call.args[0] for call in sock.sendall.call_args_list)
        parsed = http.client.parse_headers(io.BytesIO(wire.split(b"\r\n", 1)[1]))
        self.assertEqual(parsed.get_all("Authorization"), ["Bearer test-secret"])


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.ledger = self.root / "audition-spend.jsonl"
        self.week = ringer.audition_week()

    def write_rows(self, rows):
        self.ledger.write_text("".join(json.dumps(row) + "\n" for row in rows))

    def read_rows(self):
        return [json.loads(line) for line in self.ledger.read_text().splitlines()]

    def test_adjustments_include_zero_negative_and_only_this_runs_recorded_cost(self):
        for delta in ("0.038", "0.023", "0.010", "-0.005"):
            with self.subTest(delta=delta):
                self.write_rows([
                    dict(week=self.week, run_id="earlier", cost_usd=2),
                    dict(week="2000-W01", run_id="old", cost_usd=10),
                    dict(week=self.week, run_id="run", cost_usd=0.020),
                    dict(week=self.week, run_id="run", cost_usd=0.003, estimated=True),
                ])
                ringer.reconcile_audition_spend(self.ledger, "run", Decimal(delta))
                row = self.read_rows()[-1]
                self.assertEqual(row, dict(week=self.week, run_id="run", kind="reconciliation",
                                          cost_usd=float(Decimal(delta) - Decimal("0.023")),
                                          provider_delta=float(delta)))
                self.assertEqual(ringer.audition_spent(self.ledger, self.week), Decimal(2) + Decimal(delta))

    def test_invalid_task_costs_still_rejected(self):
        for cost, kind in ((-1, "task"), (True, "reconciliation"), (float("nan"), "reconciliation")):
            self.write_rows([dict(week=self.week, kind=kind, cost_usd=cost)])
            with self.subTest(cost=cost), self.assertRaisesRegex(ValueError, "ledger"):
                ringer.audition_spent(self.ledger, self.week)

    def make_config(self, usage_url="https://provider.invalid/key"):
        task = self.root / "set" / "fix"
        (task / "fixture").mkdir(parents=True)
        (task / "fixture" / "seed.txt").write_text("seed")
        (task / "check.py").write_text("raise SystemExit(0)")
        (task / "spec.md").write_text("Fix the fixture.")
        (task / "task.toml").write_text('key="fix"\ntask_type="code-fix"\nexpect_files=["out.txt"]\n')
        credential = self.root / "key"
        credential.write_text("test-secret\n")
        config_path = self.root / "config.toml"
        config_path.write_text(f'state_dir="{self.root / "state"}"\n[artifact]\nenabled=false\n'
                               f'[eval]\nbackend="jsonl"\njsonl_path="{self.root / "rows.jsonl"}"\n')
        config = ringer.AppConfig.load(config_path)
        return replace(config, audition=ringer.AuditionConfig(
            weekly_budget_usd=10, credential_file=credential, engine="codex",
            set_dir=task.parent, usage_url=usage_url))

    def run_command(self, responses, *, disabled=False, dry_run=False, cost=0.023, exit_code=0):
        config = self.make_config("" if disabled else "https://provider.invalid/key")
        catalog = self.root / "catalog.json"
        catalog.write_text(json.dumps([dict(id="acme/model", modality="text->text", context_length=32000,
                                           prompt_per_m=1, completion_per_m=1, supported_parameters=["tools"])]))
        args = argparse.Namespace(dry_run=dry_run, max_models=None, catalog_file=catalog, no_refresh=True)
        events = []
        def usage(*a, **kw):
            events.append("usage")
            self.assertEqual(a[0].get_header("Authorization"), "Bearer test-secret")
            response = responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return io.BytesIO(json.dumps({"data": {"usage": response}}).encode())
        planner = ringer.plan_auditions
        def plan(*a, **kw):
            events.append("plan")
            return planner(*a, **kw)
        async def worker(runner, runtime, spec, attempt):
            events.append("worker")
            runtime.taskdir.joinpath("out.txt").write_text("done")
            return ringer.WorkerResult(exit_code, False, 100, cost_usd=cost)
        output = io.StringIO()
        with patch.dict(os.environ, RINGER_HOME=str(self.root), RINGER_NO_SELF_UPDATE="1"), \
             patch.object(ringer.urllib.request.OpenerDirector, "open", side_effect=usage) as request, \
             patch.object(ringer, "plan_auditions", side_effect=plan), \
             patch.object(ringer, "preflight_engine_bins"), \
             patch.object(ringer.RingerRunner, "_run_worker", worker), \
             patch.object(ringer.Verifier, "verify", AsyncMock(return_value=ringer.VerifyResult(
                 exit_code == 0, exit_code, False, "PASS" if exit_code == 0 else "FAIL", ()))), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            status = ringer.run_audition_command(config, args)
        self.assertNotIn("test-secret", output.getvalue())
        if self.ledger.exists():
            self.assertNotIn("test-secret", self.ledger.read_text())
        return status, output.getvalue(), events, request.call_count

    def test_run_reconciles_after_workers_and_before_summary(self):
        status, output, events, calls = self.run_command([1, 1.038])
        self.assertEqual(status, 0)
        self.assertEqual(events, ["usage", "plan", "worker", "usage"])
        self.assertEqual(calls, 2)
        self.assertEqual(len(self.read_rows()), 2)
        self.assertEqual(self.read_rows()[0]["run_id"], self.read_rows()[1]["run_id"])
        self.assertEqual(ringer.audition_spent(self.ledger, self.week), Decimal("0.038"))
        self.assertIn("provider-reported spend this run: $0.038000", output)
        self.assertIn("spent this week: $0.038000", output)
        self.assertNotIn("unreconciled", output)

    def test_before_failure_does_not_prevent_final_read_or_change_status(self):
        status, output, _, calls = self.run_command([OSError("test-secret"), 1.038])
        self.assertEqual((status, calls, len(self.read_rows())), (0, 2, 1))
        self.assertIn("(unreconciled): usage before run unavailable", output)

    def test_after_failure_preserves_task_spend(self):
        status, output, _, calls = self.run_command([1, TimeoutError("test-secret")])
        self.assertEqual((status, calls, len(self.read_rows())), (0, 2, 1))
        self.assertIn("(unreconciled): usage after run unavailable", output)

    def test_disabled_run_does_not_request(self):
        status, output, _, calls = self.run_command([], disabled=True)
        self.assertEqual((status, calls, len(self.read_rows())), (0, 0, 1))
        self.assertIn("(unreconciled): usage_url disabled", output)

    def test_dry_run_does_not_request_or_write(self):
        status, _, events, calls = self.run_command([], dry_run=True)
        self.assertEqual((status, calls, events), (0, 0, ["plan"]))
        self.assertFalse(self.ledger.exists())

    def test_failed_run_still_reconciles(self):
        status, output, _, calls = self.run_command([1, 1.038], exit_code=1)
        self.assertEqual((status, calls), (1, 2))
        self.assertIn("provider-reported spend this run: $0.038000", output)

    def test_zero_usage_delta_is_reconciled_and_credits_recorded_spend(self):
        status, output, _, _ = self.run_command([1, 1])
        self.assertEqual(status, 0)
        self.assertEqual(self.read_rows()[-1]["cost_usd"], -0.023)
        self.assertEqual(ringer.audition_spent(self.ledger, self.week), 0)
        self.assertIn("provider-reported spend this run: $0.000000", output)
        self.assertNotIn("unreconciled", output)

    def test_reconciliation_uses_estimated_ledger_cost_when_worker_omits_cost(self):
        status, _, _, _ = self.run_command([1, 1.038], cost=None)
        self.assertEqual(status, 0)
        rows = self.read_rows()
        self.assertTrue(rows[0]["estimated"])
        self.assertEqual(rows[0]["cost_usd"], 0.04)
        self.assertEqual(rows[1]["cost_usd"], -0.002)
        self.assertEqual(ringer.audition_spent(self.ledger, self.week), Decimal("0.038"))

    def test_usage_failure_preserves_failure_status(self):
        status, output, _, _ = self.run_command([1, OSError("test-secret")], exit_code=1)
        self.assertEqual(status, 1)
        self.assertEqual(len(self.read_rows()), 1)
        self.assertIn("(unreconciled)", output)


if __name__ == "__main__":
    unittest.main()
