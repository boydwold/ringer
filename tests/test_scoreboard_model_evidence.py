"""Regression coverage for model evidence, family isolation, and DB parity."""
import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ringer


def attempt(index=1, **changes):
    row = {
        "run_id": "run", "task_key": "task", "worker_engine": "opencode",
        "model": "openrouter/acme/worker", "task_type": "code-fix",
        "verdict": "PASS", "failure_class": None, "model_attempt": 1,
        "run_family": "work", "failure_evidence": "", "retry": False,
        "logged_at": f"2026-10-08T00:00:{index:02d}+00:00",
        "worker_tokens": 100, "duration_ms": 200,
    }
    row.update(changes)
    return row


AGGREGATORS = (ringer.aggregate_model_log_rows, ringer.aggregate_model_scoreboard_rows)


class EvidenceTests(unittest.TestCase):
    def test_counted_classes_and_pass_override(self):
        for cls in ringer.FAILURE_CLASSES | {None}:
            with self.subTest(cls=cls):
                self.assertEqual(ringer.is_model_counted(attempt(verdict="FAIL", failure_class=cls)), cls in (None, "model"))
                self.assertTrue(ringer.is_model_counted(attempt(failure_class=cls)))
        self.assertTrue(ringer.is_model_counted({"verdict": "FAIL"}))

    def test_infra_does_not_supply_identity_effort_or_final_statistics(self):
        rows = [attempt(1, verdict="FAIL", failure_class="provider_error", model_attempt=None,
                        model="wrong-start", worker_engine="codex", task_type="wrong"),
                attempt(2, reasoning_effort="high"),
                attempt(3, verdict="FAIL", failure_class="quota_exhausted", model_attempt=None,
                        model="wrong-end", worker_engine="grok", task_type="wrong", reasoning_effort="low",
                        worker_tokens=90000, duration_ms=99999)]
        for aggregate in AGGREGATORS:
            with self.subTest(aggregate=aggregate.__name__):
                groups = aggregate(rows, model="openrouter/acme/worker", task_type="code-fix")
                self.assertEqual(len(groups), 1)
                group = groups[0]
                self.assertEqual((group["engine"], group["reasoning_effort"]), ("opencode", "high"))
                self.assertEqual((group["tasks"], group["attempts"], group["passed"], group["failed"]), (1, 1, 1, 0))
                self.assertEqual((group["median_tokens"], group["median_duration_ms"], group["last_seen"]), (100, 200, rows[1]["logged_at"]))
                self.assertEqual(group["infra"], {"provider_error": 1, "quota_exhausted": 1})
        self.assertEqual(ringer.task_final_rows(rows), [rows[1]])

    def test_new_rows_chain_without_retry_flags(self):
        rows = [attempt(1, verdict="FAIL", failure_class="model"),
                attempt(2, verdict="FAIL", failure_class="sandbox_denied", model_attempt=None),
                attempt(3, model_attempt=2)]
        group = ringer.aggregate_model_scoreboard_rows(rows)[0]
        self.assertEqual((group["tasks"], group["attempts"], group["retries"]), (1, 2, 1))
        self.assertEqual((group["first_try_pass_rate"], group["pass_rate"]), (0, 1))

    def test_only_infra_dropped_and_filtered(self):
        rows = [attempt(verdict="FAIL", failure_class="provider_error", model_attempt=None),
                attempt(2, verdict="FAIL", failure_class="harness_error", model_attempt=None)]
        for aggregate in AGGREGATORS:
            self.assertEqual(aggregate(rows), [])
        self.assertEqual(ringer.task_final_rows(rows), [])
        self.assertEqual(ringer.infra_only_models(rows), [{"engine": "opencode", "model": "openrouter/acme/worker",
                                                        "infra": {"provider_error": 1, "harness_error": 1}}])
        self.assertEqual(ringer.infra_only_models(rows, task_type="other"), [])
        self.assertEqual(ringer.infra_only_models(rows, model="other"), [])
        self.assertEqual(ringer.infra_only_models(rows + [attempt(run_id="work")]), [])

    def test_families_with_identical_run_and_task_keys_do_not_merge(self):
        rows = [attempt(), attempt(2, run_family="audition", verdict="FAIL", failure_class="model")]
        for aggregate in AGGREGATORS:
            groups = aggregate(rows, family="all")
            self.assertEqual({g["run_family"]: (g["tasks"], g["pass_rate"]) for g in groups},
                             {"work": (1, 1), "audition": (1, 0)})

    def test_all_helpers_reject_invalid_family_even_without_rows(self):
        for aggregate in (*AGGREGATORS, ringer.infra_only_models):
            with self.assertRaises(ValueError):
                aggregate([], family="invalid")

    def test_audition_tiers_follow_work_record(self):
        audition = [attempt(run_id=f"a{i}", run_family="audition") for i in range(4)]
        work = [attempt(run_id=f"w{i}") for i in range(3)]
        for aggregate in AGGREGATORS:
            group = aggregate(audition, family="audition")[0]
            self.assertEqual(group["tier"], "probation")
            self.assertFalse(ringer.proven_model_group(group))
            group = aggregate(audition + work, family="audition")[0]
            self.assertEqual(group["tier"], "proven")
            self.assertTrue(ringer.proven_model_group(group))

    def test_proven_delegates_to_tier_rule(self):
        with patch.object(ringer, "model_scoreboard_tier", return_value="probation") as tier:
            self.assertFalse(ringer.proven_model_group({"tasks": 5, "first_try_pass_rate": 1}))
        tier.assert_called_once_with(5, 1.0)

    def test_identity_enrichment_keeps_family_finals_separate(self):
        rows = [attempt(), attempt(2, run_family="audition")]
        groups = ringer.aggregate_model_log_rows(rows, family="all")
        with patch.object(ringer, "row_identity_fields", side_effect=lambda row, registry: {"model_display": row["run_family"]}):
            enriched = ringer.enrich_model_groups_with_identity(groups, rows, None, include_task_type=True)
        self.assertEqual({g["run_family"]: g["model_display"] for g in enriched}, {"work": "work", "audition": "audition"})
        self.assertEqual(len({g["bucket_id"] for g in enriched}), 2)


class PersistenceAndSurfacesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.log = self.root / "runs.jsonl"
        self.db = self.root / "ringer.db"
        self.rows = [attempt(), attempt(2, run_family="audition", cost_usd=0.12)]
        self.write_rows()

    def write_rows(self):
        self.log.write_text("".join(json.dumps(row) + "\n" for row in self.rows))

    def test_legacy_schema_helper_database_is_rebuilt_by_sync(self):
        with sqlite3.connect(self.db) as conn:
            ringer.create_read_model_schema(conn)
            conn.execute("INSERT INTO attempts(model, verdict) VALUES ('stale', 'FAIL')")
        self.assertTrue(ringer.sync_read_model_db(self.db, self.log).rebuilt)
        db_rows, _ = ringer.db_attempt_rows(self.db)
        self.assertEqual([row["model"] for row in db_rows], [row["model"] for row in self.rows])
        self.assertEqual(db_rows[1]["cost_usd"], 0.12)
        with sqlite3.connect(self.db) as conn:
            # A legacy caller must not downgrade a current cache.
            ringer.create_read_model_schema(conn)
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 4)
            self.assertEqual(conn.execute("SELECT version FROM schema_version").fetchone()[0], 4)
        self.assertFalse(ringer.sync_read_model_db(self.db, self.log).rebuilt)

    def test_initial_sync_creates_evidence_schema(self):
        ringer.sync_read_model_db(self.db, self.log)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 4)
            self.assertEqual(conn.execute("SELECT version FROM schema_version").fetchone()[0], 4)
        db_rows, _ = ringer.db_attempt_rows(self.db)
        for family in ("work", "audition", "all"):
            self.assertEqual(ringer.aggregate_model_log_rows(db_rows, family=family),
                             ringer.aggregate_model_log_rows(self.rows, family=family))

    def test_db_preserves_legacy_nonretry_boundaries_and_null_new_fields(self):
        legacy = {k: v for k, v in attempt().items() if k not in {"failure_class", "model_attempt", "run_family", "failure_evidence"}}
        self.rows = [legacy, dict(legacy, verdict="FAIL"), dict(legacy, retry=True),
                     attempt(run_id="new", model_attempt=None), attempt(2, run_id="new", model_attempt=None)]
        self.write_rows()
        ringer.rebuild_read_model_db(self.db, self.log)
        db_rows, _ = ringer.db_attempt_rows(self.db)
        self.assertEqual([len(task) for task in ringer.group_model_log_tasks(db_rows)], [1, 2, 2])
        for aggregate in AGGREGATORS:
            self.assertEqual(aggregate(db_rows), aggregate(self.rows))

    def test_roundtrip_all_families_and_incremental_sync(self):
        self.rows += [attempt(3, verdict="FAIL", failure_class="rate_limited", model_attempt=None),
                      attempt(4, run_id="infra", verdict="FAIL", failure_class="provider_policy", model_attempt=None)]
        self.write_rows()
        ringer.rebuild_read_model_db(self.db, self.log)
        db_rows, _ = ringer.db_attempt_rows(self.db)
        self.assertEqual(db_rows[1]["cost_usd"], 0.12)
        for family in ("work", "audition", "all"):
            for aggregate in (*AGGREGATORS, ringer.infra_only_models):
                self.assertEqual(aggregate(db_rows, family=family), aggregate(self.rows, family=family))
        result = ringer.sync_read_model_db(self.db, self.log)
        self.assertFalse(result.rebuilt)
        with self.log.open("a") as fh:
            fh.write(json.dumps(attempt(run_id="appended")) + "\n")
        ringer.sync_read_model_db(self.db, self.log)
        self.assertEqual(len(ringer.db_attempt_rows(self.db)[0]), len(self.rows) + 1)

    def test_either_old_version_stamp_triggers_rebuild(self):
        for statement in ("PRAGMA user_version = 3", "UPDATE schema_version SET version = 3"):
            ringer.rebuild_read_model_db(self.db, self.log)
            with sqlite3.connect(self.db) as conn:
                conn.execute(statement)
                conn.execute("DELETE FROM attempts")
            self.assertTrue(ringer.sync_read_model_db(self.db, self.log).rebuilt)
            self.assertEqual(len(ringer.db_attempt_rows(self.db)[0]), 2)
            with sqlite3.connect(self.db) as conn:
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 4)
                self.assertEqual(conn.execute("SELECT version FROM schema_version").fetchone()[0], 4)

    def test_api_family_applies_to_groups_and_rollup(self):
        for use_db in (False, True):
            payload = ringer.build_models_api_payload(
                log_path=self.log, default_log_path=self.root / "default.jsonl",
                db_path=self.db if use_db else None, family="audition",
                catalog_path=self.root / "no-catalog", notes_path=self.root / "no-notes",
            )
            for key in ("groups", "rollup"):
                self.assertEqual(len(payload[key]), 1)
                self.assertEqual(payload[key][0]["run_family"], "audition")
            self.assertEqual(payload["columns"], list(ringer.MODEL_SCOREBOARD_COLUMNS))

    def test_cli_family_reaches_table_explore_json_and_html(self):
        import argparse
        config = type("Config", (), {"eval": type("Eval", (), {"jsonl_path": self.root / "default.jsonl"})()})()
        for surface in ("table", "explore", "json", "html"):
            args = argparse.Namespace(log=self.log, since=None, engine=None, task_type=None, model=None,
                                      family="audition", explore=surface == "explore", json=surface == "json",
                                      html="" if surface == "html" else None)
            with patch.object(ringer, "print_model_log_table") as table, \
                 patch.object(ringer, "print_model_explore") as explore, \
                 patch.object(ringer, "write_model_scoreboard_html", return_value=self.root / "page.html") as html, \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(ringer.run_models_command(config, args), 0)
            if surface == "table":
                groups = table.call_args.args[3]
            elif surface == "explore":
                groups = explore.call_args.kwargs["groups"]
            elif surface == "html":
                groups = html.call_args.kwargs["rows"]
            else:
                groups = json.loads(output.getvalue())
            self.assertEqual([g["run_family"] for g in groups], ["audition"])


if __name__ == "__main__":
    unittest.main()
