#!/usr/bin/env python3
"""Fallback engine: a second engine takes over when the first engine fails.

Fork-only feature (2026-11-19). A task may name `fallback_engine` (and
optionally `fallback_model`). When an attempt on the first engine does not
pass, for any reason (a failed check, a timeout, an engine that does not
answer), the next attempt runs on the fallback engine. Ringer does not wait
for provider retries on the first engine. The fallback attempt gets the same
failure context as a normal retry. The engine check and the data-rule check
cover the fallback engine too, so a fallback cannot send data to a provider
the label does not allow.
"""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import ringer

RULE = textwrap.dedent(
    """\
    <!-- data-rule:start -->
    | provider | personal | work-code | customer | what it is |
    |---|---|---|---|---|
    | codex | yes | yes | no | Codex |
    | mac-local | yes | yes | yes | Ollama on the Mac |
    <!-- data-rule:end -->
    """
)

SPEC = "Write the correct answer to out.txt."
CHECK = "test -s out.txt"


def config_text(root: Path, rule: bool) -> str:
    rule_block = f'[data_rule]\npath = "{root / "rule.md"}"\n' if rule else ""
    return textwrap.dedent(
        f"""\
        state_dir = "{root / "state"}"
        {rule_block}
        [eval]
        backend = "jsonl"
        jsonl_path = "{root / "rows.jsonl"}"

        [artifact]
        enabled = false

        [retry]
        infra_base_delay_s = 0
        infra_max_delay_s = 0

        [engines.mac-ollama]
        bin = "/bin/true"
        provider = "mac-local"
        model_default = "ollama-mac/small"
        args_template = ["{{taskdir}}", "{{model}}", "{{spec}}"]
        sandbox_args = []
        full_access_args = []

        [engines.codex]
        bin = "/bin/true"
        provider = "codex"
        args_template = ["{{spec}}"]
        sandbox_args = []
        full_access_args = []
        """
    )


def load_config(root: Path, *, rule: bool = False) -> ringer.AppConfig:
    (root / "rule.md").write_text(RULE)
    path = root / "config.toml"
    path.write_text(config_text(root, rule))
    return ringer.AppConfig.load(path)


def task(**extra) -> ringer.TaskSpec:
    obj = {"key": "t", "spec": SPEC, "check": CHECK, "engine": "mac-ollama", "max_attempts": 2}
    obj.update(extra)
    return ringer.TaskSpec.from_obj(obj)


def manifest(root: Path, *tasks: ringer.TaskSpec) -> ringer.Manifest:
    return ringer.Manifest("fallback-test", root / "work", 1, False, None, tuple(tasks))


class ParseTests(unittest.TestCase):
    def test_fields_parse(self):
        spec = task(fallback_engine=" codex ", fallback_model="")
        self.assertEqual(spec.fallback_engine, "codex")
        self.assertEqual(spec.fallback_model, "")

    def test_default_is_no_fallback(self):
        self.assertEqual(task().fallback_engine, "")

    def test_fallback_equal_to_engine_is_refused(self):
        with self.assertRaisesRegex(ValueError, "fallback_engine"):
            task(fallback_engine="mac-ollama")

    def test_fallback_model_without_engine_is_refused(self):
        with self.assertRaisesRegex(ValueError, "fallback_model"):
            task(fallback_model="gpt-5")

    def test_non_string_is_refused(self):
        with self.assertRaisesRegex(ValueError, "fallback_engine"):
            task(fallback_engine=["codex"])

    def test_fallback_task_swaps_engine(self):
        spec = task(fallback_engine="codex", model="ollama-mac/small", engine_args=["--x"])
        swapped = ringer.fallback_task(spec)
        self.assertEqual(swapped.engine, "codex")
        self.assertEqual(swapped.model, "")
        self.assertEqual(swapped.engine_args, ())
        self.assertEqual(swapped.fallback_engine, "")
        self.assertEqual((swapped.key, swapped.spec, swapped.check, swapped.data),
                         (spec.key, spec.spec, spec.check, spec.data))
        self.assertIsNone(ringer.fallback_task(task()))


class ValidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_unknown_fallback_engine_is_refused(self):
        config = load_config(self.root)
        with self.assertRaisesRegex(ValueError, "nosuch"):
            ringer.validate_manifest_engines(manifest(self.root, task(fallback_engine="nosuch")), config)

    def test_fallback_model_on_engine_without_model_slot_is_refused(self):
        config = load_config(self.root)
        with self.assertRaisesRegex(ValueError, "model"):
            ringer.validate_manifest_engines(
                manifest(self.root, task(fallback_engine="codex", fallback_model="gpt-5")), config
            )

    def test_known_fallback_passes(self):
        config = load_config(self.root)
        ringer.validate_manifest_engines(manifest(self.root, task(fallback_engine="codex")), config)

    def test_data_rule_checks_the_fallback(self):
        config = load_config(self.root, rule=True)
        refused = manifest(self.root, task(fallback_engine="codex", data="customer"))
        with self.assertRaisesRegex(ValueError, r"t \(fallback\).*codex.*customer"):
            ringer.validate_manifest_data(refused, config)
        ringer.validate_manifest_data(
            manifest(self.root, task(fallback_engine="codex", data="work-code")), config
        )

    def test_preflight_checks_the_fallback_bin(self):
        config = load_config(self.root)
        config.engines["codex"] = ringer.dataclass_replace(config.engines["codex"], bin="/nonexistent/codex")
        with self.assertRaisesRegex(ValueError, "codex"):
            ringer.preflight_engine_bins(manifest(self.root, task(fallback_engine="codex")), config)


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = load_config(self.root)

    def runner_for(self, spec: ringer.TaskSpec):
        runner = ringer.RingerRunner(manifest(self.root, spec), self.config, "test", dashboard_enabled=False)
        self.addCleanup(runner.logger.close)
        runner.state_writer.flush = Mock()
        runner._harvest_deliverables_on_pass = Mock()
        runner._cleanup_worktree_on_pass = AsyncMock()
        return runner, runner.runtimes[0]

    def script(self, runner, runtime, outputs, passes):
        engines = []

        async def worker(rt, spec, attempt):
            engines.append(rt.task.engine)
            return ringer.WorkerResult(1, False, None, output_tail=outputs[len(engines) - 1])

        runner._run_worker = AsyncMock(side_effect=worker)
        runner.verifier.verify = AsyncMock(side_effect=[
            ringer.VerifyResult(True, 0, False, "ok") if ok else ringer.VerifyResult(False, 1, False, f"check {i}")
            for i, ok in enumerate(passes)
        ])
        return engines

    def rows(self):
        return [json.loads(line) for line in self.config.eval.jsonl_path.read_text().splitlines()]

    async def test_failed_check_moves_to_fallback(self):
        runner, runtime = self.runner_for(task(fallback_engine="codex"))
        engines = self.script(runner, runtime, ["mac output", "codex output"], [False, True])
        with contextlib.redirect_stdout(io.StringIO()):
            await runner._run_task(runtime)
        self.assertEqual(engines, ["mac-ollama", "codex"])
        self.assertEqual(runtime.status, "pass")
        self.assertEqual(runtime.fallback_from, "mac-ollama")
        spec = runner._run_worker.call_args_list[1].args[1]
        self.assertIn("check 0", spec)
        self.assertIn("mac output", spec)
        rows = self.rows()
        self.assertEqual([row["worker_engine"] for row in rows], ["mac-ollama", "codex"])

    async def test_provider_error_falls_back_without_waiting(self):
        runner, runtime = self.runner_for(task(fallback_engine="codex"))
        engines = self.script(runner, runtime, ["ERROR: Selected model is at capacity.", "done"], [False, True])
        sleep = AsyncMock()
        with patch.object(ringer.asyncio, "sleep", sleep), contextlib.redirect_stdout(io.StringIO()):
            await runner._run_task(runtime)
        sleep.assert_not_awaited()
        self.assertEqual(engines, ["mac-ollama", "codex"])
        self.assertEqual(runtime.status, "pass")
        self.assertEqual(runtime.infra_retries, 0)

    async def test_harness_error_falls_back(self):
        runner, runtime = self.runner_for(task(fallback_engine="codex"))
        engines = self.script(runner, runtime, ["broken", "done"], [False, True])
        real = ringer.classify_failure
        calls = []

        def classify(*args, **kwargs):
            calls.append(1)
            return ("harness_error", "no answer") if len(calls) == 1 else real(*args, **kwargs)

        with patch.object(ringer, "classify_failure", classify), contextlib.redirect_stdout(io.StringIO()):
            await runner._run_task(runtime)
        self.assertEqual(engines, ["mac-ollama", "codex"])
        self.assertEqual(runtime.status, "pass")

    async def test_fallback_gets_its_own_attempts(self):
        runner, runtime = self.runner_for(task(fallback_engine="codex", max_attempts=2))
        engines = self.script(runner, runtime, ["a", "b", "c"], [False, False, True])
        with contextlib.redirect_stdout(io.StringIO()):
            await runner._run_task(runtime)
        self.assertEqual(engines, ["mac-ollama", "codex", "codex"])
        self.assertEqual(runtime.status, "pass")

    async def test_fallback_failure_ends_the_task(self):
        runner, runtime = self.runner_for(task(fallback_engine="codex", max_attempts=1))
        engines = self.script(runner, runtime, ["a", "b"], [False, False])
        with contextlib.redirect_stdout(io.StringIO()):
            await runner._run_task(runtime)
        self.assertEqual(engines, ["mac-ollama", "codex"])
        self.assertEqual(runtime.status, "fail")

    async def test_no_fallback_keeps_old_behaviour(self):
        runner, runtime = self.runner_for(task(max_attempts=2))
        engines = self.script(runner, runtime, ["a", "b"], [False, True])
        with contextlib.redirect_stdout(io.StringIO()):
            await runner._run_task(runtime)
        self.assertEqual(engines, ["mac-ollama", "mac-ollama"])
        self.assertIsNone(runtime.fallback_from)

    async def test_state_records_the_fallback(self):
        runner, runtime = self.runner_for(task(fallback_engine="codex"))
        self.script(runner, runtime, ["a", "b"], [False, True])
        with contextlib.redirect_stdout(io.StringIO()):
            await runner._run_task(runtime)
        task_state = runner.state_writer.snapshot()["tasks"][0]
        self.assertEqual(task_state["fallback_from"], "mac-ollama")
        self.assertEqual(task_state["engine"], "codex")

    async def test_sandbox_refusal_does_not_fall_back(self):
        runner, runtime = self.runner_for(task(fallback_engine="codex", max_attempts=1))
        engines = self.script(runner, runtime, ["a", "b"], [False, True])

        def classify(*args, **kwargs):
            return ("sandbox_denied", "path outside the writable root")

        with patch.object(ringer, "classify_failure", classify), contextlib.redirect_stdout(io.StringIO()):
            await runner._run_task(runtime)
        self.assertEqual(engines, ["mac-ollama"])
        self.assertEqual(runtime.status, "fail")
        self.assertIsNone(runtime.fallback_from)

    def test_lint_reads_the_fallback_route(self):
        seen = []
        registry = Mock(defaults={}, noncanonical_routes=Mock(get=lambda key: seen.append(key)))
        ringer.noncanonical_route_findings(
            manifest(self.root, task(fallback_engine="codex")), config=self.config, registry=registry
        )
        self.assertIn("codex", [engine for engine, _ in seen])


if __name__ == "__main__":
    unittest.main()
