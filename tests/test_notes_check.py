"""Additional parser, evidence, and git-history coverage for notes check."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import ringer


MODEL = 'openrouter/z-ai/glm-5.2'
CITATION = (
    '[evidence: run=run-1 task=fix model=' + MODEL
    + ' attempt=1 verdict=FAIL type=code-fix family=work]'
)


def row(**changes):
    result = dict(run_id='run-1', task_key='fix', model=MODEL, model_attempt=1,
                  verdict='FAIL', failure_class='model', task_type='code-fix')
    result.update(changes)
    return result


class ParserAndEvidenceTests(unittest.TestCase):
    def test_parser_keeps_duplicate_sections_and_continuations(self):
        text = '''- 2026-10-08 outside any heading
## model
- undated
- 2026-10-08 first
  continued

  more
plain paragraph
  detached continuation
## model
- second
  2026-10-09 date in continuation
'''
        self.assertEqual(ringer.parse_model_notes_entries(text), [
            ('model', ['2026-10-08 first\ncontinued\n\nmore']),
            ('model', ['second\n2026-10-09 date in continuation']),
        ])

    def test_regex_requires_every_field_and_enum(self):
        self.assertIsNotNone(ringer.MODEL_NOTES_EVIDENCE_RE.fullmatch(CITATION))
        for invalid in [CITATION.replace(' type=code-fix', ''),
                        CITATION.replace('FAIL', 'UNKNOWN'),
                        CITATION.replace('family=work', 'family=probe'),
                        CITATION.replace('attempt=1', 'attempt=0'),
                        CITATION.replace('attempt=1', 'attempt=-1')]:
            with self.subTest(invalid=invalid):
                self.assertIsNone(ringer.MODEL_NOTES_EVIDENCE_RE.fullmatch(invalid))

    def test_heading_aliases_and_boundaries(self):
        registry = ringer.load_model_identity_registry()
        for heading in [MODEL, 'z-ai/glm-5.2', 'GLM 5.2 via OpenCode']:
            self.assertTrue(ringer.model_notes_heading_matches(heading, MODEL, registry))
        for heading in [MODEL + '-fast', 'x' + MODEL, 'GLM 5.20', 'opencode']:
            self.assertFalse(ringer.model_notes_heading_matches(heading, MODEL, registry))
        for heading in ['grok-build', 'Grok 4.5']:
            self.assertTrue(ringer.model_notes_heading_matches(
                heading, 'openrouter/x-ai/grok-4.5', registry))

    def test_model_evidence_and_legacy_default_family(self):
        match = ringer.MODEL_NOTES_EVIDENCE_RE.fullmatch(CITATION)
        legacy = row()
        del legacy['failure_class']
        for evidence in [row(), row(failure_class=None), legacy]:
            self.assertEqual(ringer.model_notes_citation_errors(match, [evidence]), [])
        for failure_class in ['rate_limited', 'provider_error', 'quota_exhausted',
                              'provider_policy', 'sandbox_denied', 'harness_error']:
            with self.subTest(failure_class=failure_class):
                self.assertEqual(ringer.model_notes_citation_errors(
                    match, [row(failure_class=failure_class)]), ['not model evidence'])

    def test_pass_is_model_evidence_and_timeout_can_be(self):
        for verdict in ['PASS', 'TIMEOUT']:
            match = ringer.MODEL_NOTES_EVIDENCE_RE.fullmatch(CITATION.replace('FAIL', verdict))
            self.assertEqual(ringer.model_notes_citation_errors(
                match, [row(verdict=verdict)]), [])

    def test_every_attempt_key_must_match(self):
        match = ringer.MODEL_NOTES_EVIDENCE_RE.fullmatch(CITATION)
        for changes in [dict(run_id='other'), dict(task_key='other'),
                        dict(model='other'), dict(model_attempt=2), dict(model_attempt=None)]:
            self.assertEqual(ringer.model_notes_citation_errors(match, [row(**changes)]),
                             ['run not found'])

    def test_all_row_failures_reported(self):
        match = ringer.MODEL_NOTES_EVIDENCE_RE.fullmatch(CITATION)
        self.assertEqual(ringer.model_notes_citation_errors(match, [row(
            verdict='TIMEOUT', run_family='audition', failure_class='provider_error')]),
            ['verdict mismatch', 'family mismatch', 'not model evidence'])

    def test_display_strips_multiple_and_wrapped_citations(self):
        value = '**Clean** `fix`. ' + CITATION + '\n' + CITATION.replace(' task=', '\n task=')
        self.assertEqual(ringer.strip_inline_markdown(value), 'Clean fix.')
        self.assertEqual(ringer.strip_inline_markdown('[label](https://example.com) _ok_'),
                         'label ok')


class GitHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.notes = self.repo / 'docs' / 'MODEL NOTES.md'
        self.notes.parent.mkdir()
        self.notes.write_text('## GLM 5.2\n- 2026-10-01 old note\n\n'
                              '## GLM 5.2\n- 2026-10-02 second old note\n')
        self.git('init', '-q')
        # Commit an explicit fixture tree without staging or changing a real repo.
        blob = self.git('hash-object', '-w', str(self.notes)).strip()
        tree = self.git('mktree', input=f'100644 blob {blob}\tMODEL NOTES.md\n').strip()
        root = self.git('mktree', input=f'040000 tree {tree}\tdocs\n').strip()
        commit = self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.com',
                          'commit-tree', root, input='fixture\n').strip()
        self.git('update-ref', 'refs/heads/fixture', commit)
        self.args = argparse.Namespace(notes_file=self.notes, base='fixture', log=None)

    def git(self, *args, input=None):
        return subprocess.run(['git', *args], cwd=self.repo, input=input, text=True,
                              capture_output=True, check=True).stdout

    def check(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = ringer.run_notes_check_command(self.args)
        return status, output.getvalue()

    def test_reflow_and_move_between_duplicate_headings_not_new(self):
        self.notes.write_text('## GLM 5.2\n- 2026-10-02 second\n  old note\n'
                              '- 2026-10-01   old\n  note\n## GLM 5.2\n')
        self.assertEqual(self.check(), (0, '0 entries checked\n'))

    def test_case_edit_and_heading_rename_are_new(self):
        self.notes.write_text('## GLM 5.2\n- 2026-10-01 OLD note\n'
                              '## GLM 5.2 renamed\n- 2026-10-02 second old note\n')
        status, output = self.check()
        self.assertEqual(status, 1)
        self.assertEqual(output.count('missing evidence'), 2)
        self.assertIn('2 entries checked', output)

    def test_file_absent_at_base_checks_every_dated_entry(self):
        self.args.notes_file = self.repo / 'docs' / 'new.md'
        self.args.notes_file.write_text('## GLM 5.2\n- undated\n- 2026-10-08 new ' + CITATION)
        self.assertEqual(self.check(), (0, '1 entries checked\n'))

    def test_continuation_citations_and_multiple_citations(self):
        self.notes.write_text('## GLM 5.2\n- 2026-10-08 new\n  ' + CITATION
                              + '\n  ' + CITATION.replace('run-1', 'missing'))
        self.args.log = self.repo / 'runs.jsonl'
        self.args.log.write_text(json.dumps(row()) + '\n')
        status, output = self.check()
        self.assertEqual(status, 1)
        self.assertIn('run not found', output)
        self.assertIn('1 entries checked', output)
        self.assertEqual(len(output.splitlines()), 2)

    def test_valid_citation_does_not_hide_malformed_one(self):
        self.notes.write_text('## GLM 5.2\n- 2026-10-08 new ' + CITATION
                              + ' [evidence: run=broken]')
        status, output = self.check()
        self.assertEqual(status, 1)
        self.assertIn('invalid citation', output)


if __name__ == '__main__':
    unittest.main()
