#!/usr/bin/env python3
"""The macOS sandbox denies the Keychain (Boyd's decision, 2026-11-03).

On macOS the CodeRabbit CLI keeps its sign-in tokens in the login Keychain.
The opencode sandbox shares the network, so a worker that can read the
Keychain could run a CodeRabbit review in Boyd's name. The Seatbelt profile
in engines/opencode-sandboxed.sh denies the Keychain services.

The profile-text test runs everywhere. The acceptance test runs only on macOS:
it makes a temporary keychain with a fake secret, reads it outside the
sandbox, and expects the same read to fail inside it.
"""
from __future__ import annotations

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
SECURITY = "/usr/bin/security"
ON_MAC = sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").exists() and Path(SECURITY).exists()


def profile_text() -> str:
    text = WRAP.read_text()
    return text[text.index("<<'SBEOF'"):text.index("\nSBEOF\n")]


class DarwinProfileKeychain(unittest.TestCase):
    def test_profile_denies_keychain_services(self):
        profile = profile_text()
        start = profile.index('(global-name "com.apple.SecurityServer")')
        block = profile[profile.rindex("(deny mach-lookup", 0, start):profile.index("))", start) + 2]
        for name in ("com.apple.SecurityServer", "com.apple.securityd.xpc", "com.apple.securityd"):
            self.assertIn(f'(global-name "{name}")', block)


@unittest.skipUnless(ON_MAC, "macOS with sandbox-exec only")
class DarwinKeychainAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ringer-kc-test-"))
        self.kc = self.tmp / "test.keychain-db"
        self.taskdir = self.tmp / "task"
        self.taskdir.mkdir()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        subprocess.run([SECURITY, "create-keychain", "-p", "ringer-test", str(self.kc)], check=True)
        # Cleanups run last-in first-out: the keychain goes before its folder.
        self.addCleanup(subprocess.run, [SECURITY, "delete-keychain", str(self.kc)], check=False)
        subprocess.run([SECURITY, "unlock-keychain", "-p", "ringer-test", str(self.kc)], check=True)
        subprocess.run([SECURITY, "add-generic-password", "-s", "ringer-keychain-test", "-a", "fake",
                        "-w", "FAKE-KC-SECRET", "-A", str(self.kc)], check=True)
        self.stub = self.tmp / "opencode"
        self.stub.write_text('#!/bin/sh\nif [ "$1" = "--version" ]; then exit 0; fi\nexec sh -c "$STUB_SCRIPT"\n')
        self.stub.chmod(self.stub.stat().st_mode | stat.S_IEXEC)

    def read_cmd(self) -> str:
        return f"{SECURITY} find-generic-password -s ringer-keychain-test -w '{self.kc}'; echo done"

    def test_secret_readable_outside(self):
        r = subprocess.run(["sh", "-c", self.read_cmd()], capture_output=True, text=True, timeout=30)
        self.assertIn("FAKE-KC-SECRET", r.stdout, r.stderr)

    def test_secret_unreadable_inside(self):
        env = dict(os.environ, OPENCODE_BIN=str(self.stub), STUB_SCRIPT=self.read_cmd())
        r = subprocess.run([str(WRAP), str(self.taskdir), "run", "x"], env=env, capture_output=True,
                           text=True, timeout=60, stdin=subprocess.DEVNULL)
        self.assertIn("done", r.stdout, r.stderr)
        self.assertNotIn("FAKE-KC-SECRET", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
