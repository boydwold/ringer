# Model audition set

Six small Python 3.11+ tasks measure repair, implementation and review ability.
Each attempt should take a strong model about 1–3 minutes. Every verdict comes
from an executed, deterministic standard-library check, without network access,
credentials or external data. Token estimates are conservative harness budgets,
not expected answer lengths.

| Key | Type | Measures |
|---|---|---|
| fix-paginate-off-by-one | code-fix | Index boundaries, validation and input preservation |
| fix-duration-parse | code-fix | Complete parsing, units and malformed-input rejection |
| add-csv-summary | code-feature | CSV records, column classification and aggregation |
| add-json-flag | code-feature | CLI extension with exact backward compatibility |
| review-inventory | code-review | State isolation, stock invariants and error propagation |
| review-auth-guard | code-review | Secret comparison, permissions and expiry boundaries |

## Layout and execution

Each task contains task.toml (key, title, type, deliverables, token budget),
spec.md (worker brief), fixture/ (starting files), reference/ (known-good overlay),
and check.py (private grader). Copy only fixture/ into a fresh task directory
and give the worker spec.md. Code workers edit the named files; review workers
write report.md. Answers live in check.py/reference/, which workers never see.
Do not expose this entire repository or notes to audition workers. The runner
must keep the grader and answer files outside the worker's readable workspace.

Run `python3 -I /absolute/path/to/task/check.py` with cwd set to the task directory.
Checks import modules from that cwd under unique names, disable bytecode writes,
and leave input files unchanged. The CLI check also executes isolated python3
subprocesses. Review checks read reports without executing fixture code. They
accept defect statement citations with one line of tolerance or specified short
ranges, reject decoy citations and more than eight distinct cited source lines,
and require prose alongside citations. They grade finding locations, not prose
quality or suggested fixes; free-form explanation semantics need human review.
Repeated citations do not increase the distinct-line count. This is a bounded
behavioural audition, not proof against a malicious worker or exhaustive proof
of correctness for all possible programs.

To exercise a reference, copy fixture/ to a fresh task directory, overlay
reference/, and run the same check there. From the repository root run:

```sh
python3 -m unittest tests.test_audition_set_acceptance -v
```

Acceptance also runs references through engines/check-sandboxed.sh when Linux
and bwrap are available. The launcher supplies the timeout and offline sandbox.

## Adding a task

Create a new directory whose name equals task.toml's key. Choose code-fix,
code-feature or code-review; declare relative expect_files and a realistic
20000–80000 token_estimate. Keep fixtures under roughly 150 lines total and
specify exact behaviour, input scope, deliverable names and file boundaries.
Keep planted answers and line coordinates out of the worker brief and comments.

Write a self-contained stdlib check with clear PASS/FAIL lines and exit status
0/1. Never write to fixtures or import network libraries. Test every reference,
the untouched fixture, and plausible incomplete implementations. Review tasks
need precise defect and decoy ranges plus generic, missing, empty and spam-report
negative checks. Recheck coordinates whenever fixture text changes. Verify
repeated runs, no file mutations and execution in the offline check sandbox;
then update this table and run acceptance. Never use a success-only grader.
