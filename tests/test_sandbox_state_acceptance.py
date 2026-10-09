#!/usr/bin/env python3
"""Acceptance tests: per-attempt opencode state on Linux (openspec change
trusted-multi-model-tracking, spec worker-sandbox "Per-attempt engine state on
Linux"; task 9.1).

Contract under test (engines/opencode-sandboxed.sh, Linux branch):
  inside the sandbox XDG_DATA_HOME and XDG_STATE_HOME point at fresh
  directories inside this attempt's scratch dir; if $HOME/.local/share/opencode/
  auth.json exists it is copied to $XDG_DATA_HOME/opencode/auth.json (mode 600);
  the real $HOME/.local/share/opencode and $HOME/.local/state/opencode are hidden
  (their real contents can't be read) and are unchanged after the attempt;
  parallel attempts get different data dirs.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRAP = ROOT / "engines" / "opencode-sandboxed.sh"
LINUX_BWRAP = sys.platform.startswith("linux") and shutil.which("bwrap") is not None
STUB = '#!/bin/sh\nexec sh -c "$STUB_SCRIPT"\n'


@unittest.skipUnless(LINUX_BWRAP, "Linux with bwrap only")
class PerAttemptState(unittest.TestCase):
    def setUp(self):
        base = Path.home() / ".cache" / "ringer-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        d = Path(self.tmp.name)
        self.home = d / "home"
        self.share = self.home / ".local" / "share" / "opencode"
        self.state = self.home / ".local" / "state" / "opencode"
        self.share.mkdir(parents=True)
        self.state.mkdir(parents=True)
        self.auth = self.share / "auth.json"
        self.auth.write_text('{"openrouter":{"type":"api","key":"SECRET-MAIN-KEY"}}\n')
        self.auth.chmod(0o600)
        (self.share / "opencode.db").write_text("HISTORY\n")
        (self.home / ".config" / "opencode").mkdir(parents=True)
        self.stub = d / "bin" / "opencode"
        self.stub.parent.mkdir()
        self.stub.write_text(STUB)
        self.stub.chmod(self.stub.stat().st_mode | stat.S_IEXEC)
        self.work = d / "work"

    def tearDown(self):
        self.tmp.cleanup()

    def run_wrapped(self, key, script):
        taskdir = self.work / key
        taskdir.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, HOME=str(self.home), OPENCODE_BIN=str(self.stub), STUB_SCRIPT=script,
                   PATH=str(self.stub.parent) + os.pathsep + os.environ.get("PATH", ""))
        return subprocess.run([str(WRAP), str(taskdir), "run", "x"], env=env, capture_output=True, text=True,
                              timeout=60, stdin=subprocess.DEVNULL)

    def test_xdg_dirs_are_per_attempt_scratch(self):
        r = self.run_wrapped("a", 'echo "DATA=$XDG_DATA_HOME"; echo "STATE=$XDG_STATE_HOME"; echo "TMP=$TMPDIR"')
        self.assertEqual(r.returncode, 0, r.stderr)
        vals = dict(l.split("=", 1) for l in r.stdout.splitlines() if "=" in l)
        for k in ("DATA", "STATE"):
            self.assertTrue(vals[k], k)
            self.assertFalse(vals[k].startswith(str(self.home / ".local")), f"{k} must not be the real dir")
            self.assertTrue(vals[k].startswith(vals["TMP"]), f"{k} must live in this attempt's scratch")

    def test_stored_key_copied_in_and_real_file_hidden(self):
        script = (f'cat "$XDG_DATA_HOME/opencode/auth.json"; echo "--"; '
                  f'cat "{self.auth}" 2>&1; echo "--"; cat "{self.share}/opencode.db" 2>&1; echo "--"; '
                  f'stat -c %a "$XDG_DATA_HOME/opencode/auth.json"; '
                  f'echo tampered > "{self.auth}" 2>/dev/null; true')
        r = self.run_wrapped("b", script)
        parts = r.stdout.split("--\n")
        self.assertIn("SECRET-MAIN-KEY", parts[0], "the stored key is copied into the attempt's data dir")
        self.assertNotIn("SECRET-MAIN-KEY", parts[1], "the real auth.json must be hidden")
        self.assertNotIn("HISTORY", parts[2], "the real opencode history must be hidden")
        self.assertEqual(parts[3].strip(), "600")
        self.assertEqual(self.auth.read_text(), '{"openrouter":{"type":"api","key":"SECRET-MAIN-KEY"}}\n')
        self.assertEqual((self.share / "opencode.db").read_text(), "HISTORY\n")

    def test_no_stored_key_still_runs(self):
        self.auth.unlink()
        r = self.run_wrapped("c", 'test -d "$XDG_DATA_HOME/opencode" && echo ok')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ok", r.stdout)

    def test_parallel_attempts_get_separate_databases(self):
        results = {}

        def go(key):
            results[key] = self.run_wrapped(key, 'echo "$XDG_DATA_HOME"; echo db > "$XDG_DATA_HOME/opencode/opencode.db"; sleep 1')

        threads = [threading.Thread(target=go, args=(k,)) for k in ("p1", "p2")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        dirs = {k: r.stdout.strip().splitlines()[0] for k, r in results.items()}
        for k, r in results.items():
            self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotEqual(dirs["p1"], dirs["p2"])


if __name__ == "__main__":
    unittest.main()
