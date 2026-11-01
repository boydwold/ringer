#!/usr/bin/env python3
"""Provider API keys reach an opencode worker inside the Linux sandbox.

OpenCode 2.2.5 keeps provider keys in opencode.db as well as auth.json. The
Linux sandbox gives every attempt a fresh data dir with only a copy of
auth.json, so a `--standalone` worker found no provider and failed with
`provider.no-route: Model unavailable: openrouter/z-ai/glm-5.2` (klipsch,
2026-11-01). engines/opencode-sandboxed.sh now writes each API key in
auth.json to a private config file in the attempt's scratch dir
(provider.<id>.options.apiKey, mode 600) and points OPENCODE_CONFIG at it:

- only the path is in the environment, so tools the worker runs never
  inherit a key, and the key is never in bwrap's argv or the wrapper's output;
- only entries with "type": "api" and a non-empty string key count, and the
  provider id is used as it is (no guessing of variable names);
- a caller's own OPENCODE_CONFIG is kept;
- a missing or broken auth.json changes nothing, and the worker still runs;
- when python3 fails, the wrapper says so on stderr and the worker still runs.

A real run on klipsch (opencode 2.2.5) showed that OpenCode gives a
<PROVIDER>_API_KEY variable and OPENCODE_CONFIG_CONTENT priority over this
file, so a key the caller set still wins.
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
STUB = '#!/bin/sh\nif [ "$1" = "--version" ]; then exit 0; fi\nexec sh -c "$STUB_SCRIPT"\n'
KEY = "sk-or-v1-TEST-KEY-0123456789"

# Records bwrap's argv (NUL-separated, appended per call), then runs the real bwrap.
BWRAP_SPY = '#!/bin/sh\nfor a in "$@"; do printf "%s\\0" "$a" >> "$SPY_LOG"; done\nexec "$REAL_BWRAP" "$@"\n'

# Prints the config the worker sees: path, mode, and the provider keys as JSON.
SHOW_CONFIG = (
    'echo "CFG=${OPENCODE_CONFIG:-}"; '
    'if [ -n "${OPENCODE_CONFIG:-}" ]; then stat -c "MODE=%a" "$OPENCODE_CONFIG"; '
    'printf "JSON="; cat "$OPENCODE_CONFIG"; echo; fi; echo "TMP=$TMPDIR"'
)


@unittest.skipUnless(LINUX_BWRAP, "Linux with bwrap only")
class ProviderKeysInSandbox(unittest.TestCase):
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
        self.auth = self.share / "auth.json"
        self.bindir = d / "bin"
        self.bindir.mkdir()
        self.stub = self.bindir / "opencode"
        self.stub.write_text(STUB)
        self.stub.chmod(self.stub.stat().st_mode | stat.S_IEXEC)
        self.spy = self.bindir / "bwrap-spy"
        self.spy.write_text(BWRAP_SPY)
        self.spy.chmod(self.spy.stat().st_mode | stat.S_IEXEC)
        self.spy_log = d / "bwrap-argv.bin"
        self.taskdir = d / "work" / "t1"
        self.taskdir.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write_auth(self, data):
        self.auth.write_text(data if isinstance(data, str) else json.dumps(data))
        self.auth.chmod(0o600)

    def run_wrapped(self, script, extra_env=None, path_first=None, expect_rc=0):
        env = {k: v for k, v in os.environ.items()
               if not k.endswith("_API_KEY") and not k.startswith("OPENCODE_CONFIG")}
        path = os.pathsep.join(filter(None, (path_first, str(self.bindir), os.environ.get("PATH", ""))))
        env.update(HOME=str(self.home), OPENCODE_BIN=str(self.stub), STUB_SCRIPT=script,
                   RINGER_SANDBOX_BWRAP=str(self.spy), REAL_BWRAP=BWRAP, SPY_LOG=str(self.spy_log), PATH=path)
        env.update(extra_env or {})
        r = subprocess.run([str(WRAP), str(self.taskdir), "run", "x"], env=env, capture_output=True,
                           text=True, timeout=60, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, expect_rc, r.stderr)
        return r

    def config_inside(self, extra_env=None, path_first=None):
        r = self.run_wrapped(SHOW_CONFIG, extra_env, path_first)
        vals = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
        providers = json.loads(vals["JSON"]).get("provider") if vals.get("JSON") else None
        return vals, providers, r

    def test_keys_written_to_private_scratch_config(self):
        self.write_auth({"openrouter": {"type": "api", "key": KEY}})
        vals, providers, _ = self.config_inside()
        self.assertEqual(providers, {"openrouter": {"options": {"apiKey": KEY}}})
        self.assertEqual(vals["MODE"], "600")
        self.assertTrue(vals["CFG"].startswith(vals["TMP"] + "/"), "the config must live in this attempt's scratch")

    def test_key_not_in_worker_environment(self):
        self.write_auth({"openrouter": {"type": "api", "key": KEY}})
        r = self.run_wrapped("env")
        self.assertNotIn(KEY, r.stdout)
        self.assertNotIn("OPENROUTER_API_KEY=", r.stdout)
        self.assertIn("OPENCODE_CONFIG=", r.stdout)

    def test_provider_ids_kept_as_they_are(self):
        self.write_auth({"fireworks-ai": {"type": "api", "key": "f-key"},
                         "zai-coding-plan": {"type": "api", "key": "z-key"}})
        _, providers, _ = self.config_inside()
        self.assertEqual(providers, {"fireworks-ai": {"options": {"apiKey": "f-key"}},
                                     "zai-coding-plan": {"options": {"apiKey": "z-key"}}})

    def test_non_api_and_bad_entries_skipped(self):
        self.write_auth({"github-copilot": {"type": "oauth", "refresh": "r", "access": "a"},
                         "openai": {"type": "api", "key": ""},
                         "groq": {"type": "api", "key": 123},
                         "deepseek": "not-a-dict",
                         "openrouter": {"type": "api", "key": KEY}})
        _, providers, _ = self.config_inside()
        self.assertEqual(providers, {"openrouter": {"options": {"apiKey": KEY}}})

    def test_odd_characters_and_bad_unicode_survive(self):
        odd = "a'b\"c $HOME `id` \\ \t = ü \U0001f642 %s\nline2"
        self.auth.write_text('{"anthropic": {"type": "api", "key": "bad\\ud800"}, '
                             '"mistral": {"type": "api", "key": ' + json.dumps(odd) + '}, '
                             '"openrouter": {"type": "api", "key": "' + KEY + '"}}')
        self.auth.chmod(0o600)
        _, providers, _ = self.config_inside()
        self.assertEqual(providers["openrouter"]["options"]["apiKey"], KEY)
        self.assertEqual(providers["mistral"]["options"]["apiKey"], odd)
        self.assertEqual(providers["anthropic"]["options"]["apiKey"], "bad\ud800")

    def test_caller_config_kept(self):
        self.write_auth({"openrouter": {"type": "api", "key": KEY}})
        mine = self.home / "mine.json"
        mine.write_text("{}")
        vals, _, r = self.config_inside({"OPENCODE_CONFIG": str(mine)})
        self.assertEqual(vals["CFG"], str(mine))
        self.assertIn("OPENCODE_CONFIG is set", r.stderr)
        self.assertNotIn(KEY, r.stdout + r.stderr)

    def test_key_never_in_bwrap_argv_or_wrapper_output(self):
        self.write_auth({"openrouter": {"type": "api", "key": KEY}})
        r = self.run_wrapped("true")
        self.assertTrue(self.spy_log.exists(), "the bwrap spy did not run")
        self.assertNotIn(KEY.encode(), self.spy_log.read_bytes())
        self.assertNotIn(KEY, r.stdout + r.stderr)

    def test_exit_status_passes_with_keys(self):
        self.write_auth({"openrouter": {"type": "api", "key": KEY}})
        self.run_wrapped("exit 7", expect_rc=7)

    def test_broken_or_missing_auth_still_runs(self):
        for content in ("{not json", "[1, 2]", "{}", '{"x": {"type": "oauth"}}', None):
            with self.subTest(content=content):
                if content is None:
                    self.auth.unlink(missing_ok=True)
                else:
                    self.write_auth(content)
                vals, providers, r = self.config_inside()
                self.assertEqual(vals["CFG"], "")
                self.assertIsNone(providers)
                self.assertEqual(r.stderr.strip(), "")

    def test_noisy_python_shim_does_not_reach_worker_output(self):
        self.write_auth({"openrouter": {"type": "api", "key": KEY}})
        fake = self.home / "noisybin"
        fake.mkdir()
        real = os.path.realpath(sys.executable)
        (fake / "python3").write_text(f'#!/bin/sh\necho SHIM-NOISE\nexec "{real}" "$@"\n')
        (fake / "python3").chmod(0o755)
        vals, providers, r = self.config_inside(path_first=str(fake))
        self.assertNotIn("SHIM-NOISE", r.stdout + r.stderr)
        self.assertEqual(providers, {"openrouter": {"options": {"apiKey": KEY}}})

    def test_scratch_and_keys_file_removed_after_run(self):
        self.write_auth({"openrouter": {"type": "api", "key": KEY}})
        scratch_root = self.home / "scratch-root"
        scratch_root.mkdir()
        for script, rc in (('test -f "$OPENCODE_CONFIG"', 0), ('test -f "$OPENCODE_CONFIG" && exit 9', 9)):
            with self.subTest(rc=rc):
                self.run_wrapped(script, {"TMPDIR": str(scratch_root)}, expect_rc=rc)
                self.assertEqual(list(scratch_root.iterdir()), [])

    def test_failing_python_is_reported_and_run_continues(self):
        self.write_auth({"openrouter": {"type": "api", "key": KEY}})
        fake = self.home / "fakebin"
        fake.mkdir()
        (fake / "python3").write_text("#!/bin/sh\nexit 1\n")
        (fake / "python3").chmod(0o755)
        vals, _, r = self.config_inside(path_first=str(fake))
        self.assertEqual(vals["CFG"], "")
        self.assertIn("could not pass provider keys", r.stderr)
        self.assertNotIn(KEY, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
