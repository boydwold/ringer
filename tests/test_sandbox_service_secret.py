#!/usr/bin/env python3
"""A sandboxed opencode worker cannot read the shared service's password.

OpenCode 2.x runs a shared background service outside the sandbox, on
127.0.0.1 (port 49374 by default), and the Linux sandbox shares the host
network. The service's record in <state>/opencode/service.json always holds
its password; <config>/opencode/service.json holds one after `opencode service
set password` (service-*.json for versioned builds). OPENCODE_PASSWORD and
OPENCODE_SERVER_PASSWORD can also carry it. Before this fix a Linux worker
could read the config file through the read-only root mount, so it could
likely ask the service to run commands with no sandbox (found by a refute
pass on 2026-11-02; Boyd chose this fix on board card 2292). Nobody tried it
against a live service.

engines/opencode-sandboxed.sh now removes both variables, hides every
opencode state dir whole (the service replaces its record by rename, which
would remove a mount over one file), and mounts /dev/null over each config
service file that exists. bwrap mounts it nodev, so a read fails with
"Permission denied". On macOS a fixed Seatbelt rule denies reading and writing
any .../opencode/service*.json; this file checks only the profile text there.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRAP = ROOT / "engines" / "opencode-sandboxed.sh"
BWRAP = shutil.which("bwrap")
LINUX_BWRAP = sys.platform.startswith("linux") and BWRAP is not None
STUB = '#!/bin/sh\nif [ "$1" = "--version" ]; then echo "opencode v2.2.5"; exit 0; fi\nexec sh -c "$STUB_SCRIPT"\n'
SECRET = "FAKE-SERVICE-PASSWORD-0123"


@unittest.skipUnless(LINUX_BWRAP, "Linux with bwrap only")
class ServiceSecretHidden(unittest.TestCase):
    def setUp(self):
        base = Path.home() / ".cache" / "ringer-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        d = Path(self.tmp.name)
        self.home = d / "home"
        self.config = self.home / ".config" / "opencode"
        self.state = self.home / ".local" / "state" / "opencode"
        self.config.mkdir(parents=True)
        self.state.mkdir(parents=True)
        (self.home / ".local" / "share" / "opencode").mkdir(parents=True)
        (self.config / "opencode.json").write_text('{"username":"GLOBAL"}\n')
        self.bindir = d / "bin"
        self.bindir.mkdir()
        self.stub = self.bindir / "opencode"
        self.stub.write_text(STUB)
        self.stub.chmod(self.stub.stat().st_mode | stat.S_IEXEC)
        self.taskdir = d / "work" / "t1"
        self.taskdir.mkdir(parents=True)
        self.d = d

    def tearDown(self):
        self.tmp.cleanup()

    def secret_file(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"password":"%s"}\n' % SECRET)
        path.chmod(0o600)
        return path

    def run_wrapped(self, script, extra_env=None):
        env = {k: v for k, v in os.environ.items()
               if not k.endswith("_API_KEY") and not k.startswith("OPENCODE_")
               and not k.startswith("XDG_") and not k.startswith("RINGER_OPENCODE_")}
        env.update(HOME=str(self.home), OPENCODE_BIN=str(self.stub), STUB_SCRIPT=script)
        env.update(extra_env or {})
        r = subprocess.run([str(WRAP), str(self.taskdir), "run", "x"], env=env, capture_output=True,
                           text=True, timeout=60, stdin=subprocess.DEVNULL, cwd=self.taskdir)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def read_inside(self, paths, extra_env=None):
        script = " ; ".join(f'printf "%s\\n" "== {p}"; cat "{p}" 2>&1' for p in paths) + "; true"
        out = self.run_wrapped(script, extra_env).stdout
        for p in paths:
            self.assertIn(f"== {p}", out)
        return out

    def test_default_config_service_file_hidden(self):
        f = self.secret_file(self.config / "service.json")
        out = self.read_inside([f])
        self.assertNotIn(SECRET, out)
        self.assertIn(f"== {f}", out)

    def test_versioned_service_files_hidden(self):
        files = [self.secret_file(self.config / "service-beta.json"),
                 self.secret_file(self.config / "service-0123abcd.json")]
        out = self.read_inside(files)
        self.assertNotIn(SECRET, out)

    def test_custom_xdg_config_and_state_dirs(self):
        xc = self.d / "xdg-config"
        xs = self.d / "xdg-state"
        (xc / "opencode").mkdir(parents=True)
        (xc / "opencode" / "opencode.json").write_text("{}\n")
        files = [self.secret_file(xc / "opencode" / "service.json"),
                 self.secret_file(xs / "opencode" / "service.json"),
                 self.secret_file(self.config / "service.json")]
        out = self.read_inside(files, {"XDG_CONFIG_HOME": str(xc), "XDG_STATE_HOME": str(xs)})
        self.assertNotIn(SECRET, out)

    def test_default_state_record_hidden(self):
        f = self.secret_file(self.state / "service.json")
        out = self.read_inside([f])
        self.assertNotIn(SECRET, out)

    def test_password_variables_removed(self):
        out = self.run_wrapped('echo "P=${OPENCODE_PASSWORD:-unset} S=${OPENCODE_SERVER_PASSWORD:-unset}"',
                               {"OPENCODE_PASSWORD": SECRET, "OPENCODE_SERVER_PASSWORD": SECRET}).stdout
        self.assertNotIn(SECRET, out)
        self.assertIn("P=unset S=unset", out)

    def test_custom_state_dir_hidden_whole(self):
        xs = self.d / "xdg-state"
        files = [self.secret_file(xs / "opencode" / "pty" / "abc" / "service.json"),
                 self.secret_file(xs / "opencode" / "service.json.pty-handoff"),
                 self.secret_file(xs / "opencode" / "service.json.1.tmp")]
        out = self.read_inside(files, {"XDG_STATE_HOME": str(xs)})
        self.assertNotIn(SECRET, out)

    def test_custom_state_record_replaced_during_run(self):
        # The service writes service.json.<id>.tmp and renames it over
        # service.json on each start. A rename removes a mount over one file.
        xs = self.d / "xdg-state"
        rec = self.secret_file(xs / "opencode" / "service.json")
        ready, go = self.taskdir / "ready", self.taskdir / "go"
        script = (f'touch "{ready}"; i=0; while [ ! -e "{go}" ] && [ $i -lt 200 ]; do sleep 0.05; i=$((i+1)); done; '
                  f'printf "%s\\n" "== {rec}"; cat "{rec}" 2>&1; ls "{rec.parent}" 2>&1; true')
        env = {k: v for k, v in os.environ.items()
               if not k.endswith("_API_KEY") and not k.startswith("OPENCODE_")
               and not k.startswith("XDG_") and not k.startswith("RINGER_OPENCODE_")}
        env.update(HOME=str(self.home), OPENCODE_BIN=str(self.stub), STUB_SCRIPT=script,
                   XDG_STATE_HOME=str(xs))
        p = subprocess.Popen([str(WRAP), str(self.taskdir), "run", "x"], env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL, cwd=self.taskdir)
        for _ in range(400):
            if ready.exists() or p.poll() is not None:
                break
            time.sleep(0.05)
        self.assertTrue(ready.exists(), "worker did not start")
        tmp = rec.parent / "service.json.2.tmp"
        tmp.write_text('{"password":"%s-NEW"}\n' % SECRET)
        tmp.rename(rec)
        go.touch()
        out, err = p.communicate(timeout=60)
        self.assertEqual(p.returncode, 0, err)
        self.assertIn(f"== {rec}", out)
        self.assertNotIn(SECRET, out)

    def test_symlinked_config_service_file_hidden(self):
        target = self.secret_file(self.d / "dotfiles" / "service.json")
        link = self.config / "service.json"
        link.symlink_to(target)
        out = self.read_inside([link, target])
        self.assertNotIn(SECRET, out)

    def test_opencode_config_dir_service_file_hidden(self):
        cd = self.d / "custom-config"
        f = self.secret_file(cd / "service.json")
        out = self.read_inside([f], {"OPENCODE_CONFIG_DIR": str(cd)})
        self.assertNotIn(SECRET, out)

    def test_relative_state_dir_hidden(self):
        # The wrapper runs from the task dir; this path is relative to it.
        xs = self.d / "xs-rel"
        f = self.secret_file(xs / "opencode" / "service.json")
        out = self.read_inside([f], {"XDG_STATE_HOME": "../../xs-rel"})
        self.assertNotIn(SECRET, out)

    def test_symlinked_custom_state_dir_hidden(self):
        real = self.d / "real-state"
        f = self.secret_file(real / "service.json")
        xs = self.d / "xs-link"
        xs.mkdir()
        (xs / "opencode").symlink_to(real)
        out = self.read_inside([xs / "opencode" / "service.json", f], {"XDG_STATE_HOME": str(xs)})
        self.assertNotIn(SECRET, out)

    def test_symlinked_default_state_dir_hidden(self):
        real = self.d / "real-default-state"
        f = self.secret_file(real / "service.json")
        shutil.rmtree(self.state)
        self.state.symlink_to(real)
        out = self.read_inside([self.state / "service.json", f])
        self.assertNotIn(SECRET, out)

    def run_expect_refusal(self, extra_env):
        env = {k: v for k, v in os.environ.items()
               if not k.endswith("_API_KEY") and not k.startswith("OPENCODE_")
               and not k.startswith("XDG_") and not k.startswith("RINGER_OPENCODE_")}
        env.update(HOME=str(self.home), OPENCODE_BIN=str(self.stub), STUB_SCRIPT=f'cat "{self.taskdir}"/*/opencode/service.json; echo RAN')
        env.update(extra_env)
        r = subprocess.run([str(WRAP), str(self.taskdir), "run", "x"], env=env, capture_output=True,
                           text=True, timeout=60, stdin=subprocess.DEVNULL, cwd=self.taskdir)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("RAN", r.stdout)
        self.assertNotIn(SECRET, r.stdout)
        return r

    def test_relative_opencode_config_dir_refused(self):
        self.secret_file(self.d / "cfg" / "service.json")
        r = self.run_expect_refusal({"OPENCODE_CONFIG_DIR": "cfg"})
        self.assertIn("absolute", r.stderr)

    def test_state_dir_inside_taskdir_refused(self):
        xs = self.taskdir / "xs"
        self.secret_file(xs / "opencode" / "service.json")
        r = self.run_expect_refusal({"XDG_STATE_HOME": str(xs)})
        self.assertIn("inside the task", r.stderr)

    def test_symlinked_share_dir_runs(self):
        share = self.home / ".local" / "share" / "opencode"
        real = self.d / "real-share"
        real.mkdir()
        (real / "auth.json").write_text('{"k":"%s"}\n' % SECRET)
        share.rmdir()
        share.symlink_to(real)
        out = self.read_inside([share / "auth.json"])
        self.assertNotIn(SECRET, out)

    def test_global_config_still_readable(self):
        self.secret_file(self.config / "service.json")
        out = self.read_inside([self.config / "opencode.json"])
        self.assertIn("GLOBAL", out)

    def test_host_files_are_unchanged(self):
        f = self.secret_file(self.config / "service.json")
        self.run_wrapped(f'echo x > "{f}" 2>/dev/null; true')
        self.assertIn(SECRET, f.read_text())

    def test_no_service_files_still_runs(self):
        r = self.run_wrapped("echo ran")
        self.assertEqual(r.stdout.strip(), "ran")


class DarwinProfile(unittest.TestCase):
    def test_profile_denies_service_files(self):
        text = WRAP.read_text()
        profile = text[text.index("<<'SBEOF'"):text.index("\nSBEOF\n")]
        self.assertIn('(deny file-read* file-write*\n  (regex #"/opencode/service[^/]*\\.json$"))', profile)


if __name__ == "__main__":
    unittest.main()
