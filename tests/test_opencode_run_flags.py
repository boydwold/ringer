#!/usr/bin/env python3
"""The argv that reaches `opencode run` from Ringer's opencode engine.

OpenCode 2.x removed `opencode run --dir` ("Unrecognized flag: --dir in
command opencode run", seen in a review run on 2026-10-31). Ringer
already starts every worker with the task directory as its working directory,
so `--dir {taskdir}` is redundant:

- engines/opencode-sandboxed.sh drops a `--dir` (or `--dir=`) whose value is
  the task directory, so existing configs keep working on every version;
- a `--dir` that names another directory passes through unchanged;
- the config.sample.toml example no longer passes `--dir`.

OpenCode 2.x also starts a shared background service and writes
~/.config/opencode/service.json, which the sandbox keeps read-only (EPERM,
real run 2026-11-01). Inside the sandbox the wrapper therefore adds
`--standalone` (a private server) after `run` on 2.x, and only there;
RINGER_OPENCODE_STANDALONE=1|0 forces the choice. The last argument is the
prompt and is never filtered or read as a flag.
"""
from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ringer import EngineConfig, build_worker_command  # noqa: E402

WRAP = ROOT / "engines" / "opencode-sandboxed.sh"
SAMPLE = ROOT / "config.sample.toml"
DARWIN_SANDBOX = sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").exists()

# Records its argv (one per line) and working directory inside the task dir.
STUB = '#!/bin/sh\nif [ "$1" = "--version" ]; then printf "%b\\n" "$STUB_VERSION"; exit 0; fi\n: > argv.txt\nfor a in "$@"; do printf "%s\\n" "$a" >> argv.txt; done\npwd -P > cwd.txt\n'

# The template every existing opencode config uses (before OpenCode 2.x).
LEGACY_TEMPLATE = (
    "{taskdir}", "{access_args}", "run", "-m", "{model}", "--dangerously-skip-permissions",
    "--format", "json", "{engine_args}", "--dir", "{taskdir}", "{spec}",
)


def opencode_engine(template=LEGACY_TEMPLATE) -> EngineConfig:
    return EngineConfig(
        name="opencode",
        bin=str(WRAP),
        args_template=tuple(template),
        full_access_args=("--no-sandbox",),
        sandbox_args=(),
        token_regex=None,
        model_default="openrouter/z-ai/glm-5.2",
    )


class OpencodeRunArgv(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name).resolve()
        self.stub = d / "bin" / "opencode"
        self.stub.parent.mkdir()
        self.stub.write_text(STUB)
        self.stub.chmod(self.stub.stat().st_mode | stat.S_IEXEC)
        self.taskdir = d / "work" / "task-a"
        self.taskdir.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def run_engine(self, *, full_access: bool, template=LEGACY_TEMPLATE, engine_args=(),
                   version="opencode v2.2.0", spec="say ok", extra_env=None):
        command = build_worker_command(
            opencode_engine(template), taskdir=self.taskdir, spec=spec,
            full_access=full_access, engine_args=tuple(engine_args),
        )
        env = dict(os.environ, OPENCODE_BIN=str(self.stub), STUB_VERSION=version)
        env.pop("RINGER_OPENCODE_STANDALONE", None)
        env.update(extra_env or {})
        result = subprocess.run(command, cwd=self.taskdir, env=env, capture_output=True,
                                text=True, timeout=60, stdin=subprocess.DEVNULL)
        self.assertEqual(result.returncode, 0, result.stderr)
        argv = (self.taskdir / "argv.txt").read_text().splitlines()
        cwd = (self.taskdir / "cwd.txt").read_text().strip()
        return argv, cwd

    def test_legacy_template_drops_task_dir_flag(self):
        argv, cwd = self.run_engine(full_access=True)
        self.assertEqual(argv, ["run", "-m", "openrouter/z-ai/glm-5.2",
                                "--dangerously-skip-permissions", "--format", "json", "say ok"])
        self.assertEqual(cwd, str(self.taskdir))

    def test_equals_form_is_dropped_too(self):
        template = ("{taskdir}", "{access_args}", "run", "--dir={taskdir}", "{spec}")
        argv, _ = self.run_engine(full_access=True, template=template)
        self.assertEqual(argv, ["run", "say ok"])

    def test_other_directory_passes_through(self):
        other = str(self.taskdir.parent)
        argv, _ = self.run_engine(full_access=True, engine_args=("--dir", other))
        self.assertIn("--dir", argv)
        self.assertEqual(argv[argv.index("--dir") + 1], other)

    @unittest.skipUnless(DARWIN_SANDBOX, "macOS sandbox-exec only")
    def test_sandboxed_darwin_drops_task_dir_flag(self):
        argv, cwd = self.run_engine(full_access=False)
        self.assertNotIn("--dir", argv)
        self.assertEqual(argv[-1], "say ok")
        self.assertEqual(cwd, str(self.taskdir))

    @unittest.skipUnless(DARWIN_SANDBOX, "macOS sandbox-exec only")
    def test_sandboxed_v2_runs_standalone(self):
        argv, _ = self.run_engine(full_access=False)
        self.assertEqual(argv[:2], ["run", "--standalone"])
        self.assertEqual(argv.count("--standalone"), 1)

    @unittest.skipUnless(DARWIN_SANDBOX, "macOS sandbox-exec only")
    def test_sandboxed_v2_does_not_repeat_standalone(self):
        template = ("{taskdir}", "{access_args}", "run", "--standalone", "{spec}")
        argv, _ = self.run_engine(full_access=False, template=template)
        self.assertEqual(argv, ["run", "--standalone", "say ok"])

    @unittest.skipUnless(DARWIN_SANDBOX, "macOS sandbox-exec only")
    def test_sandboxed_v1_gets_no_standalone(self):
        argv, _ = self.run_engine(full_access=False, version="1.18.3")
        self.assertNotIn("--standalone", argv)

    def test_prompt_equal_to_dir_flag_is_kept(self):
        spec = f"--dir={self.taskdir}"
        argv, _ = self.run_engine(full_access=True, template=("{taskdir}", "{access_args}", "run", "{spec}"),
                                  spec=spec)
        self.assertEqual(argv, ["run", spec])

    def test_dir_flag_before_prompt_keeps_prompt(self):
        template = ("{taskdir}", "{access_args}", "run", "--dir", "{spec}")
        argv, _ = self.run_engine(full_access=True, template=template, spec=str(self.taskdir))
        self.assertEqual(argv, ["run", "--dir", str(self.taskdir)])

    @unittest.skipUnless(DARWIN_SANDBOX, "macOS sandbox-exec only")
    def test_version_strings(self):
        cases = {
            "opencode v2.2.0": True, "opencode 2.2.0": True, "v10.0.0": True, "2.0.0-beta": True,
            "opencode v2.2.0\\nupdate available: v1.0.0": True,
            "1.18.3": False, "opencode v1.18.3": False, "0.9.1": False, "": False,
        }
        for version, expected in cases.items():
            with self.subTest(version=version):
                argv, _ = self.run_engine(full_access=False, version=version)
                self.assertEqual("--standalone" in argv, expected, argv)

    @unittest.skipUnless(DARWIN_SANDBOX, "macOS sandbox-exec only")
    def test_prompt_equal_to_standalone_still_gets_flag(self):
        template = ("{taskdir}", "{access_args}", "run", "{spec}")
        argv, _ = self.run_engine(full_access=False, template=template, spec="--standalone")
        self.assertEqual(argv, ["run", "--standalone", "--standalone"])

    @unittest.skipUnless(DARWIN_SANDBOX, "macOS sandbox-exec only")
    def test_override_forces_choice(self):
        argv, _ = self.run_engine(full_access=False, version="1.18.3",
                                  extra_env={"RINGER_OPENCODE_STANDALONE": "1"})
        self.assertIn("--standalone", argv)
        argv, _ = self.run_engine(full_access=False, extra_env={"RINGER_OPENCODE_STANDALONE": "0"})
        self.assertNotIn("--standalone", argv)

    def test_full_access_gets_no_standalone(self):
        argv, _ = self.run_engine(full_access=True)
        self.assertNotIn("--standalone", argv)


class SampleConfig(unittest.TestCase):
    def test_sample_opencode_template_has_no_dir_flag(self):
        text = SAMPLE.read_text()
        block = re.search(r"^# \[engines\.opencode\]\n((?:#.*\n)+?)# sandbox_args", text, re.M)
        self.assertIsNotNone(block, "commented [engines.opencode] example not found")
        body = "\n".join(line[2:] for line in block.group(1).splitlines())
        template = tomllib.loads(body)["args_template"]
        self.assertNotIn("--dir", template)
        self.assertEqual(template[:3], ["{taskdir}", "{access_args}", "run"])
        self.assertEqual(template[-1], "{spec}")
        for line in text.splitlines():
            if line.startswith("# args_template = ["):
                self.assertNotIn('"--dir"', line, line)


if __name__ == "__main__":
    unittest.main()
