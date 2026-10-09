#!/usr/bin/env python3
"""Acceptance tests for the audition set (openspec change
trusted-multi-model-tracking, spec model-auditions "Fixed audition set" and
"Review tasks plant known defects"; task 7.1).

Layout contract, one directory per task under templates/audition/<name>/:
  task.toml   key (= directory name), task_type (code-fix | code-feature |
              code-review), expect_files (list, relative), token_estimate (int),
              title (str)
  spec.md     the worker's brief: self-contained, names every deliverable
  fixture/    the files the worker starts with (copied into its task dir)
  reference/  a known-good result: for code tasks, files that overlay the
              fixture at the same relative paths; for review tasks, the
              report named in expect_files
  check.py    stdlib only, run as `python3 -I <path>/check.py` with cwd = the
              task dir; exit 0 = pass, nonzero = fail with a reason on stdout;
              must not modify fixture files it reads, must not use the network
"""
from __future__ import annotations

import ast
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SET = ROOT / "templates" / "audition"
CHECK_SANDBOX = ROOT / "engines" / "check-sandboxed.sh"
TYPES = ("code-fix", "code-feature", "code-review")


def tasks() -> list[Path]:
    return sorted(p for p in SET.iterdir() if p.is_dir() and not p.name.startswith((".", "_")))


def meta(task: Path) -> dict:
    return tomllib.loads((task / "task.toml").read_text())


def stage(task: Path, overlay: Path | None, extra: dict[str, str] | None = None) -> Path:
    d = Path(tempfile.mkdtemp(prefix="audition-acc-"))
    shutil.copytree(task / "fixture", d, dirs_exist_ok=True)
    if overlay is not None:
        shutil.copytree(overlay, d, dirs_exist_ok=True)
    for rel, text in (extra or {}).items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(text)
    return d


def run_check(task: Path, taskdir: Path, sandboxed: bool = False) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-I", str(task / "check.py")]
    if sandboxed:
        cmd = [str(CHECK_SANDBOX), str(taskdir), "60"] + cmd
    return subprocess.run(cmd, cwd=taskdir, capture_output=True, text=True, timeout=120)


def snapshot(d: Path) -> dict[str, bytes]:
    return {str(p.relative_to(d)): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}


class AuditionSetLayout(unittest.TestCase):
    def test_coverage(self):
        counts = {t: 0 for t in TYPES}
        for task in tasks():
            counts[meta(task)["task_type"]] += 1
        for t in TYPES:
            self.assertGreaterEqual(counts[t], 2, f"need at least two {t} tasks")

    def test_files_and_fields(self):
        for task in tasks():
            with self.subTest(task=task.name):
                for part in ("task.toml", "spec.md", "check.py"):
                    self.assertTrue((task / part).is_file(), part)
                for part in ("fixture", "reference"):
                    self.assertTrue((task / part).is_dir(), part)
                m = meta(task)
                self.assertEqual(m["key"], task.name)
                self.assertIn(m["task_type"], TYPES)
                self.assertIsInstance(m["token_estimate"], int)
                self.assertTrue(m["title"].strip())
                self.assertTrue(m["expect_files"])
                spec = (task / "spec.md").read_text()
                self.assertGreater(len(spec), 200)
                for rel in m["expect_files"]:
                    self.assertFalse(Path(rel).is_absolute())
                    self.assertIn(rel, spec, "spec must name every deliverable")

    def test_checks_are_stdlib_only(self):
        stdlib = set(sys.stdlib_module_names)
        for task in tasks():
            with self.subTest(task=task.name):
                tree = ast.parse((task / "check.py").read_text())
                for node in ast.walk(tree):
                    names = []
                    if isinstance(node, ast.Import):
                        names = [a.name.split(".")[0] for a in node.names]
                    elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                        names = [node.module.split(".")[0]]
                    for n in names:
                        self.assertIn(n, stdlib, f"non-stdlib import {n}")
                        self.assertNotIn(n, {"socket", "urllib", "http", "ssl", "ftplib", "smtplib"}, f"network module {n}")


class AuditionChecksBehave(unittest.TestCase):
    def test_reference_passes_twice_and_in_check_sandbox(self):
        for task in tasks():
            with self.subTest(task=task.name):
                d = stage(task, task / "reference")
                r1, r2 = run_check(task, d), run_check(task, d)
                self.assertEqual(r1.returncode, 0, r1.stdout + r1.stderr)
                self.assertEqual(r2.returncode, 0, "same deliverable, same verdict")
                if shutil.which("bwrap") and sys.platform.startswith("linux"):
                    r3 = run_check(task, d, sandboxed=True)
                    self.assertEqual(r3.returncode, 0, "reference must pass with no network: " + r3.stdout + r3.stderr)
                shutil.rmtree(d)

    def test_untouched_fixture_fails_for_code_tasks(self):
        for task in tasks():
            if meta(task)["task_type"] == "code-review":
                continue
            with self.subTest(task=task.name):
                d = stage(task, None)
                r1, r2 = run_check(task, d), run_check(task, d)
                self.assertNotEqual(r1.returncode, 0, "unchanged fixture must fail")
                self.assertNotEqual(r2.returncode, 0)
                self.assertTrue(r1.stdout.strip(), "a failing check must say why")
                shutil.rmtree(d)

    def test_check_does_not_modify_fixture(self):
        for task in tasks():
            with self.subTest(task=task.name):
                d = stage(task, task / "reference")
                before = snapshot(d)
                run_check(task, d)
                after = snapshot(d)
                for rel, data in before.items():
                    self.assertEqual(after.get(rel), data, f"check modified {rel}")
                shutil.rmtree(d)


class ReviewTasksResistGaming(unittest.TestCase):
    def review_tasks(self):
        return [t for t in tasks() if meta(t)["task_type"] == "code-review"]

    def report_name(self, task):
        return meta(task)["expect_files"][0]

    def test_generic_report_fails(self):
        for task in self.review_tasks():
            with self.subTest(task=task.name):
                d = stage(task, None, {self.report_name(task): "# Review\n\nThe code looks fine. No issues found.\n"})
                self.assertNotEqual(run_check(task, d).returncode, 0)
                shutil.rmtree(d)

    def test_flag_everything_report_fails(self):
        for task in self.review_tasks():
            with self.subTest(task=task.name):
                lines = []
                for f in sorted((task / "fixture").rglob("*")):
                    if f.is_file():
                        rel = f.relative_to(task / "fixture")
                        n = len(f.read_text(errors="replace").splitlines())
                        lines += [f"- {rel}:{i} possible bug here" for i in range(1, n + 1)]
                d = stage(task, None, {self.report_name(task): "# Review\n\n" + "\n".join(lines) + "\n"})
                self.assertNotEqual(run_check(task, d).returncode, 0, "citing every line must fail")
                shutil.rmtree(d)

    def test_missing_report_fails(self):
        for task in self.review_tasks():
            with self.subTest(task=task.name):
                d = stage(task, None)
                self.assertNotEqual(run_check(task, d).returncode, 0)
                shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
