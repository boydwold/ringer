#!/usr/bin/env python3
"""Data labels: Ringer refuses an engine that the data rule does not allow.

Fork-only feature (2026-11-19). Each task carries a `data`
label (personal, work-code, customer). Each engine names its `provider`. The
rule file (a Markdown table between `data-rule:` markers) says which provider
may see which label. When `[data_rule] path` is set in config.toml, a task with
no label, an engine with no provider, or a pair the rule does not allow is
refused before any worker starts. Ringer never guesses a label.
"""
from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ringer import (  # noqa: E402
    DATA_LABELS,
    AppConfig,
    Manifest,
    TaskSpec,
    load_engines,
    parse_data_rule,
    validate_manifest_data,
)

RULE = textwrap.dedent(
    """\
    # Data rule

    Text before the table is ignored.

    <!-- data-rule:start -->
    | provider | personal | work-code | customer | what it is |
    |---|---|---|---|---|
    | codex | yes | yes | no | Codex |
    | mac-local | yes | yes | yes | Ollama on the Mac |
    | gemini-agy | yes | no | no | Gemini through agy |
    | bedrock | no | yes | yes | Bedrock |
    <!-- data-rule:end -->

    | codex | yes | yes | yes | a table outside the markers is ignored |
    """
)

LONG_SPEC = (
    "Create the requested artifact in the current working directory, keep the change scoped, "
    "and make the check command able to explain any failure clearly."
)
CHECK = "test -s output.txt || { echo 'FAIL: output.txt missing'; exit 1; }"


def task(key: str, engine: str, data: str | None) -> TaskSpec:
    obj = {"key": key, "spec": LONG_SPEC, "check": CHECK, "engine": engine}
    if data is not None:
        obj["data"] = data
    return TaskSpec.from_obj(obj)


def manifest(*tasks: TaskSpec) -> Manifest:
    return Manifest(
        run_name="data-label-test",
        workdir=Path(tempfile.gettempdir()),
        max_parallel=1,
        worktrees=False,
        repo=None,
        tasks=tuple(tasks),
    )


class DataRuleTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.rule_path = self.dir / "data-rule.md"
        self.rule_path.write_text(RULE)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def config(self, rule_line: str | None = None) -> AppConfig:
        if rule_line is None:
            rule_line = f'[data_rule]\npath = "{self.rule_path}"\n'
        toml = textwrap.dedent(
            f"""\
            state_dir = "{self.dir / 'state'}"

            [eval]
            backend = "jsonl"
            jsonl_path = "{self.dir / 'runs.jsonl'}"

            [engines.mac-ollama]
            bin = "/bin/true"
            provider = "mac-local"
            model_default = "ollama-mac/qwen3.5:35b-a3b-coding-nvfp4"
            args_template = ["{{taskdir}}", "{{model}}", "{{spec}}"]
            sandbox_args = []
            full_access_args = []

            [engines.agy]
            bin = "/bin/true"
            provider = "gemini-agy"
            args_template = ["{{spec}}"]
            sandbox_args = []
            full_access_args = []

            [engines.noprovider]
            bin = "/bin/true"
            args_template = ["{{spec}}"]
            sandbox_args = []
            full_access_args = []

            [engines.unlisted]
            bin = "/bin/true"
            provider = "some-new-cloud"
            args_template = ["{{spec}}"]
            sandbox_args = []
            full_access_args = []

            {rule_line}
            """
        )
        path = self.dir / "config.toml"
        path.write_text(toml)
        return AppConfig.load(path)


class ParseDataRuleTests(DataRuleTestCase):
    def test_labels_are_the_three_known_values(self) -> None:
        self.assertEqual(tuple(DATA_LABELS), ("personal", "work-code", "customer"))

    def test_reads_only_the_table_between_the_markers(self) -> None:
        rule = parse_data_rule(RULE)
        self.assertEqual(rule["codex"], frozenset({"personal", "work-code"}))
        self.assertEqual(rule["mac-local"], frozenset({"personal", "work-code", "customer"}))
        self.assertEqual(rule["gemini-agy"], frozenset({"personal"}))
        self.assertEqual(rule["bedrock"], frozenset({"work-code", "customer"}))
        self.assertEqual(set(rule), {"codex", "mac-local", "gemini-agy", "bedrock"})

    def test_missing_markers_is_an_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "data-rule:start"):
            parse_data_rule("| provider | personal | work-code | customer |\n")

    def test_a_cell_that_is_not_yes_or_no_is_an_error(self) -> None:
        bad = RULE.replace("| gemini-agy | yes | no | no |", "| gemini-agy | yes | maybe | no |")
        with self.assertRaisesRegex(ValueError, "gemini-agy"):
            parse_data_rule(bad)

    def test_a_header_without_the_three_labels_is_an_error(self) -> None:
        bad = RULE.replace("| provider | personal | work-code | customer |", "| provider | personal | work | customer |")
        with self.assertRaisesRegex(ValueError, "work-code"):
            parse_data_rule(bad)


class TaskAndEngineFieldTests(DataRuleTestCase):
    def test_task_reads_its_data_label(self) -> None:
        self.assertEqual(task("t", "codex", "work-code").data, "work-code")
        self.assertEqual(task("t", "codex", None).data, "")

    def test_task_rejects_an_unknown_label(self) -> None:
        with self.assertRaisesRegex(ValueError, "personal, work-code, customer"):
            task("t", "codex", "secret")

    def test_engine_reads_its_provider(self) -> None:
        config = self.config()
        self.assertEqual(config.engines["mac-ollama"].provider, "mac-local")
        self.assertEqual(config.engines["noprovider"].provider, "")

    def test_built_in_codex_engine_is_provider_codex(self) -> None:
        self.assertEqual(load_engines(None)["codex"].provider, "codex")

    def test_config_reads_the_rule_path(self) -> None:
        self.assertEqual(self.config().data_rule_path, self.rule_path)
        self.assertIsNone(self.config(rule_line="").data_rule_path)


class ValidateManifestDataTests(DataRuleTestCase):
    def test_allowed_pairs_pass(self) -> None:
        validate_manifest_data(
            manifest(
                task("a", "codex", "work-code"),
                task("b", "mac-ollama", "customer"),
                task("c", "agy", "personal"),
            ),
            self.config(),
        )

    def test_missing_label_is_refused_with_a_clear_message(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            validate_manifest_data(manifest(task("nolabel", "codex", None)), self.config())
        message = str(ctx.exception)
        self.assertIn("nolabel", message)
        self.assertIn('"data"', message)
        self.assertIn("personal, work-code, customer", message)

    def test_engine_not_allowed_for_label_is_refused(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            validate_manifest_data(manifest(task("w", "agy", "work-code")), self.config())
        message = str(ctx.exception)
        self.assertIn("w", message)
        self.assertIn("agy", message)
        self.assertIn("gemini-agy", message)
        self.assertIn("work-code", message)
        # It names what is allowed, so the author can fix the manifest.
        self.assertIn("codex", message)
        self.assertIn("mac-ollama", message)

    def test_customer_data_is_refused_on_codex(self) -> None:
        with self.assertRaisesRegex(ValueError, "customer"):
            validate_manifest_data(manifest(task("c", "codex", "customer")), self.config())

    def test_engine_without_provider_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "provider"):
            validate_manifest_data(manifest(task("p", "noprovider", "personal")), self.config())

    def test_provider_missing_from_rule_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "some-new-cloud"):
            validate_manifest_data(manifest(task("u", "unlisted", "personal")), self.config())

    def test_every_bad_task_is_reported_at_once(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            validate_manifest_data(
                manifest(task("first", "codex", None), task("second", "agy", "customer")),
                self.config(),
            )
        self.assertIn("first", str(ctx.exception))
        self.assertIn("second", str(ctx.exception))

    def test_missing_rule_file_is_refused_not_ignored(self) -> None:
        self.rule_path.unlink()
        with self.assertRaisesRegex(ValueError, "data rule"):
            validate_manifest_data(manifest(task("a", "codex", "personal")), self.config())

    def test_rule_is_read_fresh_on_each_check(self) -> None:
        config = self.config()
        manifest_ = manifest(task("a", "agy", "work-code"))
        with self.assertRaises(ValueError):
            validate_manifest_data(manifest_, config)
        self.rule_path.write_text(RULE.replace("| gemini-agy | yes | no | no |", "| gemini-agy | yes | yes | no |"))
        validate_manifest_data(manifest_, config)

    def test_no_rule_configured_means_no_check(self) -> None:
        # Upstream behaviour is unchanged when [data_rule] is absent.
        validate_manifest_data(manifest(task("a", "noprovider", None)), self.config(rule_line=""))


if __name__ == "__main__":
    unittest.main()
