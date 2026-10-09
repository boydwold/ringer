"""Regression coverage for canonical scoreboard identities and exploration."""
from __future__ import annotations

import argparse
import contextlib
import copy
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import ringer


GLM = "openrouter/z-ai/glm-5.2"
ALIAS = "zai/glm-5.2"


def attempt(run="run", **values):
    return dict({
        "run_id": run, "task_key": "task", "worker_engine": "opencode",
        "model": GLM, "task_type": "code-fix", "verdict": "PASS",
        "run_family": "work", "failure_class": None, "model_attempt": 1,
        "logged_at": "2026-01-01T00:00:00+00:00", "retry": False,
        "worker_tokens": 10, "duration_ms": 20,
    }, **values)


def catalog_model(mid, price=0, **values):
    return dict({
        "id": mid, "name": mid, "context_length": 64000, "modality": "text->text",
        "prompt_per_m": price, "completion_per_m": price, "free": price == 0,
        "variable_pricing": False, "supported_parameters": ["tools"],
    }, **values)


class IdentityExploreTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.registry_path = self.root / "identity.toml"
        self.registry_path.write_text(
            '[engines.opencode]\nharness = "OpenCode"\naccess = "OpenRouter API"\n'
            f'[engines.opencode.models."{GLM}"]\n'
            'display = "GLM 5.2"\nlab = "Z.ai"\nalias = false\n'
            f'slug_aliases = ["opencode:{ALIAS}"]\n'
        )
        self.registry = ringer.load_model_identity_registry(self.registry_path)

    def explore(self, rows, catalog, task_type=None):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ringer.print_model_explore(
                log_path=self.root / "runs.jsonl", rows_read=len(rows), skipped=0,
                groups=[], catalog_path=self.root / "catalog.json", catalog_models=catalog,
                rows=rows, task_type=task_type, registry=self.registry,
            )
        output = out.getvalue()
        candidates = [line.split()[1] for line in output.splitlines() if line.strip().startswith("untested ")]
        return candidates, output

    def test_alias_resolves_identity_without_lineage_alias_flag(self):
        identity = self.registry.resolve("opencode", ALIAS)
        self.assertEqual(identity.model_display, "GLM 5.2")
        self.assertFalse(identity.alias)
        self.assertFalse(identity.unregistered)
        self.assertEqual(self.registry.canonical_model_key("codex", ALIAS), ALIAS)

    def test_malformed_alias_identifies_entry(self):
        for value in ["missing-separator", ":slug", "opencode:"]:
            with self.subTest(value=value):
                self.registry_path.write_text(f'[engines.opencode.models."{GLM}"]\nslug_aliases = ["{value}"]\n')
                with self.assertRaisesRegex(ValueError, value):
                    ringer.load_model_identity_registry(self.registry_path)

    def test_legacy_alias_retry_groups_and_does_not_mutate_input(self):
        rows = [attempt(model=ALIAS, verdict="FAIL"), attempt(model=GLM, retry=True)]
        for row in rows:
            del row["failure_class"]
            del row["model_attempt"]
        original = copy.deepcopy(rows)
        for aggregate in [ringer.aggregate_model_log_rows, ringer.aggregate_model_scoreboard_rows]:
            with self.subTest(aggregate=aggregate.__name__):
                group, = aggregate(rows, registry=self.registry, model=ALIAS)
                self.assertEqual((group["tasks"], group["attempts"], group["passed"]), (1, 2, 1))
                self.assertEqual(group["model"], GLM)
                self.assertEqual(group["first_try_pass_rate"], 0)
        self.assertEqual(rows, original)
        self.assertEqual(len(ringer.aggregate_model_log_rows(rows)), 2)

    def test_effort_buckets_and_latest_identity_use_aliases(self):
        rows = [attempt("a", reasoning_effort="high"), attempt("b", model=ALIAS)]
        groups = ringer.aggregate_model_log_rows(rows, registry=self.registry)
        enriched = ringer.enrich_model_groups_with_identity(groups, rows, self.registry, include_task_type=True)
        self.assertEqual(len(enriched), 2)
        self.assertTrue(all(g["show_reasoning_effort"] for g in enriched))
        self.assertTrue(all(g["identity_key"] == GLM and g["lab"] == "Z.ai" for g in enriched))
        self.assertTrue(all(not g["unregistered"] for g in enriched))

    def test_blank_models_stay_unattributed(self):
        group, = ringer.aggregate_model_log_rows([attempt(model="")], registry=self.registry)
        self.assertTrue(group["unattributed"])
        self.assertNotEqual(group["model"], GLM)

    def test_audition_tier_uses_canonical_work_evidence(self):
        rows = [attempt(str(i), model=ALIAS) for i in range(3)] + [attempt("aud", run_family="audition")]
        for aggregate in [ringer.aggregate_model_log_rows, ringer.aggregate_model_scoreboard_rows]:
            group, = aggregate(rows, family="audition", registry=self.registry)
            self.assertEqual(group["work_tasks"], 3)
            self.assertEqual(group["tier"], "proven")

    def test_infra_rows_respect_all_bucket_dimensions(self):
        rows = [attempt(reasoning_effort="high")]
        variants = [{}, {"task_type": "code-review"}, {"reasoning_effort": "low"},
                    {"run_family": "audition"}, {"worker_engine": "codex"}]
        rows += [attempt(str(i), model=ALIAS, verdict="FAIL", failure_class="provider_error",
                         **dict({"reasoning_effort": "high"}, **values)) for i, values in enumerate(variants)]
        group, = ringer.aggregate_model_log_rows(rows, family="all", registry=self.registry)
        self.assertEqual(group["infra"], {"provider_error": 1})
        rollup, = ringer.aggregate_model_scoreboard_rows(rows, family="all", registry=self.registry)
        self.assertEqual(rollup["infra"], {"provider_error": 2})
        rollup, = ringer.aggregate_model_scoreboard_rows(rows, task_type="code-fix", registry=self.registry)
        self.assertEqual(rollup["infra"], {"provider_error": 1})

    def test_infra_is_attributed_to_its_row_model(self):
        rows = [attempt("a", model="other"), attempt("b"),
                attempt("b", model="other", verdict="FAIL", failure_class="provider_error")]
        groups = {g["model"]: g for g in ringer.aggregate_model_log_rows(rows, registry=self.registry)}
        self.assertEqual(groups[GLM]["infra"], {})
        self.assertEqual(groups["other"]["infra"], {"provider_error": 1})

    def test_infra_only_merges_aliases_and_excludes_tested_models(self):
        rows = [attempt("a", model=ALIAS, verdict="FAIL", failure_class="provider_error"),
                attempt("b", verdict="FAIL", failure_class="rate_limited")]
        group, = ringer.infra_only_models(rows, model=ALIAS, registry=self.registry)
        self.assertEqual(group, {"engine": "opencode", "model": GLM,
                                 "infra": {"provider_error": 1, "rate_limited": 1}})
        self.assertEqual(ringer.infra_only_models(rows + [attempt("c")], registry=self.registry), [])

    def test_supported_parameters_missing_empty_and_mixed(self):
        raw = {"id": "acme/a", "architecture": {"modality": "text->text"},
               "pricing": {"prompt": "0", "completion": "0"}, "context_length": 64000}
        legacy = ringer.normalize_catalog_model(raw, fetched_at="now")
        self.assertNotIn("supported_parameters", legacy)
        self.assertTrue(ringer.catalog_model_is_text_candidate(legacy))
        empty = ringer.normalize_catalog_model(dict(raw, supported_parameters=[]), fetched_at="now")
        self.assertFalse(ringer.catalog_model_is_text_candidate(empty))
        mixed = ringer.normalize_catalog_model(dict(raw, supported_parameters=[3, "tools"]), fetched_at="now")
        self.assertEqual(mixed["supported_parameters"], ["tools"])

    def test_explore_tested_is_work_evidence_per_task_type(self):
        catalog = [catalog_model("z-ai/glm-5.2")]
        rows = [attempt(model=ALIAS, verdict="FAIL", failure_class="model")]
        self.assertEqual(self.explore(rows, catalog, "code-fix")[0], [])
        self.assertEqual(self.explore(rows, catalog)[0], [])
        self.assertEqual(self.explore(rows, catalog, "code-review")[0], ["z-ai/glm-5.2"])
        rows[0]["failure_class"] = "provider_error"
        self.assertEqual(self.explore(rows, catalog)[0], ["z-ai/glm-5.2"])
        rows[0].update(verdict="PASS", run_family="audition")
        self.assertEqual(self.explore(rows, catalog)[0], ["z-ai/glm-5.2"])

    def test_policy_latest_timestamp_wins_across_aliases_and_task_types(self):
        now = datetime.now(timezone.utc)
        recent = (now - timedelta(hours=1)).isoformat()
        older = (now - timedelta(days=1)).isoformat()
        rows = [attempt(model=ALIAS, verdict="FAIL", failure_class="provider_policy", logged_at=recent,
                        task_type="code-review"),
                attempt(model=GLM, verdict="FAIL", failure_class="provider_error", logged_at=older)]
        candidates, output = self.explore(rows, [catalog_model("z-ai/glm-5.2")], "code-fix")
        self.assertEqual(candidates, [])
        self.assertIn("blocked by provider policy\n  z-ai/glm-5.2", output)
        rows[0]["failure_class"], rows[1]["failure_class"] = "provider_error", "provider_policy"
        candidates, output = self.explore(rows, [catalog_model("z-ai/glm-5.2")])
        self.assertEqual(candidates, ["z-ai/glm-5.2"])
        self.assertNotIn("blocked by provider policy", output)

    def test_old_invalid_and_future_policy_rows_do_not_block(self):
        now = datetime.now(timezone.utc)
        for stamp in [(now - timedelta(days=8)).isoformat(), "bad date", (now + timedelta(days=1)).isoformat()]:
            with self.subTest(stamp=stamp):
                rows = [attempt(verdict="FAIL", failure_class="provider_policy", logged_at=stamp)]
                self.assertEqual(self.explore(rows, [catalog_model("z-ai/glm-5.2")])[0], ["z-ai/glm-5.2"])

    def test_audition_priority_precedes_free_and_survives_limit(self):
        catalog = [catalog_model(f"acme/free-{i}") for i in range(12)]
        catalog += [catalog_model("z-ai/glm-5.2", 100)]
        rows = [attempt(model=ALIAS, run_family="audition")]
        candidates, _ = self.explore(rows, catalog, "code-fix")
        self.assertEqual(len(candidates), 10)
        self.assertEqual(candidates[0], "z-ai/glm-5.2")
        candidates, _ = self.explore(rows, catalog, "code-review")
        self.assertTrue(candidates[0].startswith("acme/free-"))

    def setup_surfaces(self):
        self.log = self.root / "runs.jsonl"
        self.log.write_text("".join(json.dumps(row) + "\n" for row in [attempt("a"), attempt("b", model=ALIAS)]))
        self.catalog = self.root / "catalog.json"
        self.catalog.write_text(json.dumps({"models": [catalog_model("z-ai/glm-5.2"),
            catalog_model("acme/no-tools", supported_parameters=[]), catalog_model("acme/yes-tools")]}))
        self.db = self.root / "ringer.db"
        self.args = argparse.Namespace(
            log=self.log, db=self.db, task_type=None, model=None, engine=None, since=None,
            family="work", explore=False, catalog_file=self.catalog, registry=self.registry_path,
            notes_file=self.root / "missing.md", html=None, open=False, json=True,
        )
        self.config = ringer.AppConfig(
            path=None, identity_default=None, state_dir=self.root / "state", dashboard_port_base=8787,
            hud_port=8700, hud_app_path=None, allow_full_access=False,
            eval=ringer.EvalConfig(backend="jsonl", jsonl_path=self.log), engines={},
            artifact=ringer.ArtifactConfig(enabled=False, out_template=str(self.root / "live.html"),
                report_template=str(self.root / "report.html"), index_out=self.root / "index.html"),
        )

    def test_api_db_and_jsonl_alias_parity(self):
        self.setup_surfaces()
        kwargs = dict(log_path=self.log, db_path=self.db, catalog_path=self.catalog,
                      registry_path=self.registry_path, notes_path=self.args.notes_file)
        with patch.object(ringer, "read_model_log_rows", side_effect=AssertionError("unexpected JSONL fallback")):
            db = ringer.build_models_api_payload(**kwargs)
        with patch.object(ringer, "should_use_read_model_db", return_value=False):
            jsonl = ringer.build_models_api_payload(**kwargs)
        self.assertEqual(db["groups"], jsonl["groups"])
        self.assertEqual(db["rollup"], jsonl["rollup"])
        self.assertEqual(db["columns"], list(ringer.MODEL_SCOREBOARD_COLUMNS))
        self.assertEqual(len(db["rollup"]), 1)
        self.assertEqual(db["rollup"][0]["tasks"], 2)
        self.assertEqual(db["rollup"][0]["model_display"], "GLM 5.2")

    def test_models_db_explore_retains_tool_filter_and_aliases(self):
        self.setup_surfaces()
        self.args.explore = True
        out = io.StringIO()
        with patch.object(ringer, "read_model_log_rows", side_effect=AssertionError("unexpected JSONL fallback")), contextlib.redirect_stdout(out):
            self.assertEqual(ringer.run_models_command(self.config, self.args), 0)
        candidates = [line.split()[1] for line in out.getvalue().splitlines() if line.strip().startswith("untested ")]
        self.assertEqual(candidates, ["acme/yes-tools"])
        self.assertIn("tasks=2", out.getvalue())

    def test_models_db_json_and_html_receive_canonical_groups(self):
        self.setup_surfaces()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(ringer.run_models_command(self.config, self.args), 0)
        group, = json.loads(out.getvalue())
        self.assertEqual((group["model"], group["tasks"]), (GLM, 2))
        self.args.html = str(self.root / "scoreboard.html")
        with patch.object(ringer, "write_model_scoreboard_html", return_value=Path(self.args.html)) as render, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ringer.run_models_command(self.config, self.args), 0)
        group, = render.call_args.kwargs["rows"]
        self.assertEqual((group["model"], group["tasks"], group["model_display"]), (GLM, 2, "GLM 5.2"))


if __name__ == "__main__":
    unittest.main()
