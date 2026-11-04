#!/usr/bin/env python3
"""The macOS sandbox hides the login keys and the key agent (Boyd's decision
on board item 2421, 2026-11-03).

The sandbox shares the network. With an ssh key or the key agent, a worker
could log in to the other computer and from there back to this one, outside
the sandbox. engines/opencode-sandboxed.sh hides ~/.ssh and denies connecting
to the agent's socket.

The profile-text tests run everywhere. The acceptance tests run only on
macOS, with a fake HOME, a fake key and fake agent sockets.
"""
from __future__ import annotations

import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRAP = ROOT / "engines" / "opencode-sandboxed.sh"
ON_MAC = sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").exists()
PY = os.path.realpath(sys.executable)


class DarwinProfileLoginKeys(unittest.TestCase):
    def test_wrapper_hides_ssh_folder(self):
        self.assertIn('always_hide "$HOME/.ssh"', WRAP.read_text())

    def test_profile_denies_launchd_agent(self):
        text = WRAP.read_text()
        profile = text[text.index("<<'SBEOF'"):text.index("\nSBEOF\n")]
        self.assertIn('(deny network-outbound\n  (regex #"^/private/tmp/com\\.apple\\.launchd\\.[^/]+/Listeners$"))',
                      profile)

    def test_hidden_folders_deny_sockets(self):
        text = WRAP.read_text()
        self.assertIn('(deny network-outbound (subpath (param "HIDE_%d")))', text)
        self.assertIn('(deny network-outbound (literal (param "AGENT_SOCK")))', text)


@unittest.skipUnless(ON_MAC, "macOS with sandbox-exec only")
class DarwinLoginKeysAcceptance(unittest.TestCase):
    def setUp(self):
        # A short path: a socket path on macOS holds at most 104 bytes.
        self.tmp = Path(tempfile.mkdtemp(prefix="rlk-", dir="/private/tmp"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "h"
        (self.home / ".ssh").mkdir(parents=True, mode=0o700)
        (self.home / ".ssh" / "id_fake").write_text("FAKE-SSH-KEY\n")
        self.taskdir = self.tmp / "t"
        self.taskdir.mkdir()
        self.stub = self.tmp / "opencode"
        self.stub.write_text('#!/bin/sh\nif [ "$1" = "--version" ]; then exit 0; fi\nexec sh -c "$STUB_SCRIPT"\n')
        self.stub.chmod(self.stub.stat().st_mode | stat.S_IEXEC)

    def fake_agent(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(path))
        srv.listen(4)
        self.addCleanup(srv.close)

    def probe(self, path: Path) -> str:
        return (f"{PY} -I -c \"import socket\n"
                "s=socket.socket(socket.AF_UNIX)\n"
                "try:\n s.connect('" + str(path) + "'); print('AGENT-REACHED')\n"
                "except OSError as e:\n print('agent-unreachable', e.errno)\n\"; echo done")

    def run_wrapped(self, script: str, extra_env=None):
        env = dict(os.environ, HOME=str(self.home), OPENCODE_BIN=str(self.stub), STUB_SCRIPT=script)
        env.pop("SSH_AUTH_SOCK", None)
        env.update(extra_env or {})
        return subprocess.run([str(WRAP), str(self.taskdir), "run", "x"], env=env, capture_output=True,
                              text=True, timeout=60, stdin=subprocess.DEVNULL)

    def assert_unreachable(self, r):
        self.assertIn("done", r.stdout, r.stderr)
        self.assertIn("agent-unreachable", r.stdout)
        self.assertNotIn("AGENT-REACHED", r.stdout)

    def test_fake_agent_reachable_outside(self):
        sock = self.tmp / "a" / "s.sock"
        self.fake_agent(sock)
        r = subprocess.run(["sh", "-c", self.probe(sock)], capture_output=True, text=True, timeout=30)
        self.assertIn("AGENT-REACHED", r.stdout, r.stderr)

    def test_key_unreadable_inside(self):
        r = self.run_wrapped(f"cat '{self.home}/.ssh/id_fake'; ls -A '{self.home}/.ssh'; echo done")
        self.assertIn("done", r.stdout, r.stderr)
        self.assertNotIn("FAKE-SSH-KEY", r.stdout + r.stderr)
        self.assertNotIn("id_fake", r.stdout)

    def test_agent_in_ssh_folder_unreachable(self):
        sock = self.home / ".ssh" / "a.sock"
        self.fake_agent(sock)
        self.assert_unreachable(self.run_wrapped(self.probe(sock)))

    def test_agent_named_by_ssh_auth_sock_unreachable(self):
        sock = self.tmp / "a" / "s.sock"
        self.fake_agent(sock)
        r = self.run_wrapped(self.probe(sock) + '; echo "sock=[$SSH_AUTH_SOCK]"',
                             extra_env={"SSH_AUTH_SOCK": str(sock)})
        self.assert_unreachable(r)
        self.assertIn("sock=[]", r.stdout)

    def test_launchd_agent_unreachable_without_ssh_auth_sock(self):
        sock = Path(tempfile.mkdtemp(prefix="com.apple.launchd.rlk", dir="/private/tmp")) / "Listeners"
        self.addCleanup(shutil.rmtree, sock.parent, ignore_errors=True)
        self.fake_agent(sock)
        self.assert_unreachable(self.run_wrapped(self.probe(sock)))


    def test_launchd_agent_unreachable_through_tmp_path(self):
        sock = Path(tempfile.mkdtemp(prefix="com.apple.launchd.rlk", dir="/private/tmp")) / "Listeners"
        self.addCleanup(shutil.rmtree, sock.parent, ignore_errors=True)
        self.fake_agent(sock)
        short = Path("/tmp") / sock.parent.name / "Listeners"
        self.assert_unreachable(self.run_wrapped(self.probe(short)))

    def test_agent_unreachable_through_symlink_made_inside(self):
        sock = self.tmp / "a" / "s.sock"
        self.fake_agent(sock)
        link = self.taskdir / "l.sock"
        r = self.run_wrapped(f"ln -s '{sock}' '{link}'; " + self.probe(link), extra_env={"SSH_AUTH_SOCK": str(sock)})
        self.assert_unreachable(r)

    def test_launchd_agent_unreachable_through_symlink_made_inside(self):
        sock = Path(tempfile.mkdtemp(prefix="com.apple.launchd.rlk", dir="/private/tmp")) / "Listeners"
        self.addCleanup(shutil.rmtree, sock.parent, ignore_errors=True)
        self.fake_agent(sock)
        link = self.taskdir / "l.sock"
        self.assert_unreachable(self.run_wrapped(f"ln -s '{sock}' '{link}'; " + self.probe(link)))

    def test_one_password_agent_unreachable(self):
        sock = self.home / "Library" / "Group Containers" / "2BUA8C4S2C.com.1password" / "t" / "agent.sock"
        self.fake_agent(sock)
        self.assert_unreachable(self.run_wrapped(self.probe(sock)))

if __name__ == "__main__":
    unittest.main()
