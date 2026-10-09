#!/usr/bin/env python3
"""Acceptance tests: infrastructure failures appear in model detail on every
scoreboard surface, primary columns unchanged (openspec change
trusted-multi-model-tracking, spec model-scoreboard "Infrastructure failures in
model detail"; task 3.6).

Contract under test:
  /api/models payload (build_models_api_payload): every group and rollup item
  has "infra" {class: count}; payload has "infra_only" [{engine, model,
  model_display?, infra}]; "columns" == list(MODEL_SCOREBOARD_COLUMNS).
  CLI `models`: after the table, a section headed "Infrastructure failures"
  lists each model with infra counts as "<class> ×<n>" (× or x), including
  infrastructure-only models; no section when there are none.
  HTML scoreboard (`models --html PATH`): the model's detail shows the same
  "<class> ×<n>" text; the ranked table's header cells are unchanged.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ringer  # noqa: E402

GLM = "openrouter/z-ai/glm-5.2"
KIMI = "openrouter/moonshotai/kimi-k2.7-code"
_t = [0]


def row(run, key, verdict, *, model=GLM, cls=None, ma=1):
    _t[0] += 1
    return {"run_id": run, "task_key": key, "verdict": verdict, "model": model, "worker_engine": "opencode",
            "task_type": "code-fix", "failure_class": cls, "model_attempt": ma if cls in (None, "model") else None,
            "run_family": "work", "retry": False, "logged_at": f"2026-10-09T01:00:{_t[0]:02d}+00:00",
            "worker_tokens": 100, "duration_ms": 100, "notes": ""}


INFRA = re.compile(r"(\w+)\s*[×x]\s*(\d+)")


class InfraDisplay(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.log, self.cfg, self.home = d / "runs.jsonl", d / "config.toml", d / "home"
        rows = [row("r1", "a", "FAIL", cls="rate_limited"), row("r1", "a", "FAIL", cls="rate_limited"),
                row("r1", "a", "PASS"), row("r2", "b", "FAIL", cls="rate_limited"), row("r2", "b", "PASS"),
                row("r3", "c", "FAIL", cls="provider_error", model=KIMI), row("r3", "c", "FAIL", cls="provider_error", model=KIMI)]
        self.log.write_text("".join(json.dumps(r) + "\n" for r in rows))
        self.cfg.write_text(f'state_dir = "{d}/state"\n[eval]\nbackend = "jsonl"\njsonl_path = "{self.log}"\n')
        self.d = d

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args):
        env = dict(os.environ, RINGER_NO_SELF_UPDATE="1", RINGER_HOME=str(self.home))
        r = subprocess.run([sys.executable, "-B", str(ROOT / "ringer.py"), "--config", str(self.cfg), "models",
                            "--log", str(self.log), *args], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def test_api_payload(self):
        payload = ringer.build_models_api_payload(log_path=self.log, db_path=self.d / "ringer.db")
        self.assertEqual(payload["columns"], list(ringer.MODEL_SCOREBOARD_COLUMNS))
        glm = [g for g in payload["groups"] if g["model"] == GLM]
        self.assertEqual(len(glm), 1)
        self.assertEqual(glm[0]["infra"], {"rate_limited": 3})
        for item in payload["rollup"]:
            self.assertIn("infra", item)
        only = payload["infra_only"]
        self.assertEqual([o["model"] for o in only], [KIMI])
        self.assertEqual(only[0]["infra"], {"provider_error": 2})

    def test_cli_section(self):
        out = self.cli()
        self.assertIn("Infrastructure failures", out)
        section = out.split("Infrastructure failures", 1)[1]
        found = {(m.group(1), int(m.group(2))) for m in INFRA.finditer(section)}
        self.assertIn(("rate_limited", 3), found)
        self.assertIn(("provider_error", 2), found)
        self.assertRegex(section, r"(?i)kimi")

    def test_cli_no_section_without_infra(self):
        self.log.write_text(json.dumps(row("r9", "z", "PASS")) + "\n")
        self.assertNotIn("Infrastructure failures", self.cli())

    def test_primary_table_header_unchanged(self):
        out = self.cli()
        header = next(l for l in out.splitlines() if l.startswith("Model ") and "|" in l)
        self.assertEqual([c.strip() for c in header.split("|")], list(ringer.MODEL_SCOREBOARD_COLUMNS))

    def test_html_detail(self):
        target = self.d / "scoreboard.html"
        self.cli("--html", str(target))
        html = target.read_text()
        found = {(m.group(1), int(m.group(2))) for m in INFRA.finditer(re.sub(r"<[^>]+>", " ", html))}
        self.assertIn(("rate_limited", 3), found)
        self.assertIn(("provider_error", 2), found)


if __name__ == "__main__":
    unittest.main()
