"""Regression coverage for per-attempt engine accounting."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest

import ringer


class ParsingTests(unittest.TestCase):
    def test_token_formats_and_fallback(self):
        for regex in (ringer.DEFAULT_TOKEN_REGEX, None):
            text = 'tokens used: 1,234\ntokens used\n56'
            self.assertEqual(ringer.parse_token_count(text, regex), 56)
            self.assertEqual(ringer.parse_token_count(text, regex, 'sum'), 1290)
            self.assertIsNone(ringer.parse_token_count('nothing', regex, 'sum'))

    def test_last_skips_unparseable_matches_and_sum_keeps_zero(self):
        text = 'count=12 count=0 count=unknown'
        self.assertEqual(ringer.parse_token_count(text, r'count=(\w+)'), 0)
        self.assertEqual(ringer.parse_token_count(text, r'count=(\w+)', 'sum'), 12)
        self.assertEqual(ringer.parse_token_count('count=0', r'count=(\w+)', 'sum'), 0)
        self.assertEqual(ringer.parse_token_count('12 34', r'\d+', 'sum'), 46)

    def test_cost_first_group_scientific_notation_and_invalid_values(self):
        regex = r'cost=(\S+)( units)?'
        self.assertAlmostEqual(ringer.parse_cost('cost=1e-3 units cost=bad cost=2E-3', regex), .003)
        self.assertEqual(ringer.parse_cost('cost=0', regex), 0.0)
        self.assertIsNone(ringer.parse_cost('cost=bad', regex))
        self.assertIsNone(ringer.parse_cost('cost=', r'cost=(\d+)?'))

    def test_config_errors_name_key(self):
        for key, values in {
            'token_aggregate': ['median', None, [], 1],
            'cost_regex': ['(', 'no group', '', 1, []],
        }.items():
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, f'engines.custom.{key}'):
                    ringer.load_engines({'custom': {'args_template': ['{spec}'], key: value}})

    def test_defaults(self):
        engine = ringer.load_engines(None)[ringer.DEFAULT_ENGINE_NAME]
        self.assertEqual(engine.token_aggregate, 'last')
        self.assertIsNone(engine.cost_regex)
        self.assertIsNone(ringer.WorkerResult(0, False, None).cost_usd)

    def test_database_receives_cost(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / 'runs.jsonl'
            log.write_text('\n'.join(json.dumps({
                'run_id': 'cost', 'task_key': str(i), 'worker_engine': 'custom',
                'model': 'model', 'verdict': 'PASS', 'cost_usd': cost,
            }) for i, cost in enumerate((0.006, None))) + '\n')
            db = root / 'ringer.db'
            ringer.rebuild_read_model_db(db, log)
            with contextlib.closing(ringer.connect_read_model_db(db)) as conn:
                self.assertEqual([row[0] for row in conn.execute('SELECT cost_usd FROM attempts ORDER BY task_key')], [0.006, None])


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_large_output_and_retries_exclude_headers_and_previous_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            engine = ringer.EngineConfig(
                'custom', sys.executable,
                ('-c', 'import sys; print("tokens=10 cost=0.1"); print("x" * int(sys.argv[1])); print("tokens=20 cost=0.2")', '{spec}'),
                (), (), token_regex=r'tokens=(\d+)', token_aggregate='sum', cost_regex=r'cost=([\d.]+)',
            )
            runner = ringer.RingerRunner.__new__(ringer.RingerRunner)
            runner.config = SimpleNamespace(engines={'custom': engine}, steering=SimpleNamespace(dir=None))
            runner.lock = threading.Lock()
            runner.active_processes = {}
            task = ringer.TaskSpec('task', 'spec', 'false', engine='custom')
            runtime = ringer.TaskRuntime(task, root, root / 'worker.log')
            runtime.log_path.write_text('tokens=999 cost=999\n')
            for attempt, padding in enumerate(('1000100', '0'), 1):
                with contextlib.redirect_stdout(io.StringIO()):
                    result = await runner._run_worker(runtime, padding, attempt)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.tokens, 30)
                self.assertAlmostEqual(result.cost_usd, 0.3)
                self.assertLessEqual(len(result.output_tail), 1_000_000)


if __name__ == '__main__':
    unittest.main()
