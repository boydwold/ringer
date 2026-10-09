#!/usr/bin/env python3
"""Private location-based review grader; all answer coordinates stay here."""
import os
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
# Inclusive accepted source ranges, including one line of citation tolerance.
DEFECTS = [('shared default history', 'inventory.py', 3, 5), ('overselling stock', 'inventory.py', 11, 13), ('hidden save failure', 'storage.py', 7, 10)]
DECOYS = [('inventory.py', 20, 21), ('storage.py', 15, 17)]
SOURCE_LENGTHS = {'inventory.py': 22, 'storage.py': 17}
CITATION = re.compile(r"(?P<path>[A-Za-z0-9_./\\-]+\.py):(?P<start>[0-9]+)(?:-(?P<end>[0-9]+))?")


def main():
    failures = []
    try:
        report = (Path(os.getcwd()) / "report.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        print("FAIL: cannot read report.md: " + " ".join(str(exc).splitlines()))
        return 1
    if not report.strip():
        failures.append("report.md is empty")
    cited = set()
    for match in CITATION.finditer(report):
        path = match["path"]
        if path.startswith("./"):
            path = path[2:]
        start = int(match["start"])
        end = int(match["end"] or start)
        if path not in SOURCE_LENGTHS or not 1 <= start <= end <= SOURCE_LENGTHS.get(path, 0):
            failures.append(f"invalid source citation: {match[0]}")
            continue
        cited.update((path, line) for line in range(start, end + 1))
        # Require prose on the citation's own line, without guessing its wording.
        row = report[report.rfind("\n", 0, match.start()) + 1:report.find("\n", match.end()) if "\n" in report[match.end():] else len(report)]
        explanation = CITATION.sub("", row)
        if not re.search(r"[A-Za-z]{2,}", explanation):
            failures.append(f"citation lacks a one-line explanation: {match[0]}")
    if not cited:
        failures.append("no source citations found")
    if len(cited) > 8:
        failures.append("more than 8 distinct cited lines (flagging everything)")
    for label, path, low, high in DEFECTS:
        if not any((path, line) in cited for line in range(low, high + 1)):
            failures.append(f"missing defect: {label}")
    for path, low, high in DECOYS:
        if any((path, line) in cited for line in range(low, high + 1)):
            failures.append(f"incorrect finding on correct code: {path}:{low}-{high}")
    for failure in failures:
        print("FAIL: " + failure)
    if not failures:
        print("PASS: all defects located without decoys or citation spam")
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(main())
