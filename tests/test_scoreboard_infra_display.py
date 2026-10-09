"""Infrastructure detail contracts beyond the shared acceptance fixtures."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import ringer


ROOT = Path(__file__).resolve().parents[1]


class InfraDisplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.log = self.root / "runs.jsonl"
        self.registry = self.root / "registry.toml"
        self.registry.write_text('''
[engines.opencode]
harness = "OpenCode"
access = "API"
[engines.opencode.models.known]
display = "Known <model>"
lab = "Example"
slug_aliases = ["opencode:alias"]
[engines.opencode.models.only]
display = "Only <model>"
lab = "Example"
slug_aliases = ["opencode:only-alias"]
''')
        self.catalog = self.root / "catalog.json"
        self.catalog.write_text('{"models": []}')
        self.notes = self.root / "notes.md"
        self.notes.write_text("")
        self.config = self.root / "config.toml"
        self.config.write_text(
            f'state_dir = "{self.root}/state"\n[eval]\n'
            f'backend = "jsonl"\njsonl_path = "{self.root}/unused.jsonl"\n'
        )

    def row(self, model="known", failure=None, family="work", task_type="code-fix"):
        return dict(run_id=f"{model}-{failure}-{family}-{task_type}", task_key="a",
                    model=model, worker_engine="opencode", task_type=task_type,
                    verdict="FAIL" if failure else "PASS", failure_class=failure,
                    model_attempt=None if failure else 1, run_family=family,
                    logged_at="2026-10-08T12:00:00+00:00", retry=False)

    def write(self, rows):
        self.log.write_text("".join(json.dumps(row) + "\n" for row in rows))

    def payload(self, family="work", db=False):
        return ringer.build_models_api_payload(
            log_path=self.log, default_log_path=self.root / "unused.jsonl",
            db_path=self.root / "ringer.db" if db else None,
            registry_path=self.registry, catalog_path=self.catalog,
            notes_path=self.notes, family=family,
        )

    def cli(self, *args):
        result = subprocess.run(
            [sys.executable, "-B", str(ROOT / "ringer.py"), "--config", str(self.config),
             "models", "--log", str(self.log), "--registry", str(self.registry),
             "--catalog-file", str(self.catalog), "--notes-file", str(self.notes), *args],
            env=dict(os.environ, RINGER_HOME=str(self.root / "home"), RINGER_NO_SELF_UPDATE="1"),
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_api_family_aliases_and_sqlite_parity(self):
        self.write([self.row(), self.row("alias", "rate_limited"),
                    self.row("only-alias", "provider_error"),
                    self.row("only", "provider_error"),
                    self.row("audition-only", "provider_policy", "audition")])
        for db in (False, True):
            with self.subTest(db=db):
                work = self.payload(db=db)
                self.assertEqual(work["columns"], list(ringer.MODEL_SCOREBOARD_COLUMNS))
                for key in ("groups", "rollup"):
                    self.assertEqual(len(work[key]), 1)
                    self.assertEqual(work[key][0]["infra"], {"rate_limited": 1})
                    self.assertEqual(work[key][0]["tasks"], 1)
                    self.assertEqual(work[key][0]["first_try_pass_rate"], 1)
                self.assertEqual(work["infra_only"], [dict(
                    engine="opencode", model="only", model_display="Only <model>",
                    infra={"provider_error": 2})])
                audition = self.payload("audition", db=db)
                self.assertEqual(audition["rollup"], [])
                self.assertEqual(audition["infra_only"][0]["model"], "audition-only")
                self.assertEqual(len(self.payload("all", db=db)["infra_only"]), 2)

    def test_api_empty_infra_maps_and_list(self):
        self.write([self.row()])
        payload = self.payload()
        for key in ("groups", "rollup"):
            self.assertEqual(payload[key][0]["infra"], {})
        self.assertEqual(payload["infra_only"], [])

    def test_cli_one_model_line_includes_other_task_type_infra(self):
        self.write([self.row(), self.row("alias", "rate_limited"),
                    self.row("known", "rate_limited", task_type="research"),
                    self.row("known", "provider_error"), self.row("only", "provider_policy")])
        section = self.cli().split("Infrastructure failures (not counted in rates)")[1]
        self.assertEqual(section.count("Known <model>"), 1)
        self.assertIn("Known <model>: rate_limited ×2, provider_error ×1", section)
        self.assertIn("Only <model> (no model evidence yet): provider_policy ×1", section)

    def test_cli_filters_apply_to_infrastructure_only_models(self):
        self.write([self.row(), self.row("known", "rate_limited"),
                    self.row("only", "provider_error", task_type="research"),
                    self.row("only", "provider_policy", "audition")])
        work = self.cli("--task-type", "code-fix")
        self.assertIn("Known <model> [code-fix]: rate_limited ×1", work)
        self.assertNotIn("provider_error", work)
        audition = self.cli("--family", "audition", "--model", "only-alias")
        self.assertIn("Only <model> (no model evidence yet): provider_policy ×1", audition)
        self.assertNotIn("rate_limited", audition)
        self.assertNotIn("Infrastructure failures", self.cli("--model", "missing"))

    def test_html_detail_escaping_and_primary_header(self):
        self.write([self.row(), self.row("known", "<script>bad</script>"),
                    self.row("only", "provider_error")])
        target = self.root / "scoreboard.html"
        self.cli("--html", str(target))
        page = target.read_text()
        self.assertIn("Known &lt;model&gt;", page)
        self.assertIn("Only &lt;model&gt; (no model evidence yet): provider_error ×1", page)
        self.assertIn("&lt;script&gt;bad&lt;/script&gt; ×1", page)
        self.assertNotIn("<script>bad</script>", page)
        header = page.split("<thead>", 1)[1].split("</thead>", 1)[0]
        self.assertEqual(re.findall(r"<th[^>]*>(.*?)</th>", header), list(ringer.MODEL_SCOREBOARD_COLUMNS))
        detail = page.split('<details class="model-detail">', 1)[1].split("</details>", 1)[0]
        self.assertIn("Infrastructure failures (not counted in rates)", detail)

    def test_html_infrastructure_only_without_ranked_evidence(self):
        self.write([self.row("only", "provider_error")])
        target = self.root / "scoreboard.html"
        self.cli("--html", str(target))
        page = target.read_text()
        self.assertIn("No local model evidence", page)
        self.assertIn("Infrastructure only", page)
        self.assertIn("provider_error ×1", page)

    def test_legacy_tab_renders_expanded_detail_and_infra_only_empty_state(self):
        template = ('<style>    main {\n}</style>\n    <main>\n'
                    '<section id="artifacts-panel"></section>\n    </main>\n'
                    '<script>\n    tickClock();\n</script>')
        page = ringer.inject_models_tab_into_ringside_html(template)
        script = page.split("<script>")[1].split("</script>")[0]
        harness = r'''
const assert = require("node:assert/strict");
const elements = new Map();
const document = { getElementById(id) {
  if (!elements.has(id)) elements.set(id, {
    events: {}, classList: { toggle() {} }, setAttribute() {},
    addEventListener(name, fn) { this.events[name] = fn; }
  });
  return elements.get(id);
}};
const localStorage = { getItem: () => "models", setItem() {} };
const setInterval = () => {};
const tickClock = () => {};
let payload = {
  rollup: [{display_bucket_id: "one", model_display: "<Model>", infra: {provider_error: 1, rate_limited: 3}}],
  groups: [{display_bucket_id: "one", task_type: "<task>", infra: {"<error>": 2}}],
  infra_only: [{model_display: "<Only>", infra: {provider_error: 4}}]
};
const fetch = async () => ({json: async () => payload});
'''
        checks = r'''
setImmediate(async () => {
  const wrap = elements.get("models-table-wrap");
  wrap.events.click({target: {closest: () => ({getAttribute: () => "one"})}});
  assert.match(wrap.innerHTML, /rate_limited ×3, provider_error ×1/);
  assert.match(wrap.innerHTML, /&lt;task&gt;/);
  assert.match(wrap.innerHTML, /&lt;error&gt; ×2/);
  assert.match(wrap.innerHTML, /&lt;Only&gt; \(no model evidence yet\): provider_error ×4/);
  assert.equal((wrap.innerHTML.split("</thead>")[0].match(/<th[ >]/g) || []).length, 12);
  assert.doesNotMatch(wrap.innerHTML, /<Model>|<Only>|<error>/);
  payload = {...payload, rollup: [], groups: []};
  elements.get("models-tab").events.click();
  await new Promise(resolve => setImmediate(resolve));
  assert.match(wrap.innerHTML, /No model results yet/);
  assert.match(wrap.innerHTML, /Infrastructure only/);
  assert.match(wrap.innerHTML, /provider_error ×4/);
});
'''
        result = subprocess.run(["node", "-e", harness + script + checks],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
