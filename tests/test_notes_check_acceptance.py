#!/usr/bin/env python3
"""Acceptance tests for `ringer.py notes check` and the evidence citation
(openspec change trusted-multi-model-tracking, spec model-notes, design D7;
tasks 6.1-6.2).

Contract under test:
  ringer.py notes check --base <git-ref> [--log PATH] [--notes-file PATH]
    --notes-file defaults to docs/MODEL-NOTES.md in the ringer checkout; the git
    repo is the one containing the notes file.
    Exit 0 when every new/edited dated entry is valid; prints "<n> entries checked".
    Exit 1 listing each failing entry with a reason; exit 2 on a bad ref or no git.
  Citation, one or more per entry:
    [evidence: run=<run_id> task=<task_key> model=<slug> attempt=<n> verdict=<PASS|FAIL|TIMEOUT> type=<task_type> family=<work|audition>]
  The cited model must belong to the entry's heading: the heading contains, as a
  whole token, the slug (with or without "openrouter/"), its registry display
  name, or its identity key.
  strip_inline_markdown removes "[evidence: ...]" from displayed notes.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ringer  # noqa: E402

BASE = """# Model notes

Intro text.

## glm-5.2 via opencode (`openrouter/z-ai/glm-5.2`)

- 2026-08-01 — code-review, good blast-area work on a big repo.

## kimi-k2.7 via opencode (`openrouter/moonshotai/kimi-k2.7-code`)

- 2026-08-02 — lost lanes to provider errors.

## glm-5.2 via opencode (`openrouter/z-ai/glm-5.2`)

- 2026-08-03 — duplicate heading section, upstream style.
"""

RUN = "audition-20261012T030001Z-p42"
GLM = "openrouter/z-ai/glm-5.2"


def cite(run=RUN, task="fix-off-by-one--z-ai-glm-5-2", model=GLM, attempt=1, verdict="PASS", type_="code-fix", family="audition"):
    return f"[evidence: run={run} task={task} model={model} attempt={attempt} verdict={verdict} type={type_} family={family}]"


def log_row(run=RUN, task="fix-off-by-one--z-ai-glm-5-2", model=GLM, ma=1, verdict="PASS", cls=None, family="audition"):
    return {"run_id": run, "task_key": task, "model": model, "worker_engine": "opencode", "model_attempt": ma,
            "verdict": verdict, "failure_class": cls, "task_type": "code-fix", "run_family": family,
            "logged_at": "2026-10-12T03:05:00+00:00", "retry": False, "notes": ""}


class NotesCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        (self.repo / "docs").mkdir(parents=True)
        self.notes = self.repo / "docs" / "MODEL-NOTES.md"
        self.notes.write_text(BASE)
        self.git("init", "-q")
        self.git("-c", "user.email=t@t", "-c", "user.name=t", "add", ".")
        self.git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "base")
        self.log = Path(self.tmp.name) / "runs.jsonl"
        self.write_log([log_row(), log_row(run="r-infra", task="t2", verdict="FAIL", cls="provider_policy", ma=None)])

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True)

    def write_log(self, rows):
        self.log.write_text("".join(json.dumps(r) + "\n" for r in rows))

    def add_entry(self, text, heading_index=0):
        lines = self.notes.read_text().splitlines()
        heads = [i for i, l in enumerate(lines) if l.startswith("## ")]
        insert_at = heads[heading_index] + 2
        lines.insert(insert_at, text)
        self.notes.write_text("\n".join(lines) + "\n")

    def check(self, *extra, base="HEAD", log=True):
        args = [sys.executable, "-B", str(ROOT / "ringer.py"), "--no-self-update", "notes", "check", "--base", base,
                "--notes-file", str(self.notes)]
        if log:
            args += ["--log", str(self.log)]
        env = dict(os.environ, RINGER_HOME=str(Path(self.tmp.name) / "home"))
        return subprocess.run(args + list(extra), capture_output=True, text=True, env=env, timeout=60)

    def test_unchanged_file_passes_with_zero_entries(self):
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("0 entries checked", r.stdout)

    def test_valid_entry_passes(self):
        self.add_entry(f"- 2026-10-12 — code-fix audition, clean first try. {cite()}")
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("1 entries checked", r.stdout)

    def test_valid_entry_without_log_checks_format_only(self):
        self.add_entry(f"- 2026-10-12 — code-fix audition. {cite(run='not-in-any-log')}")
        r = self.check(log=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_missing_citation(self):
        self.add_entry("- 2026-10-12 — great at everything, trust me.")
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing evidence", r.stdout)
        self.assertIn("great at everything", r.stdout)

    def test_run_not_found(self):
        self.add_entry(f"- 2026-10-12 — claims a run. {cite(run='audition-nope-p1')}")
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("run not found", r.stdout)

    def test_verdict_mismatch(self):
        self.add_entry(f"- 2026-10-12 — says it failed. {cite(verdict='FAIL')}")
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("verdict", r.stdout)

    def test_infrastructure_citation_rejected(self):
        self.add_entry(f"- 2026-10-12 — unreliable. {cite(run='r-infra', task='t2', verdict='FAIL', attempt=1, family='audition')}")
        self.write_log([log_row(), log_row(run="r-infra", task="t2", verdict="FAIL", cls="provider_policy", ma=1)])
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("not model evidence", r.stdout)

    def test_wrong_model_for_heading(self):
        self.add_entry(f"- 2026-10-12 — kimi did this. {cite()}", heading_index=1)
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not match heading", r.stdout)

    def test_edited_upstream_entry_counts_as_new(self):
        text = self.notes.read_text().replace("good blast-area work on a big repo", "excellent blast-area work on a big repo")
        self.notes.write_text(text)
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing evidence", r.stdout)

    def test_new_entry_under_duplicate_heading_detected(self):
        self.add_entry("- 2026-10-12 — under the second glm section, no evidence.", heading_index=2)
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("second glm section", r.stdout)

    def test_bad_base(self):
        r = self.check(base="no-such-ref-xyz")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not found", (r.stdout + r.stderr).lower())

    def test_not_a_git_checkout(self):
        outside = Path(self.tmp.name) / "loose" / "MODEL-NOTES.md"
        outside.parent.mkdir()
        outside.write_text(BASE)
        args = [sys.executable, "-B", str(ROOT / "ringer.py"), "--no-self-update", "notes", "check", "--base", "HEAD",
                "--notes-file", str(outside)]
        r = subprocess.run(args, capture_output=True, text=True, timeout=60,
                           env=dict(os.environ, GIT_CEILING_DIRECTORIES=self.tmp.name))
        self.assertEqual(r.returncode, 2)
        self.assertIn("git", (r.stdout + r.stderr).lower())


class DisplayStripsCitation(unittest.TestCase):
    def test_citation_removed_from_display(self):
        shown = ringer.strip_inline_markdown(f"code-fix audition, clean first try. {cite()}")
        self.assertNotIn("evidence:", shown)
        self.assertIn("clean first try", shown)


if __name__ == "__main__":
    unittest.main()
