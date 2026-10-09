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
    paginate = load("paginate.py").paginate
except Exception as exc:
    failures.append(f"cannot import paginate.py: {exc}")
else:
    def case(items, page, size, expected):
        before = items.copy()
        result = paginate(items, page, size)
        equal(result, expected)
        equal(type(result), list)
        equal(items, before)
        if result is items:
            raise AssertionError("must return a new list")

    for length in (0, 1, 2, 5, 11):
        for size in (1, 2, 3, 7, 20):
            for page in (1, 2, 3, 5, 12, 1000000):
                items = [f"item-{i}" for i in range(length)]
                start = (page - 1) * size
                test(f"length={length} page={page} size={size}",
                     lambda: case(items, page, size, items[start:start + size]))
    for bad in (0, -1, -100, True, False, 1.0, "2", None):
        for items in ([], [1, 2, 3]):
            test(f"invalid page {bad!r}", lambda: rejects(paginate, items, bad, 2))
            test(f"invalid size {bad!r}", lambda: rejects(paginate, items, 1, bad))
sys.exit(finish())
