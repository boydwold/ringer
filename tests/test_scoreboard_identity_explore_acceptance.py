#!/usr/bin/env python3
"""Acceptance tests: slug aliases, catalog tool support, exploration per task
type, and infra counts for dropped tasks (openspec change
trusted-multi-model-tracking, spec model-scoreboard, design D5; tasks 3.4-3.5).

Contract under test:
  registry entries may carry slug_aliases = ["<engine>:<slug>", ...];
  ModelIdentityRegistry.canonical_model_key(engine, model) -> canonical slug
  (alias -> registered slug; a slug without "openrouter/" -> the registered
  "openrouter/<slug>" for that engine; otherwise unchanged).
  aggregate_model_log_rows / aggregate_model_scoreboard_rows / infra_only_models
  accept registry=...; variants then group under the canonical slug.
  A group's "infra" counts every infrastructure row of that model/task
  type/family, including rows of tasks that had no model-counted attempt.
  normalize_catalog_model keeps "supported_parameters".
  models --explore --task-type T: untested = no model-counted WORK task of type T;
  entries listing supported_parameters without "tools" are never candidates
  (entries without the key are kept); a model whose latest row in the last 7
  days is provider_policy is printed under "blocked by provider policy";
  candidates that passed an audition task of type T come first.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ringer  # noqa: E402

GLM = "openrouter/z-ai/glm-5.2"
_t = [0]


def row(run, key, verdict, *, model=GLM, cls=None, ma=1, family="work", task_type="code-fix", engine="opencode", when=None):
    _t[0] += 1
    stamp = when or f"2026-10-09T00:{_t[0] // 60:02d}:{_t[0] % 60:02d}+00:00"
    return {"run_id": run, "task_key": key, "verdict": verdict, "model": model, "worker_engine": engine,
            "task_type": task_type, "failure_class": cls, "model_attempt": None if cls not in (None, "model") else ma,
            "run_family": family, "retry": False, "logged_at": stamp, "worker_tokens": 100, "duration_ms": 100, "notes": ""}


class Aliases(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.reg_path = Path(self.tmp.name) / "registry.toml"
        self.reg_path.write_text(
            '[engines.opencode.models."openrouter/z-ai/glm-5.2"]\n'
            'display = "GLM 5.2"\nlab = "Z.ai"\nconfidence = "verified"\nsource = "test"\nlast_verified = 2026-10-09\n'
            'slug_aliases = ["opencode:zai/glm-5.2"]\n'
        )
        self.reg = ringer.load_model_identity_registry(self.reg_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_canonical_key(self):
        self.assertEqual(self.reg.canonical_model_key("opencode", "zai/glm-5.2"), GLM)
        self.assertEqual(self.reg.canonical_model_key("opencode", "z-ai/glm-5.2"), GLM)
        self.assertEqual(self.reg.canonical_model_key("opencode", GLM), GLM)
        self.assertEqual(self.reg.canonical_model_key("opencode", "zhipu/glm-5.2"), "zhipu/glm-5.2")
        self.assertEqual(self.reg.canonical_model_key("codex", "zai/glm-5.2"), "zai/glm-5.2", "aliases are per engine")

    def test_variants_group_together(self):
        rows = [row("r1", "a", "PASS"), row("r2", "b", "PASS", model="z-ai/glm-5.2"),
                row("r3", "c", "FAIL", model="zai/glm-5.2", cls="model"), row("r4", "d", "PASS", model="zhipu/glm-5.2")]
        groups = ringer.aggregate_model_log_rows(rows, registry=self.reg)
        by_model = {g["model"]: g for g in groups}
        self.assertEqual(sorted(by_model), [GLM, "zhipu/glm-5.2"])
        self.assertEqual(by_model[GLM]["tasks"], 3)
        rollup = {m["model"]: m for m in ringer.aggregate_model_scoreboard_rows(rows, registry=self.reg)}
        self.assertEqual(rollup[GLM]["tasks"], 3)

    def test_repo_registry_has_glm_aliases(self):
        reg = ringer.load_model_identity_registry(ROOT / "registry" / "model-identity.toml")
        self.assertEqual(reg.canonical_model_key("opencode", "zai/glm-5.2"), GLM)
        self.assertEqual(reg.canonical_model_key("opencode", "z-ai/glm-5.2"), GLM)


class InfraCountsIncludeDroppedTasks(unittest.TestCase):
    def test_dropped_task_infra_still_counted(self):
        rows = [row("r1", "a", "PASS")] + [row("r2", "b", "FAIL", cls="provider_error") for _ in range(2)]
        g = [g for g in ringer.aggregate_model_log_rows(rows) if g["model"] == GLM][0]
        self.assertEqual(g["tasks"], 1)
        self.assertEqual(g["infra"], {"provider_error": 2})


class CatalogKeepsToolSupport(unittest.TestCase):
    def test_normalize_keeps_supported_parameters(self):
        raw = {"id": "acme/m1", "name": "M1", "context_length": 64000, "architecture": {"modality": "text->text"},
               "pricing": {"prompt": "0.0000001", "completion": "0.0000002"}, "supported_parameters": ["tools", "temperature"]}
        m = ringer.normalize_catalog_model(raw, fetched_at="2026-10-09T00:00:00+00:00")
        self.assertEqual(m["supported_parameters"], ["tools", "temperature"])


class ExploreCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.log, self.cat, self.cfg = d / "runs.jsonl", d / "catalog.json", d / "config.toml"
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        base = {"context_length": 128000, "modality": "text->text", "variable_pricing": False, "pricing_unknown": False,
                "fetched_at": "2026-10-09T00:00:00+00:00", "pricing": {}}
        def cm(mid, price, tools=True, free=False, has_key=True):
            m = dict(base, id=mid, name=mid, prompt_per_m=price, completion_per_m=price, free=free)
            if has_key:
                m["supported_parameters"] = ["tools", "temperature"] if tools else ["temperature"]
            return m
        self.cat.write_text(json.dumps({"fetched_at": "2026-10-09T00:00:00+00:00", "models": [
            cm("acme/plain-a", 0.10), cm("acme/no-tools-b", 0.05, tools=False), cm("acme/blocked-c:free", 0.0, free=True),
            cm("acme/tested-d", 0.20), cm("acme/auditioned-e", 0.30), cm("acme/old-snapshot-f", 0.15, has_key=False)]}))
        rows = [row("w1", "t", "PASS", model="openrouter/acme/tested-d"),
                row("a1", "t", "PASS", model="openrouter/acme/auditioned-e", family="audition"),
                row("p1", "t", "FAIL", model="openrouter/acme/blocked-c:free", cls="provider_policy", when=yesterday)]
        self.log.write_text("".join(json.dumps(r) + "\n" for r in rows))
        self.cfg.write_text(f'state_dir = "{d}/state"\n[eval]\nbackend = "jsonl"\njsonl_path = "{self.log}"\n')
        self.home = d / "home"

    def tearDown(self):
        self.tmp.cleanup()

    def explore(self, task_type):
        env = dict(os.environ, RINGER_NO_SELF_UPDATE="1", RINGER_HOME=str(self.home))
        r = subprocess.run([sys.executable, "-B", str(ROOT / "ringer.py"), "--config", str(self.cfg), "models", "--explore",
                            "--task-type", task_type, "--log", str(self.log), "--catalog-file", str(self.cat)],
                           capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    @staticmethod
    def candidates(out):
        section = out.split("CANDIDATES", 1)[1]
        return [l.split()[1] for l in section.splitlines() if l.strip().startswith("untested")]

    def test_code_fix_candidates(self):
        out = self.explore("code-fix")
        cands = self.candidates(out)
        self.assertNotIn("acme/no-tools-b", cands)
        self.assertNotIn("acme/tested-d", cands, "tested on work for code-fix")
        self.assertNotIn("acme/blocked-c:free", cands)
        self.assertIn("acme/plain-a", cands)
        self.assertIn("acme/old-snapshot-f", cands, "entries without supported_parameters are kept")
        self.assertEqual(cands[0], "acme/auditioned-e", "audition-passing candidates come first")
        self.assertIn("blocked by provider policy", out)
        self.assertIn("acme/blocked-c:free", out.split("blocked by provider policy", 1)[1])

    def test_tested_is_per_task_type(self):
        self.assertIn("acme/tested-d", self.candidates(self.explore("code-review")))


if __name__ == "__main__":
    unittest.main()
