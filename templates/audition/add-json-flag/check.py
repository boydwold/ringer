#!/usr/bin/env python3
"""Private, offline behavioural check; run with the task directory as cwd."""
import importlib.util
import os
import sys
import uuid
from pathlib import Path

sys.dont_write_bytecode = True
failures = []


def test(label, action):
    try:
        action()
    except Exception as exc:
        failures.append(f"{label}: {type(exc).__name__}: {exc}")


def equal(actual, expected):
    if actual != expected:
        raise AssertionError(f"expected {expected!r}, got {actual!r}")


def rejects(function, *args):
    try:
        function(*args)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def load(filename):
    name = "_audition_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, Path(os.getcwd()) / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def finish():
    for failure in failures:
        print("FAIL: " + " ".join(failure.splitlines()))
    if not failures:
        print("PASS: all behavioural cases passed")
    return int(bool(failures))


import contextlib
import io
import json
import subprocess


def import_case():
    output, errors = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        try:
            load("wordcount.py")
        except SystemExit as exc:
            raise AssertionError(f"argument parsing on import: {exc}")
    equal(output.getvalue(), "")
    equal(errors.getvalue(), "")


def run(args):
    return subprocess.run(["python3", "-I", "wordcount.py", *args],
                          cwd=os.getcwd(), capture_output=True, text=True,
                          encoding="utf-8", timeout=5)


def case(text, mode):
    counts = {"lines": len(text.splitlines()), "words": len(text.split()),
              "characters": len(text)}
    args = [text] if mode == "text" else (["--json", text] if mode == "before" else [text, "--json"])
    result = run(args)
    equal(result.returncode, 0)
    equal(result.stderr, "")
    if mode == "text":
        equal(result.stdout, "".join(f"{key}: {value}\n" for key, value in counts.items()))
    else:
        def unique(pairs):
            obj = dict(pairs)
            if len(obj) != len(pairs):
                raise AssertionError("duplicate JSON keys")
            return obj
        obj = json.loads(result.stdout, object_pairs_hook=unique)
        equal(obj, counts)
        equal(type(obj), dict)
        for value in obj.values():
            equal(type(value), int)


test("quiet import", import_case)
for text in ("", "hi there", "a\nb\n", "\n", "  \t\n ", "café 🐍\t世界",
             "one\r\ntwo\rthree", "a\v b\f c", "a\u2028b\u00a0c"):
    for mode in ("text", "before", "after"):
        test(f"{mode} {text!r}", lambda: case(text, mode))

def cli_edges():
    equal(run(["--help"]).returncode, 0)
    for args in ([], ["--json"], ["a", "b"], ["--unknown", "a"]):
        if run(args).returncode == 0:
            raise AssertionError(f"invalid arguments accepted: {args!r}")
    result = run(["--json", "--", "-x"])
    equal(result.returncode, 0)
    equal(result.stderr, "")
    equal(json.loads(result.stdout), {"lines": 1, "words": 1, "characters": 2})

test("argparse behaviour", cli_edges)
sys.exit(finish())
