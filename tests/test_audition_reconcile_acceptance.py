#!/usr/bin/env python3
"""Acceptance tests: audition spend reconciled with the provider's key usage
(openspec change trusted-multi-model-tracking, spec model-auditions "Spend
matches the provider"; task 9.2).

Contract under test:
  [audition] usage_url (default "https://openrouter.ai/api/v1/key"): GET with
  "Authorization: Bearer <audition key>", JSON {"data": {"usage": <float USD>}}.
  A real (non-dry) audition run reads usage before and after; when both reads
  succeed it appends one ledger line {"week", "run_id", "kind": "reconciliation",
  "cost_usd": (after - before) - <sum of this run's per-task ledger costs>,
  "provider_delta": after - before}; the week's spend then equals the provider
  delta. When a read fails, no reconciliation line is written and the summary
  says spend is "unreconciled"; the run still finishes normally.
  The summary prints the provider-reported spend when reconciled.
  usage_url = "" turns reconciliation off (no network call; summary says
  "unreconciled").
"""
from __future__ import annotations

import datetime as dt
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINUX_BWRAP = sys.platform.startswith("linux") and shutil.which("bwrap") is not None
CHECK = "import sys, pathlib\nsys.exit(0 if pathlib.Path('out.txt').read_text().strip() == 'done' else 1)\n"


def week_key():
    y, w, _ = dt.datetime.now().astimezone().isocalendar()
    return f"{y}-W{w:02d}"


class UsageStub:
    def __init__(self, values):
        self.values = list(values)
        self.auth_headers = []
        self.paths = []
        stub = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                stub.auth_headers.append(self.headers.get("Authorization", ""))
                stub.paths.append(self.path)
                usage = stub.values.pop(0) if stub.values else stub.values_last
                body = json.dumps({"data": {"usage": usage, "limit": 25}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.values_last = values[-1]
        self.server = http.server.HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/api/v1/key"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@unittest.skipUnless(LINUX_BWRAP, "audition checks run in the Linux check sandbox")
class Reconcile(unittest.TestCase):
    def setUp(self):
        base = Path.home() / ".cache" / "ringer-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        d = self.d = Path(self.tmp.name)
        self.home = d / "home"
        self.home.mkdir()
        self.log = d / "runs.jsonl"
        self.log.write_text("")
        t = d / "set" / "tiny-fix"
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
        self.catalog.write_text(json.dumps({"fetched_at": "2026-10-09T00:00:00+00:00", "models": [{
            "id": "acme/alpha", "name": "alpha", "context_length": 128000, "modality": "text->text",
            "variable_pricing": False, "pricing_unknown": False, "free": False, "prompt_per_m": 0.5,
            "completion_per_m": 1.5, "pricing": {}, "fetched_at": "2026-10-09T00:00:00+00:00",
            "supported_parameters": ["tools"]}]}))

    def tearDown(self):
        self.tmp.cleanup()

    def config(self, usage_url):
        body = "printf done > out.txt; echo '{\"type\":\"step_finish\",\"part\":{\"tokens\":{\"total\":1000},\"cost\":0.01}}'"
        (self.d / "config.toml").write_text("\n".join([
            f'state_dir = "{self.d}/state"', "dashboard_port_base = 19387", "", "[eval]", 'backend = "jsonl"',
            f'jsonl_path = "{self.log}"', "", "[engines.fake]", 'bin = "/bin/sh"',
            f"args_template = {json.dumps(['-c', body])}", "sandbox_args = []", "full_access_args = []",
            'failure_profile = "opencode"', 'token_aggregate = "sum"', "token_regex = '\"tokens\":\\{\"total\":([0-9]+)'",
            "cost_regex = '\"cost\":([0-9.]+)'", "", "[audition]", 'engine = "fake"', f'set_dir = "{self.d}/set"',
            "weekly_budget_usd = 10.0", f'credential_file = "{self.cred}"', "concurrency = 1", f'usage_url = "{usage_url}"', ""]))

    def audition(self):
        env = dict(os.environ, RINGER_HOME=str(self.home), RINGER_NO_SELF_UPDATE="1", PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, "-B", str(ROOT / "ringer.py"), "--config", str(self.d / "config.toml"),
                               "audition", "--catalog-file", str(self.catalog), "--no-refresh"],
                              cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)

    def ledger(self):
        p = self.home / "audition-spend.jsonl"
        return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []

    def test_reconciliation_line_matches_provider(self):
        stub = UsageStub([1.000, 1.050])
        try:
            self.config(stub.url)
            r = self.audition()
        finally:
            stub.close()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # Only requests to the key endpoint are ours. Unauthenticated GET / probes
        # from elsewhere on the host sometimes reach this random local port.
        ours = [h for h, path in zip(stub.auth_headers, stub.paths) if path == "/api/v1/key"]
        self.assertEqual(len(ours), 2, f"usage read before and after; saw {stub.paths}")
        self.assertTrue(all(h == "Bearer sk-or-AUDITION-TEST-KEY" for h in ours), "uses the audition key")
        led = self.ledger()
        rec = [x for x in led if x.get("kind") == "reconciliation"]
        self.assertEqual(len(rec), 1, led)
        self.assertAlmostEqual(rec[0]["cost_usd"], 0.04, places=6)
        self.assertAlmostEqual(rec[0]["provider_delta"], 0.05, places=6)
        self.assertEqual(rec[0]["week"], week_key())
        week_total = sum(x["cost_usd"] for x in led if x.get("week") == week_key())
        self.assertAlmostEqual(week_total, 0.05, places=6)
        self.assertNotIn("unreconciled", r.stdout.lower())
        self.assertNotIn("sk-or-AUDITION-TEST-KEY", r.stdout + r.stderr)

    def test_unavailable_usage_marks_unreconciled(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        self.config(f"http://127.0.0.1:{port}/api/v1/key")
        r = self.audition()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("unreconciled", r.stdout.lower())
        self.assertEqual([x for x in self.ledger() if x.get("kind") == "reconciliation"], [])
        self.assertEqual(len([x for x in self.ledger() if x.get("kind") != "reconciliation"]), 1)


if __name__ == "__main__":
    unittest.main()
