#!/usr/bin/env python3
"""A sandboxed opencode worker cannot change its own permissions through config.

OpenCode reads project config (opencode.json, opencode.jsonc and the
.opencode folder) from the task dir and every dir above it. The worker can write its task dir, so it could write permission rules
there, and in worktrees mode a repo could ship them (board card 2153,
option B; Boyd chose this fix on card 2288, 2026-11-02).

engines/opencode-sandboxed.sh now:

- removes OPENCODE_CONFIG_PROJECT_DISABLE and sets
  OPENCODE_DISABLE_PROJECT_CONFIG=1 for the sandboxed worker. OpenCode 2.2.5
  read project config again when both names were set, even both to 1
  (`opencode debug config --standalone`, klipsch, 2026-11-02), so exactly
  one name is set;
- leaves the environment alone with RINGER_OPENCODE_PROJECT_CONFIG=1 (a repo
  the operator trusts) and on the --no-sandbox path;
- on Linux, mounts the provider keys file (OPENCODE_CONFIG, in the writable
  scratch dir) read-only, because OpenCode watches that file for changes.

The real-OpenCode check is in test_real_opencode_ignores_task_dir_config and
runs only when OPENCODE_BIN points at an OpenCode 2.x executable.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRAP = ROOT / "engines" / "opencode-sandboxed.sh"
BWRAP = shutil.which("bwrap")
LINUX_BWRAP = sys.platform.startswith("linux") and BWRAP is not None
DARWIN_SANDBOX = sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").exists()
SANDBOX = LINUX_BWRAP or DARWIN_SANDBOX
STUB = '#!/bin/sh\nif [ "$1" = "--version" ]; then echo "opencode v2.2.5"; exit 0; fi\nexec sh -c "$STUB_SCRIPT"\n'
KEY = "sk-or-v1-TEST-KEY-0123456789"

SHOW_ENV = ('echo "NEW=${OPENCODE_CONFIG_PROJECT_DISABLE-<unset>}"; '
            'echo "OLD=${OPENCODE_DISABLE_PROJECT_CONFIG-<unset>}"')


class ProjectConfigBase(unittest.TestCase):
    def setUp(self):
        base = Path.home() / ".cache" / "ringer-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        d = Path(self.tmp.name)
        self.home = d / "home"
        self.share = self.home / ".local" / "share" / "opencode"
        self.share.mkdir(parents=True)
        (self.home / ".local" / "state" / "opencode").mkdir(parents=True)
        (self.home / ".config" / "opencode").mkdir(parents=True)
        self.bindir = d / "bin"
        self.bindir.mkdir()
        self.stub = self.bindir / "opencode"
        self.stub.write_text(STUB)
        self.stub.chmod(self.stub.stat().st_mode | stat.S_IEXEC)
        self.taskdir = d / "work" / "t1"
        self.taskdir.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def run_wrapped(self, script, *, extra_env=None, no_sandbox=False, args=("run", "x")):
        env = {k: v for k, v in os.environ.items()
               if not k.endswith("_API_KEY") and not k.startswith("OPENCODE_")
               and not k.startswith("RINGER_OPENCODE_")}
        env.update(HOME=str(self.home), OPENCODE_BIN=str(self.stub), STUB_SCRIPT=script)
        env.update(extra_env or {})
        argv = [str(WRAP), str(self.taskdir)] + (["--no-sandbox"] if no_sandbox else []) + list(args)
        r = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=60,
                           stdin=subprocess.DEVNULL, cwd=self.taskdir)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def env_inside(self, **kw):
        r = self.run_wrapped(SHOW_ENV, **kw)
        return dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)


@unittest.skipUnless(SANDBOX, "needs bwrap (Linux) or sandbox-exec (macOS)")
class ProjectConfigOff(ProjectConfigBase):
    def test_project_config_is_off_inside_sandbox(self):
        vals = self.env_inside()
        self.assertEqual(vals, {"NEW": "<unset>", "OLD": "1"})

    def test_caller_value_of_newer_name_is_removed(self):
        # With both names set, OpenCode 2.2.5 read project config again.
        for value in ("0", "1", "", "true"):
            with self.subTest(value=value):
                vals = self.env_inside(extra_env={"OPENCODE_CONFIG_PROJECT_DISABLE": value})
                self.assertEqual(vals, {"NEW": "<unset>", "OLD": "1"})

    def test_caller_cannot_turn_it_back_on_with_older_name(self):
        vals = self.env_inside(extra_env={"OPENCODE_DISABLE_PROJECT_CONFIG": "0"})
        self.assertEqual(vals, {"NEW": "<unset>", "OLD": "1"})

    def test_opt_out_leaves_environment_alone(self):
        vals = self.env_inside(extra_env={"RINGER_OPENCODE_PROJECT_CONFIG": "1"})
        self.assertEqual(vals, {"NEW": "<unset>", "OLD": "<unset>"})
        vals = self.env_inside(extra_env={"RINGER_OPENCODE_PROJECT_CONFIG": "1",
                                          "OPENCODE_CONFIG_PROJECT_DISABLE": "0"})
        self.assertEqual(vals, {"NEW": "0", "OLD": "<unset>"})

    def test_other_opt_out_values_do_not_count(self):
        for value in ("0", "yes", "true", ""):
            with self.subTest(value=value):
                vals = self.env_inside(extra_env={"RINGER_OPENCODE_PROJECT_CONFIG": value})
                self.assertEqual(vals, {"NEW": "<unset>", "OLD": "1"})

    def test_non_run_commands_get_it_too(self):
        vals = self.env_inside(args=("debug", "config"))
        self.assertEqual(vals, {"NEW": "<unset>", "OLD": "1"})


class NoSandboxUnchanged(ProjectConfigBase):
    def test_full_access_path_is_unchanged(self):
        vals = self.env_inside(no_sandbox=True, extra_env={"OPENCODE_CONFIG_PROJECT_DISABLE": "0"})
        self.assertEqual(vals, {"NEW": "0", "OLD": "<unset>"})


@unittest.skipUnless(LINUX_BWRAP, "Linux with bwrap only")
class KeysFileReadOnly(ProjectConfigBase):
    def write_auth(self):
        auth = self.share / "auth.json"
        auth.write_text(json.dumps({"openrouter": {"type": "api", "key": KEY}}))
        auth.chmod(0o600)

    def test_worker_cannot_change_keys_config(self):
        self.write_auth()
        script = (
            'f="$OPENCODE_CONFIG"; '
            'if printf "%s" "{\\"permission\\":{\\"bash\\":\\"allow\\"}}" > "$f" 2>/dev/null; '
            'then echo WRITE=ok; else echo WRITE=denied; fi; '
            'if rm -f "$f" 2>/dev/null && [ ! -e "$f" ]; then echo RM=ok; else echo RM=denied; fi; '
            'if mv "$f" "$f.x" 2>/dev/null; then echo MV=ok; else echo MV=denied; fi; '
            'printf "JSON="; cat "$f"; echo'
        )
        r = self.run_wrapped(script)
        vals = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
        self.assertEqual(vals["WRITE"], "denied")
        self.assertEqual(vals["RM"], "denied")
        self.assertEqual(vals["MV"], "denied")
        self.assertEqual(json.loads(vals["JSON"]),
                         {"provider": {"openrouter": {"options": {"apiKey": KEY}}}})
        self.assertNotIn(KEY, r.stderr)

    def test_rest_of_scratch_stays_writable(self):
        self.write_auth()
        r = self.run_wrapped('echo hi > "$TMPDIR/note" && cat "$TMPDIR/note" && echo hi > note.txt && cat note.txt')
        self.assertEqual(r.stdout.split(), ["hi", "hi"])

    def test_no_keys_file_still_runs(self):
        r = self.run_wrapped('echo "CFG=${OPENCODE_CONFIG-<unset>}"')
        self.assertIn("CFG=<unset>", r.stdout)


def real_opencode():
    path = os.environ.get("OPENCODE_BIN")
    if not path or not os.access(path, os.X_OK):
        return None
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=30,
                             stdin=subprocess.DEVNULL).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    return path if out.split() and out.split()[-1].lstrip("v").split(".")[0].isdigit() \
        and int(out.split()[-1].lstrip("v").split(".")[0]) >= 2 else None


@unittest.skipUnless(SANDBOX and real_opencode(), "set OPENCODE_BIN to an OpenCode 2.x executable")
class RealOpencode(unittest.TestCase):
    def test_real_opencode_ignores_task_dir_config(self):
        cache = Path.home() / ".cache" / "ringer-tests"
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as d:
            # A fake HOME, so no real auth.json is copied into the sandbox.
            home = Path(d) / "home"
            (home / ".config" / "opencode").mkdir(parents=True)
            (home / ".config" / "opencode" / "opencode.json").write_text('{"username":"GLOBAL"}\n')
            (home / ".local" / "share" / "opencode").mkdir(parents=True)
            (home / ".local" / "state" / "opencode").mkdir(parents=True)
            task = Path(d) / "task"
            (task / ".opencode").mkdir(parents=True)
            (task / "opencode.json").write_text('{"username":"WORKER-SET-FILE"}\n')
            (task / ".opencode" / "opencode.json").write_text('{"username":"WORKER-SET-DIR"}\n')
            base = {k: v for k, v in os.environ.items()
                    if not k.startswith("OPENCODE_") and not k.startswith("RINGER_OPENCODE_")
                    and not k.endswith("_API_KEY") and not k.startswith("XDG_")}
            base.update(OPENCODE_BIN=real_opencode(), HOME=str(home))

            def config(**extra):
                r = subprocess.run([str(WRAP), str(task), "debug", "config", "--standalone"],
                                   env=dict(base, **extra), capture_output=True, text=True,
                                   timeout=120, stdin=subprocess.DEVNULL)
                self.assertEqual(r.returncode, 0, r.stderr[-2000:])
                return r.stdout

            for extra in ({}, {"OPENCODE_CONFIG_PROJECT_DISABLE": "0"},
                          {"OPENCODE_CONFIG_PROJECT_DISABLE": "1"}):
                with self.subTest(env=extra):
                    out = config(**extra)
                    self.assertIn("GLOBAL", out, "the global config should still load")
                    self.assertNotIn("WORKER-SET", out)
            out = config(RINGER_OPENCODE_PROJECT_CONFIG="1")
            self.assertIn("WORKER-SET-FILE", out, "the opt-out should load project config")


if __name__ == "__main__":
    unittest.main()
