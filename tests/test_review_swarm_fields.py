#!/usr/bin/env python3
"""Priority and Confidence values in review-swarm findings.

The value may be wrapped in markdown emphasis, but it must sit on the same
line as its label (templates/review-swarm/checks/review-swarm.py).
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "review_swarm_check", ROOT / "templates" / "review-swarm" / "checks" / "review-swarm.py")
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


class FieldValues(unittest.TestCase):
    def test_priority(self):
        good = ["Priority: P1", "Priority: **P2**", "**Priority:** P0", "Priority: _P3_",
                "Priority: `P1`", "priority:\tP2 (blocking)"]
        bad = ["Priority: P4", "Priority: P10", "Priority: high", "Priority:\n\n* P0 later bullet",
               "Priority: P1x"]
        for text in good:
            with self.subTest(text=text):
                self.assertIsNotNone(CHECK.PRIORITY_RE.search(text))
        for text in bad:
            with self.subTest(text=text):
                self.assertIsNone(CHECK.PRIORITY_RE.search(text))

    def test_confidence(self):
        good = ["Confidence: high", "Confidence: **medium**", "**Confidence:** low", "Confidence: _high_"]
        bad = ["Confidence: certain", "Confidence:\n- high", "Confidence: highest"]
        for text in good:
            with self.subTest(text=text):
                self.assertIsNotNone(CHECK.CONFIDENCE_RE.search(text))
        for text in bad:
            with self.subTest(text=text):
                self.assertIsNone(CHECK.CONFIDENCE_RE.search(text))


if __name__ == "__main__":
    unittest.main()
