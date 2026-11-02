#!/usr/bin/env python3
"""A Linux sandbox run removes scratch dirs that killed runs left behind.

Each run of engines/opencode-sandboxed.sh on Linux makes a scratch dir with a
copy of auth.json and, on OpenCode 2.2.5+, a provider keys file. An EXIT trap
removes it, but a SIGKILL skips the trap, so the keys stayed on disk.

Now each run holds a flock on its scratch dir itself for its whole life, then
writes a .ringer-lock marker, and bwrap dies with the wrapper
(--die-with-parent). At start, a run removes every dir next to its own scratch
that is named ringer-opencode.XXXXXX, is a real dir (not a symlink), is ours,
and is not locked by a live run, when it either has the marker or is older
than one day (no marker: an older wrapper, or a run without flock, which never
locks). The lock is not open in the worker. The worker can write inside its
scratch dir but cannot replace the dir, so it cannot fake, move or release its
own run's lock, and the sweep never opens a file the worker controls.
"""
from __future__ import annotations

import os
import select
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRAP = ROOT / "engines" / "opencode-sandboxed.sh"
LINUX_BWRAP = (sys.platform.startswith("linux") and shutil.which("bwrap") is not None
               and shutil.which("flock") is not None)
STUB = '#!/bin/sh\nif [ "$1" = "--version" ]; then exit 0; fi\nexec sh -c "$STUB_SCRIPT"\n'
KEY = "sk-or-v1-TEST-KEY-0123456789"
HOURS = 3600           # seconds
ANCIENT = 2 * 86400    # seconds: past the one-day limit for a dir with no marker
READY = 'echo "READY $TMPDIR"; exec sleep 60'


def age(path: Path, seconds: int) -> None:
    t = time.time() - seconds
    os.utime(path, (t, t), follow_symlinks=False)


@unittest.skipUnless(LINUX_BWRAP, "Linux with bwrap and flock only")
class ScratchSweep(unittest.TestCase):
    def setUp(self):
        base = Path.home() / ".cache" / "ringer-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        d = Path(self.tmp.name)
        self.home = d / "home"
        share = self.home / ".local" / "share" / "opencode"
        share.mkdir(parents=True)
        (self.home / ".local" / "state" / "opencode").mkdir(parents=True)
        (share / "auth.json").write_text('{"openrouter": {"type": "api", "key": "%s"}}' % KEY)
        (share / "auth.json").chmod(0o600)
        self.bindir = d / "bin"
        self.bindir.mkdir()
        self.stub = self.bindir / "opencode"
        self.stub.write_text(STUB)
        self.stub.chmod(self.stub.stat().st_mode | stat.S_IEXEC)
        self.taskdir = d / "work" / "t1"
        self.taskdir.mkdir(parents=True)
        self.scratch_root = d / "scratch-root"
        self.scratch_root.mkdir()

    def tearDown(self):
        for p in self.scratch_root.rglob("*"):
            if p.is_dir() and not p.is_symlink():
                p.chmod(0o700)
        self.tmp.cleanup()

    def env(self, script, path=None):
        env = {k: v for k, v in os.environ.items()
               if not k.endswith("_API_KEY") and not k.startswith("OPENCODE_CONFIG")}
        env.update(HOME=str(self.home), OPENCODE_BIN=str(self.stub), STUB_SCRIPT=script,
                   TMPDIR=str(self.scratch_root),
                   PATH=path or os.pathsep.join((str(self.bindir), os.environ.get("PATH", ""))))
        return env

    def run_wrapped(self, script="true", expect_rc=0):
        r = subprocess.run([str(WRAP), str(self.taskdir), "run", "x"], env=self.env(script),
                           capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, expect_rc, r.stderr)
        return r

    def start_wrapped(self, script=READY, path=None):
        """Start a run that prints READY <scratch> and then keeps running."""
        p = subprocess.Popen([str(WRAP), str(self.taskdir), "run", "x"], env=self.env(script, path),
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL, text=True)
        self.addCleanup(self.stop, p)
        line = p.stdout.readline()
        self.assertTrue(line.startswith("READY "), line)
        return p, Path(line.split(" ", 1)[1].strip())

    @staticmethod
    def stop(p):
        if p.poll() is None:
            p.kill()
        p.wait(timeout=10)
        p.stdout.close()

    @staticmethod
    def lock_free(d):
        return subprocess.run(["flock", "-n", str(d), "true"]).returncode == 0

    def leftover(self, name="ringer-opencode.AbC123", marker=True, dir_age=None):
        d = self.scratch_root / name
        (d / "data" / "opencode").mkdir(parents=True)
        (d / "data" / "opencode" / "auth.json").write_text(KEY)
        (d / "ringer-provider-keys.json").write_text(KEY)
        if marker:
            (d / ".ringer-lock").touch()
        if dir_age is not None:
            age(d, dir_age)
        return d

    def test_dead_run_scratch_removed(self):
        d = self.leftover()
        self.run_wrapped()
        self.assertFalse(d.exists())
        self.assertEqual(list(self.scratch_root.iterdir()), [])

    def test_sigkilled_run_is_cleaned_by_next_run(self):
        p, scratch = self.start_wrapped()
        os.kill(p.pid, signal.SIGKILL)
        p.wait(timeout=10)
        # The worker held the other end of stdout; EOF means it died too.
        ready, _, _ = select.select([p.stdout], [], [], 10)
        self.assertTrue(ready and p.stdout.read() == "", "the worker outlived the wrapper")
        self.assertTrue((scratch / "ringer-provider-keys.json").exists(),
                        "a SIGKILL skips the EXIT trap, so the keys stay")
        for _ in range(50):  # bwrap and the worker die with the wrapper
            if self.lock_free(scratch):
                break
            time.sleep(0.1)
        else:
            self.fail("the lock is still held after the wrapper died")
        self.run_wrapped()
        self.assertFalse(scratch.exists())

    def test_live_run_scratch_kept_without_waiting(self):
        _, scratch = self.start_wrapped()
        started = time.monotonic()
        self.run_wrapped()
        self.assertLess(time.monotonic() - started, 2.5, "the sweep must not wait for a live run")
        self.assertTrue((scratch / "ringer-provider-keys.json").exists())

    def test_live_run_kept_when_its_worker_fakes_its_marker(self):
        _, scratch = self.start_wrapped(
            'rm -f "$TMPDIR/.ringer-lock"; : > "$TMPDIR/.ringer-lock"; '
            'touch -d "-3 days" "$TMPDIR/.ringer-lock" "$TMPDIR"; ' + READY)
        self.run_wrapped()
        self.assertTrue((scratch / "ringer-provider-keys.json").exists())

    def test_live_run_without_flock_kept(self):
        nofl = Path(self.tmp.name) / "noflock"
        nofl.mkdir()
        for tool in Path("/usr/bin").iterdir():
            if tool.name != "flock":
                (nofl / tool.name).symlink_to(tool)
        _, scratch = self.start_wrapped(path=os.pathsep.join((str(self.bindir), str(nofl))))
        self.assertFalse((scratch / ".ringer-lock").exists(), "no flock, so no marker")
        age(scratch, 2 * HOURS)
        self.run_wrapped()
        self.assertTrue((scratch / "ringer-provider-keys.json").exists())

    def test_scratch_without_marker_removed_after_a_day(self):
        old = self.leftover("ringer-opencode.OLDOLD", marker=False, dir_age=ANCIENT)
        new = self.leftover("ringer-opencode.NEWNEW", marker=False, dir_age=int(23.5 * HOURS))
        edge = self.leftover("ringer-opencode.EDGE24", marker=False, dir_age=int(24.5 * HOURS))
        self.run_wrapped()
        self.assertFalse(old.exists())
        self.assertFalse(edge.exists())
        self.assertTrue(new.exists(), "an older wrapper may still be running with it")

    def test_marker_symlink_is_never_followed(self):
        target = Path(self.tmp.name) / "outside" / "PWNED"
        target.parent.mkdir()
        d = self.leftover(marker=False)
        (d / ".ringer-lock").symlink_to(target)
        self.run_wrapped()
        self.assertFalse(d.exists())
        self.assertFalse(target.exists())

    def test_nested_dirs_kept(self):
        nested = self.leftover("deeper/ringer-opencode.NeSt12")
        self.run_wrapped()
        self.assertTrue((nested / "ringer-provider-keys.json").exists())

    def test_no_sweep_when_scratch_parent_is_in_task_dir(self):
        self.scratch_root = self.taskdir / "tmp"
        self.scratch_root.mkdir()
        d = self.leftover()
        self.run_wrapped()
        self.assertTrue(d.exists(), "the worker can rename entries in its task dir")

    def test_other_names_and_symlinks_kept(self):
        others = [self.leftover(n) for n in ("ringer-opencode.TOOLONG1", "ringer-opencode.AB12",
                                             "ringer-opencode-scratch.AbC123", "other.AbC123")]
        target = self.leftover("not-ours")
        link = self.scratch_root / "ringer-opencode.LnK123"
        link.symlink_to(target)
        self.run_wrapped()
        for d in others + [target]:
            self.assertTrue((d / "ringer-provider-keys.json").exists(), d.name)
        self.assertTrue(link.is_symlink())

    def test_unremovable_leftover_does_not_stop_the_run(self):
        d = self.leftover()
        (d / "data").chmod(0o500)  # rm -rf cannot empty it
        r = self.run_wrapped('echo worker-ran')
        self.assertIn("worker-ran", r.stdout)

    def test_lock_not_open_in_worker_and_held_during_run(self):
        r = self.run_wrapped(
            'for f in /proc/self/fd/*; do echo "FD $(readlink "$f")"; done; echo "TMP $TMPDIR"; '
            'if flock -n "$TMPDIR" true; then echo LOCK-FREE; else echo LOCK-HELD; fi')
        lines = r.stdout.splitlines()
        tmp = next(line[4:] for line in lines if line.startswith("TMP "))
        self.assertNotIn(tmp, [line[3:] for line in lines if line.startswith("FD ")])
        self.assertIn("LOCK-HELD", r.stdout)

    def test_own_scratch_still_removed_after_run(self):
        self.run_wrapped('test -f "$TMPDIR/.ringer-lock"')
        self.assertEqual(list(self.scratch_root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
