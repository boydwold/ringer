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


try:
    parse = load("duration.py").parse_duration
except Exception as exc:
    failures.append(f"cannot import duration.py: {exc}")
else:
    def case(text, expected):
        result = parse(text)
        equal(type(result), int)
        equal(result, expected)

    for text, expected in (("1h30m", 5400), ("45s", 45), ("2h", 7200),
                           ("90m", 5400), ("1h0m5s", 3605), ("2h5s", 7205),
                           ("0002m03s", 123), ("0s", 0), ("0h0m0s", 0)):
        test(repr(text), lambda: case(text, expected))
    for mask in range(1, 8):
        for values in ((0, 0, 0), (3, 17, 59), (12, 90, 75)):
            parts = [(str(n) + u, n * factor) for i, (n, u, factor) in
                     enumerate(zip(values, "hms", (3600, 60, 1))) if mask & (1 << i)]
            text = "".join(p[0] for p in parts)
            expected = sum(p[1] for p in parts)
            test(repr(text), lambda: case(text, expected))
    for text in ("", "h", "1", "1h2h", "1m2h", "1s2m", "1h2s3m", "1H",
                 "1.5h", "-1s", "+2m", " 1s", "1s ", "1 s", "1s\n", "1sX",
                 "１s", "١m", None, 15, True, b"1s"):
        test(f"invalid {text!r}", lambda: rejects(parse, text))
sys.exit(finish())
