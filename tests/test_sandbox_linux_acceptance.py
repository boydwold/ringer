#!/usr/bin/env python3
"""Acceptance tests for the Linux worker sandbox and the check sandbox
(openspec change trusted-multi-model-tracking, spec worker-sandbox, design D2/D6).

Contract under test:
  engines/opencode-sandboxed.sh <taskdir> [--no-sandbox] <opencode args...>
      env OPENCODE_BIN           opencode binary to run (default: command -v opencode)
      env RINGER_SANDBOX_HIDE    colon-separated paths that read as empty inside
      env RINGER_SANDBOX_BWRAP   bwrap binary (default: bwrap); used to simulate it missing
  engines/check-sandboxed.sh <taskdir> <timeout_s> <command...>
      no network, writes only to <taskdir>, exit status passed through, timeout enforced

All tests run in a throwaway HOME with a stub in place of opencode.
"""
from __future__ import annotations

import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRAP = ROOT / "engines" / "opencode-sandboxed.sh"
CHECKW = ROOT / "engines" / "check-sandboxed.sh"

# Real interpreter path: a mise/pyenv shim on PATH can stall inside the
# read-only sandbox (it tries to write its own state), which made these probes flaky.
PY = os.path.realpath(sys.executable)
LINUX_BWRAP = sys.platform.startswith("linux") and shutil.which("bwrap") is not None

STUB = """#!/bin/sh
# Stand-in for opencode: run the script passed in STUB_SCRIPT.
exec sh -c "$STUB_SCRIPT"
"""


def tcp_server() -> tuple[int, threading.Thread]:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    srv.settimeout(60)

    def serve():
        try:
            conn, _ = srv.accept()
            conn.sendall(b"hello\n")
            conn.close()
        except OSError:
            pass
        finally:
            srv.close()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    return srv.getsockname()[1], t


@unittest.skipUnless(LINUX_BWRAP, "Linux with bwrap only")
class OpencodeWrapperLinuxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.home = base / "home"
        (self.home / ".config" / "opencode").mkdir(parents=True)
        (self.home / ".config" / "opencode" / "opencode.json").write_text("{}\n")
        self.taskdir = base / "work" / "t1"
        self.taskdir.mkdir(parents=True)
        self.stub = base / "bin" / "opencode"
        self.stub.parent.mkdir()
        self.stub.write_text(STUB)
        self.stub.chmod(self.stub.stat().st_mode | stat.S_IEXEC)
        self.secret = base / "secret"
        self.secret.mkdir()
        (self.secret / "answer.txt").write_text("THE-ANSWER\n")

    def tearDown(self):
        self.tmp.cleanup()

    def run_wrapped(self, script: str, *, extra_env=None, no_sandbox=False, timeout=60):
        env = dict(os.environ)
        env.update({"HOME": str(self.home), "OPENCODE_BIN": str(self.stub), "STUB_SCRIPT": script,
                    "PATH": str(self.stub.parent) + os.pathsep + env.get("PATH", "")})
        env.update(extra_env or {})
        args = [str(WRAP), str(self.taskdir)] + (["--no-sandbox"] if no_sandbox else []) + ["run", "x"]
        return subprocess.run(args, env=env, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)

    def test_write_inside_taskdir(self):
        r = self.run_wrapped(f"echo ok > '{self.taskdir}/report.md'")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.taskdir / "report.md").read_text().strip(), "ok")

    def test_write_outside_fails(self):
        target = self.home / "escaped.txt"
        r = self.run_wrapped(f"echo x > '{target}'; echo rc=$?")
        self.assertIn("rc=", r.stdout)
        self.assertNotIn("rc=0", r.stdout)
        self.assertFalse(target.exists())

    def test_engine_config_read_only(self):
        cfg = self.home / ".config" / "opencode" / "opencode.json"
        r = self.run_wrapped(f"cat '{cfg}' && echo changed > '{cfg}'; echo rc=$?")
        self.assertIn("{}", r.stdout)
        self.assertNotIn("rc=0", r.stdout)
        self.assertEqual(cfg.read_text(), "{}\n")

    def test_opencode_state_dirs_writable(self):
        share = self.home / ".local" / "share" / "opencode"
        state = self.home / ".local" / "state" / "opencode"
        r = self.run_wrapped(f"echo a > '{share}/s.txt' && echo b > '{state}/t.txt' && echo both-ok")
        self.assertIn("both-ok", r.stdout, r.stderr)

    def test_hidden_path_reads_empty(self):
        r = self.run_wrapped(f"cat '{self.secret}/answer.txt'; ls -A '{self.secret}'; echo done",
                             extra_env={"RINGER_SANDBOX_HIDE": str(self.secret)})
        self.assertIn("done", r.stdout)
        self.assertNotIn("THE-ANSWER", r.stdout + r.stderr)
        self.assertNotIn("answer.txt", r.stdout)

    def test_session_bus_unreachable(self):
        uid = os.getuid()
        bus = Path(f"/run/user/{uid}/bus")
        if not bus.exists():
            self.skipTest("no user session bus on this host")
        probe = (
            f"{PY} -c \"import socket,sys\n"
            "s=socket.socket(socket.AF_UNIX)\n"
            "try:\n s.connect('" + str(bus) + "'); print('BUS-REACHED')\n"
            "except OSError as e: print('bus-blocked', e)\""
        )
        r = self.run_wrapped(probe)
        self.assertIn("bus-blocked", r.stdout, r.stdout + r.stderr)
        self.assertNotIn("BUS-REACHED", r.stdout)

    def test_session_env_scrubbed(self):
        r = self.run_wrapped("env", extra_env={"DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1/bus",
                                               "SSH_AUTH_SOCK": "/tmp/agent.sock", "HERDR_SOCKET": "/tmp/h.sock"})
        for var in ("DBUS_SESSION_BUS_ADDRESS=", "SSH_AUTH_SOCK=", "HERDR_SOCKET="):
            self.assertNotIn(var, r.stdout)

    def test_host_tmp_sockets_invisible(self):
        sock_path = Path(tempfile.gettempdir()) / f"ringer-acc-{os.getpid()}.sock"
        s = socket.socket(socket.AF_UNIX)
        s.bind(str(sock_path))
        try:
            r = self.run_wrapped(f"test -e '{sock_path}' && echo VISIBLE || echo hidden")
            self.assertIn("hidden", r.stdout, r.stderr)
        finally:
            s.close()
            sock_path.unlink(missing_ok=True)

    def test_local_tcp_and_dns(self):
        port, t = tcp_server()
        probe = (
            f"{PY} -c \"import socket\n"
            f"s=socket.create_connection(('127.0.0.1',{port}),5); print(s.recv(16).decode().strip())\n"
            "print('dns', bool(socket.getaddrinfo('localhost', 80)))\""
        )
        r = self.run_wrapped(probe)
        t.join(5)
        detail = f"rc={r.returncode}\nstdout={r.stdout!r}\nstderr={r.stderr!r}"
        self.assertIn("hello", r.stdout, detail)
        self.assertIn("dns True", r.stdout, detail)

    def test_no_child_outlives_wrapper(self):
        pidfile = self.taskdir / "child.pid"
        r = self.run_wrapped(f"setsid sleep 300 & echo $! > '{pidfile}'; sleep 0.5; exit 0")
        self.assertEqual(r.returncode, 0, r.stderr)
        time.sleep(1)
        out = subprocess.run(["pgrep", "-f", "sleep 300"], capture_output=True, text=True).stdout.split()
        # The pid inside the sandbox is namespaced; check no host 'sleep 300' started by this test survives.
        survivors = []
        for pid in out:
            try:
                env = Path(f"/proc/{pid}/environ").read_bytes()
            except OSError:
                continue
            if str(self.home).encode() in env:
                survivors.append(pid)
        self.assertEqual(survivors, [], "a process started inside the sandbox outlived it")

    def test_bwrap_missing_fails_closed(self):
        marker = self.taskdir / "ran.txt"
        r = self.run_wrapped(f"touch '{marker}'", extra_env={"RINGER_SANDBOX_BWRAP": "/nonexistent/bwrap"})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("[ringer-sandbox]", r.stdout + r.stderr)
        self.assertIn("bwrap", r.stdout + r.stderr)
        self.assertFalse(marker.exists(), "worker ran without a sandbox")

    def test_no_sandbox_passthrough(self):
        r = self.run_wrapped(f"echo free > '{self.home}/free.txt'", no_sandbox=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.home / "free.txt").exists())

    def test_exit_status_propagates(self):
        r = self.run_wrapped("exit 7")
        self.assertEqual(r.returncode, 7)


@unittest.skipUnless(LINUX_BWRAP, "Linux with bwrap only")
class CheckSandboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.taskdir = Path(self.tmp.name) / "t1"
        self.taskdir.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_check(self, *cmd, timeout_s=20):
        return subprocess.run([str(CHECKW), str(self.taskdir), str(timeout_s), *cmd],
                              capture_output=True, text=True, timeout=timeout_s + 30, stdin=subprocess.DEVNULL)

    def test_exit_status_passed_through(self):
        self.assertEqual(self.run_check("sh", "-c", "exit 3").returncode, 3)
        self.assertEqual(self.run_check("sh", "-c", "exit 0").returncode, 0)

    def test_no_network(self):
        port, t = tcp_server()
        r = self.run_check("python3", "-I", "-c",
                           f"import socket\ntry:\n socket.create_connection(('127.0.0.1',{port}),3); print('NET-OK')\nexcept OSError: print('net-blocked')")
        self.assertIn("net-blocked", r.stdout, r.stdout + r.stderr)

    def test_writes_limited_to_taskdir(self):
        outside = Path(self.tmp.name) / "outside.txt"
        r = self.run_check("sh", "-c", f"echo in > '{self.taskdir}/in.txt'; echo out > '{outside}'; echo rc=$?")
        self.assertTrue((self.taskdir / "in.txt").exists())
        self.assertFalse(outside.exists())
        self.assertNotIn("rc=0", r.stdout)

    def test_timeout_enforced(self):
        start = time.monotonic()
        r = self.run_check("sleep", "30", timeout_s=2)
        self.assertNotEqual(r.returncode, 0)
        self.assertLess(time.monotonic() - start, 15)
        self.assertIn("timed out", (r.stdout + r.stderr).lower())

    def test_bwrap_missing_fails_closed(self):
        env = dict(os.environ, RINGER_SANDBOX_BWRAP="/nonexistent/bwrap")
        r = subprocess.run([str(CHECKW), str(self.taskdir), "10", "sh", "-c", f"touch '{self.taskdir}/ran'"],
                           capture_output=True, text=True, env=env, timeout=30)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("[ringer-sandbox]", r.stdout + r.stderr)
        self.assertFalse((self.taskdir / "ran").exists())


if __name__ == "__main__":
    unittest.main()
