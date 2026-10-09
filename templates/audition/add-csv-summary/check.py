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
    summarize = load("summary.py").summarize
except Exception as exc:
    failures.append(f"cannot import summary.py: {exc}")
else:
    def expected(count, numeric=None, other=None):
        return {"row_count": count, "numeric": numeric or {}, "non_numeric": other or []}

    def stats(low, high, mean):
        return {"min": low, "max": high, "mean": mean}

    cases = [
        ("", expected(0)), ("\n\r\n", expected(0)),
        ("label,value\n", expected(0, other=["label", "value"])),
        ("name,n\na,2\nb,4\n", expected(2, {"n": stats(2, 4, 3)}, ["name"])),
        ('label,x,y\n"red, blue",-2.345,1e2\n"two\nlines",4.567, 20 \n',
         expected(2, {"x": stats(-2.35, 4.57, 1.11), "y": stats(20, 100, 60)}, ["label"])),
        ("a,b,c,d\n1,NaN,inf,3\n,2,4,oops\n", expected(2, other=["a", "b", "c", "d"])),
        ("z,a\n\n3,7\r\n5,9\n", expected(2, {"z": stats(3, 5, 4), "a": stats(7, 9, 8)})),
        (' col ,blank,text\n 02 ," ","say ""hi"""\n',
         expected(1, {" col ": stats(2, 2, 2)}, ["blank", "text"])),
        ("n\n0\n0\n1\n", expected(3, {"n": stats(0, 1, 0.33)})),
        ("a,b,c\n-Infinity,+inf,nan\n", expected(1, other=["a", "b", "c"])),
        ("a,b\n,\n", expected(1, other=["a", "b"])),
    ]
    def case(text, want):
        got = summarize(text)
        equal(got, want)
        equal(type(got), dict)
        equal(type(got["row_count"]), int)
        equal(type(got["numeric"]), dict)
        equal(type(got["non_numeric"]), list)
        for columns in got["numeric"].values():
            equal(type(columns), dict)
            for value in columns.values():
                if type(value) not in (int, float):
                    raise AssertionError("statistics must be numbers, not booleans")
    for index, (text, want) in enumerate(cases + cases):
        test(f"CSV case {index + 1}", lambda: case(text, want))
sys.exit(finish())
