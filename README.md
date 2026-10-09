# Ringer

[![tests](https://github.com/NateBJones-Projects/ringer/actions/workflows/tests.yml/badge.svg)](https://github.com/NateBJones-Projects/ringer/actions/workflows/tests.yml)

![Ringer — she reviews; the wall works](docs/hero.png)

**Parallel AI-agent swarms that prove their work. Your expensive model plans and reviews; cheap workers do the typing.**

Frontier models are finally good enough to trust with real implementation — but their tokens are priced like senior-engineer hours, and most of a build is not senior-engineer work. It's scaffolding, migrations, test suites, batch transforms. Mechanical labor.

So split the roles. Your best model writes the specs and reviews the results. A swarm of cheap workers — Codex, Grok, anything with a CLI — does the implementation in parallel. Your premium budget stops scaling with lines of code written and starts scaling with decisions made.

One problem: parallel agents lie. "Done" doesn't mean working. Ringer doesn't take the worker's word for anything — it **executes your check command** against the artifact. Pass or fail is decided by running the code, not by reading the agent's summary. Failures retry once with the failure context injected, and every attempt is logged so your setup gets measurably better over time.

And because a swarm you can't see is a swarm you don't trust: **Ringside**, a local web page every run opens automatically, showing every live swarm on your machine — who's running it, what each worker is doing, elapsed time, token burn — in real time, plus a versioned library of what past runs produced.

## How it works

```
manifest.json ──▶ ringer.py ──▶ N parallel workers (codex exec, each in its own dir)
                      │                │
                      │                ▼
                      │         executed checks ── fail ──▶ retry once w/ failure context
                      │                │
                      ▼                ▼
              ~/.ringer/runs/    eval log (JSONL or Postgres)
                      │
                      ▼
              Ringside, in the browser (live, all swarms, all identities)
```

## Quickstart

Ringer runs on macOS and Linux (Windows via WSL) and needs Python 3.12+.

1. Install a worker CLI and sign in (Codex is the built-in default engine):

```bash
npm install -g @openai/codex   # or: brew install --cask codex
codex login                    # sign in with your ChatGPT plan
```

2. Get the repo:

```bash
git clone https://github.com/NateBJones-Projects/ringer && cd ringer
mkdir -p ~/.config/ringer && cp config.sample.toml ~/.config/ringer/config.toml   # optional — sane defaults without it
```

3. Teach your agent to route work through Ringer:

```bash
# optional but recommended: teach your agent to route work through ringer
./ringer.py install-agent
```

4. Run the demo:

```bash
./ringer.py demo                                      # 3 real workers, verified end to end
```

The demo spawns three Codex workers in parallel, verifies each artifact by executing it, and prints a verdict table — and Ringside, the live dashboard, opens in your browser on its own. If all three say PASS, that's the whole setup.

Run your own batch:

```bash
./ringer.py run swarm.json --max-parallel 4
```

```json
{
  "run_name": "my-batch",
  "workdir": "/tmp/my-batch",
  "max_parallel": 3,
  "tasks": [
    {
      "key": "alpha",
      "spec": "Create alpha.txt containing exactly one line: alpha ready\nEnd the file with exactly one newline. Do not add punctuation.",
      "check": "printf 'alpha ready\\n' | diff -u - alpha.txt || { echo 'FAIL: alpha.txt must contain exactly alpha ready followed by one newline'; exit 1; }",
      "expect_files": ["alpha.txt"]
    }
  ]
}
```

Each task gets its own directory, its own worker, its own log, and its own verdict. `check` is any shell command — exit 0 is the only thing Ringer believes.

> **Write checks that print why they fail.** A silent `exit 1` (the `git diff --quiet` style) costs you twice: the retry prompt gets no failure context to fix against, and the eval log records an undiagnosable row. `diff` beats `diff -q`; an assert with a message beats a bare test.

> **Checks are killed at 60 seconds by default** (`CHECK_TIMEOUT_S`), and the kill is recorded as a task FAILURE — a finished, correct deliverable gets thrown away. Raise it per task with `check_timeout_s`; a longer timeout passed *inside* your own check script cannot raise it, because Ringer kills the whole check from outside. Even with a raised cap, prefer a cheap check: have the worker TEE expensive output to a log file and have the check re-assert the cheap facts plus grep that log for the exact numbers the report claims. A check that runs a full suite is slow feedback on every attempt, not just the failing one.

> **A check cannot demand evidence the spec never supplied.** Before failing a worker for missing evidence or input, re-read the task inputs. If the spec didn't provide a value, the check must not invent one and fail on its absence — an honest UNVERIFIABLE answer is not a failure. Reserve hard failure for what the spec actually asserted.

> **Executed checks catch laziness, not subtle wrongness.** A check that *runs* the artifact catches a plausible-but-wrong change far less often than it catches a missing one. Whenever a swarm touches a dogfood artifact (Ringer's own docs, config, or checks), add an "our own artifact passes our own validator" test so the checker exercises what it preaches. And keep orchestrator patch review mandatory regardless of PASS status — a green check is not proof of semantic correctness.

**Identity**: runs are stamped with an orchestrator identity (shown in Ringside and eval rows). Resolution order: `--identity` > `FLEET_IDENTITY`/`RINGER_IDENTITY` env > a `.fleet-agent` file found walking up from the working directory (drop one in a repo root to give that repo's swarms their own name) > `identity_default` in config > short hostname.

### Manifest fields

| Field | What it does |
|---|---|
| `key` | Task name — becomes the working subdirectory and the label everywhere |
| `spec` | The prompt handed to the worker |
| `check` | Shell command run after the worker exits; exit 0 = PASS |
| `expect_files` | Files that must exist and be non-empty before the check runs |
| `engine` | Which configured engine runs this task (default `codex`) |
| `model` | Which model a harness engine runs for this task — fills the engine's `{model}` placeholder (e.g. `"openrouter/moonshotai/kimi-k2.7"`); empty uses the engine's `model_default` |
| `task_type` | Optional free-form string naming the kind of work this task is, so the model-performance log can slice pass rates by task shape rather than only by model. Suggested vocabulary: `code-feature`, `code-fix`, `code-review`, `test-hardening`, `docs`, `research`, `persona-review`, `copywriting`, `site-build`, `motion-design`, `image-gen`, `data-pipeline`, `format-conversion`, `probe`, `bakeoff`. Empty is allowed; the log just reports it under `(none)`. |
| `timeout_s` | Per-task kill timer for the worker (default 900) |
| `check_timeout_s` | Per-task kill timer for the `check` command (default 60). Raise it when the check must run something genuinely slow; the timeout message names this field and lands in the retry prompt |
| `max_attempts` | Maximum model attempts (default 2 — one try plus one retry with failure context). Set `1` to disable model re-prompts; provider retries still apply |
| `redact_spec` | Replace this task's spec with `[redacted request packet]` in the run state, the logged command line, and the eval row, for specs carrying sensitive material. Redacts Ringer's own records only — captured worker output is never rewritten (invariant), so a worker that echoes its request still puts that text in `worker.log` |
| `engine_args` | Extra CLI flags for this task's worker, spliced in at the engine's `{engine_args}` placeholder — e.g. `["-c", "model_reasoning_effort=low"]` so the orchestrator picks reasoning depth per task |
| `verified` | One plain-English sentence saying what the check proves — shown on the results page next to "finished & checked" |
| `full_access` | Worker runs unsandboxed — required for workers that spawn their own sub-workers; must also be enabled in config |
| `family` (run-level) | `"work"` (default) or `"audition"`; recorded as `run_family` on attempt rows |
| `worktrees` (run-level) | Give each task an isolated git worktree of `repo` so parallel workers can't collide |
| `meta` (run-level and per task) | Optional JSON object Ringer copies untouched into the run state (`meta` on the run and on each task), so outside tools can link a work order to where it came from — for example `{"openspec": {"change": "add-sso-login", "task": "2.1"}}`. At most 16 KB each; Ringer never reads it |

The run state file (`~/.ringer/runs/<run_id>.json`) carries `state_version` (now `2`). Tools that read it should refuse a version they do not know; it goes up whenever a field they read changes meaning or shape.

> **Worktree footgun:** on PASS the task's worktree is removed — including anything written inside it. In worktrees mode, worker logs live outside task worktrees in `workdir/logs/`; have workers write deliverables outside the worktree too, or have your `check` copy artifacts out before it exits 0.

Not sure what your tasks even are yet? [`docs/interview-prompt.md`](docs/interview-prompt.md) is a prompt you paste into any chatbot; it interviews you about the job and hands back a brief your orchestrating agent can turn into a manifest. Ready-made skeletons for the patterns that work live in [`templates/`](templates/).

## `ask` — one bounded question, one clean worker

Not every question deserves a manifest. When you want a read-only answer over
source you can already point at, `ask` selects the passages that match the
request, caps the packet, and runs a single worker on it:

```bash
./ringer.py ask "Why did the Wednesday release slip?" --source notes/status.md
./ringer.py ask "..." --source src/ --source docs/ --dry-run   # show the packet, spend nothing
```

Repeat `--source` for more files or directories. `--state` takes a small file
of settled decisions and is preferred over ordinary sources when the packet is
tight. `--max-packet-bytes` sets the budget (default 16,000). `--dry-run`
prints the selection report and stops before any model call. `--redact` keeps
the request out of the run state and eval row. The run appears on Ringside and
in the artifact library like any other.

If everything that matches is too big for the packet, `ask` says so — naming the
budget you'd need — and stops **before** calling a model. It never sends an
empty packet. A source small enough to fit whole is included whole, whether or
not it looks relevant, so pointing `ask` at unrelated material still costs one
call: the packet is only as good as the sources you name.

Directory scans stay inside the tree you named. A symlink pointing out of it, or
one resolving to a sensitive filename, is skipped and reported. A file you name
explicitly is always read — naming it is consent.

> `ask` verifies only that an answer was produced and is non-empty. There is
> nothing to execute against free-form prose, so this is the one lane in Ringer
> where the check does not prove the result is right. Read the answer. Anything
> whose output a check could actually execute belongs in a manifest.

## Lint

Lint checks a manifest for the mistakes that make swarms hard to trust: checks that cannot fail, silent checks, worktree deliverables that disappear, worker commits that die with deleted worktrees, deliverables declared outside the worker's writable root, serial fan-out, write collisions, and underspecified specs.

```bash
./ringer.py lint templates/review-swarm/manifest.json
lint: clean (1 tasks)
```

`run` and `demo` also print any lint findings as non-blocking warnings after the manifest loads. They teach at the moment of use; they do not stop a run.

A check that cannot fail is trusting the worker with extra steps.

### Baseline: prove your checks before spending tokens

Lint reads the manifest; `--baseline` executes it — every task's `check` runs against the unmodified tree, spawning no workers and writing no eval rows:

```bash
./ringer.py run swarm.json --baseline
```

Each check runs in a fresh scratch dir (a detached worktree when the manifest uses worktrees) through the same verifier as a real run. Reading the results: an assertion that demands the NEW behavior workers will build is *expected* to FAIL baseline; an assertion about UNCHANGED behavior that fails baseline is a bug in the check itself, and at run time it would burn a worker's attempts against something no model can satisfy. Fix the check before spawning.

## Make your agent actually use this

Between swarms, agents drift back to invisible inline work. Reminders decay, so enforcement ships with the product.

Run one command:

```bash
./ringer.py install-agent
```

It installs the ringer skill — the orchestrator playbook — user-level for Claude Code, and registers two gentle hooks: a Bash hook that notices model-calling or harness commands running outside a live Ringer run, and an edit-loop hook that notices batch editing without a run. Each hook nudges ONCE per session, pointing the agent at the skill.

The hooks never block anything. A user who says "just do it inline" is obeyed; uninstall with `./ringer.py uninstall-agent`.

For CI and evals, `config.sample.toml` includes `[engines.mock]` so the enforcement stack can be tested without an API bill.

## Engines are pluggable

![Identical workers, each under its own light](docs/engines.png)

Ringer ships with three worker lanes: **Codex CLI** is the built-in default, and `config.sample.toml` carries verified engine blocks for **Grok Build CLI** (works as-is once you `grok login`) and **OpenCode + OpenRouter** (one edit: point `bin` at the sandbox wrapper in your clone). Anything else with a headless CLI is a config block away:

```toml
[engines.mymodel]
bin = "/usr/local/bin/mycli"
args_template = ["run", "{spec}", "--dir", "{taskdir}"]
```

Per-task `"engine": "mymodel"` routes work to it — the invariants (stdin closed, process-group kill, executed verification, raw logs) apply to every engine identically.

### The universal harness: OpenCode + OpenRouter

Unless a model ships its own first-class harness (Codex does), OpenCode is the harness that runs it — one engine block covers every OpenRouter-served model. `config.sample.toml` includes a ready-to-uncomment engine whose `{model}` placeholder is filled per task from the manifest's `"model"` field, with `model_default` as the fallback. The shipped default is OpenRouter's `z-ai/glm-5.2` — roughly $0.74/M input and $2.33/M output (2026-07), about 20-30x cheaper output than frontier coding models; a complete write-code-and-pass-the-check task lands around a penny.

OpenCode ships no OS sandbox, so the engine's `bin` points at an absolute path to `engines/opencode-sandboxed.sh` (ringer does not resolve engine bins relative to the repo). The wrapper uses macOS Seatbelt or Linux bubblewrap, allowing network and reads while confining persistent writes to the task dir, a per-run scratch dir (`TMPDIR`/`XDG_CACHE_HOME`), and OpenCode's share/state dirs. `~/.config/opencode` stays read-only. Headless approval flags (`--auto` on OpenCode 1.18.x, `--dangerously-skip-permissions` on older versions) only silence interactive prompts; the wrapper supplies OS containment. On macOS, task and hidden paths reach Seatbelt through `sandbox-exec -D` parameters, so quotes or parens cannot inject profile rules. `--no-sandbox` is wired as the engine's `full_access_args`, so ringer's `allow_full_access` gate still governs escapes. Other platforms fail closed.

Setting it up takes about five minutes:

```bash
# 1) Install the OpenCode CLI (pick one)
curl -fsSL https://opencode.ai/install | bash
# or: npm install -g opencode-ai
# or: brew install anomalyco/tap/opencode

# 2) Connect OpenRouter — create a key at https://openrouter.ai/settings/keys
opencode auth login   # select OpenRouter, paste the key

# 3) In ~/.config/ringer/config.toml, uncomment [engines.opencode] and set
#    bin to the ABSOLUTE path of engines/opencode-sandboxed.sh in this clone.
#    Linux also requires bwrap and working unprivileged user namespaces.
```

Route with per-task `"engine": "opencode"`, pick the model with per-task `"model": "openrouter/<any-model>"`, and set reasoning effort via `engine_args`: `["--variant", "low|high|max"]`. A sensible split: mechanical or tightly-specced tasks on the cheap lane, gnarly ones on your frontier engine — the executed check catches shortfalls either way, and `swarm_runs` rows tell you whether the cheap lane's pass rate holds.

### Linux sandbox

The OpenCode wrapper requires `bwrap` (bubblewrap). It mounts the host filesystem read-only and permits persistent writes only in the task directory and per-run scratch directory. Scratch is removed when the wrapper exits. Host `/tmp` and `/run/user/$(id -u)` are replaced by private, writable tmpfs mounts, hiding session sockets. Explicit task/scratch mounts remain visible; a HOME or executable beneath those temporary locations is restored read-only. The wrapper removes `DBUS_SESSION_BUS_ADDRESS`, `SSH_AUTH_SOCK`, `DISPLAY`, `WAYLAND_DISPLAY`, and every `HERDR_*` environment variable. PID/IPC namespaces contain child processes; missing bwrap or failed sandbox setup stops the run.

Each Linux attempt gets its own OpenCode data and state directories under scratch via `XDG_DATA_HOME` and `XDG_STATE_HOME`, so parallel workers use separate databases. If present, the main `auth.json` is copied into the attempt with mode `600`; workers can read that credential copy, but cannot see the original `~/.local/share/opencode/auth.json` or session history because the legacy paths expose only empty, writable compatibility directories. Missing legacy directories are created only inside the sandbox, leaving the real home unchanged. macOS still shares OpenCode credentials and history; isolation there is a follow-up.

Set `RINGER_SANDBOX_HIDE=/absolute/secret:/absolute/other` to hide additional paths: existing directories read as empty and regular files read as `/dev/null` on Linux; macOS denies reads through parameterized Seatbelt rules. Entries must be absolute and cannot contain colons. Set `OPENCODE_BIN` to pin an executable (otherwise the wrapper finds `opencode` on PATH), or `RINGER_SANDBOX_BWRAP` to select a bwrap executable. For OpenCode 1.18.x, use `--pure` to skip user plugins and `--auto` for headless approval; see the Linux example in `config.sample.toml`.

For offline checks, run `engines/check-sandboxed.sh <taskdir> <timeout_s> <command...>` (for example, `engines/check-sandboxed.sh "$PWD" 60 bash -c 'make test'`). This Linux-only wrapper permits file writes only in the task directory, masks host temporary paths with private read-only mounts, and disables network with `--unshare-net`. The task directory remains writable even beneath `/tmp`; checks needing temporary files should place them inside it. It passes through the command's exit status and reports timeouts with exit 124, using `timeout --kill-after=5`. It also supports `RINGER_SANDBOX_BWRAP` and fails closed if setup fails.

The OpenCode worker shares the host network namespace so API access, DNS, and local TCP still work. **Abstract Unix sockets remain reachable**, even though filesystem session sockets are hidden; reachable host services remain a containment risk.

### The plan lane: Grok Build CLI

If you already pay for SuperGrok or X Premium Plus, Grok Build is a second flat-rate worker lane — no per-token bill:

```bash
# 1) Install (pick one)
curl -fsSL https://x.ai/cli/install.sh | bash
# or: npm install -g @xai-official/grok

# 2) Sign in — OAuth on a SuperGrok or X Premium Plus plan
grok login

# 3) In ~/.config/ringer/config.toml, uncomment [engines.grok]
```

Route with per-task `"engine": "grok"` and pick the model with `"model": "grok-build"` or `"model": "grok-composer-2.5-fast"` (the shipped default — the speed pick). Grok brings its own OS sandbox on macOS (profile `workspace`: read everywhere, writes confined to the task dir, temp, and `~/.grok`), and its JSON output exposes no token counts — plan-billed workers report cost as included in plan.

`args_template` is an argv array, not a shell string. Ringer replaces `{taskdir}`, `{spec}`, and `{model}` inside each argv element. `{access_args}`, `{sandbox_args}`, `{full_access_args}`, `{model_args}` (becomes `-m <resolved model>` when the task or engine names one), and `{engine_args}` (the task's per-task `engine_args`) expand to multiple argv elements only when they appear as their own array item.

Watch for variadic CLI flags. If an engine has a flag that consumes all following values, put `{spec}` before that flag. For Claude-style CLIs, prefer:

```toml
args_template = ["-p", "{spec}", "--allowedTools", "Bash"]
```

not:

```toml
args_template = ["-p", "--allowedTools", "Bash", "{spec}"]
```

Each worker process runs with cwd set to `workdir/<task.key>/`. Use absolute paths in `spec` when workers need shared inputs outside their task directory.

## Ringside — mission control

![Ringside in the browser: a run's live results page with per-worker status and verification](docs/ringside.png)

Ringside is a local web page — no install, no account, nothing leaves your machine. Your first run opens it automatically; every later run streams into the same tab:

```bash
./ringer.py run manifest.json   # starts Ringside and opens the tab for you
./ringer.py hud                 # or open it any time → http://127.0.0.1:8700
```

`./ringer.py hud` reuses an open Ringside tab when it has pinged the server within the last 15 seconds. Use `./ringer.py hud --force-open` to open a new tab anyway, or set `reuse_open_tab = false` under `[hud]` in your config to always open one.

**Live runs** shows every swarm, its progress, and a searchable task table. Select a task to inspect its brief, model, harness, attempts, last executed check and raw worker log. A failed check stays visible while its task retries; stopped workers are marked explicitly. **Outputs** keeps each run's result and saved versions together, with a live preview and access to its folder. **Models** shows first-try pass rates alongside task/attempt counts, task-type filtering and a low-sample warning. Expand all signals for the full scoreboard and judgment notes. Compact view keeps live runs and runs needing attention in a small window.

Multiple swarms at once is the designed-for case: run three batches under three identities and Ringside shows all three, live. `--browser` opens a simpler per-run fallback dashboard, and `--no-dashboard` runs headless.

A native desktop build (Tauri, under `hud/`) exists as a v0.1.1 prototype. It shares `dashboard/ringside.html`, `ringside.css` and `ringside.js` with the browser, plus the native transport in `hud/frontend/hud.js`. The browser remains the primary interface. Native Models and folder actions need the local `ringer.py hud` server; runs and artifact reads also have native transports. Build assets under `hud/dist/` are generated by `hud/scripts/sync-dist.sh`, never edited directly. The older `dashboard/dashboard.html` remains the per-run `--browser` fallback.

The visual direction is recorded in [the Ringside Figma design](https://www.figma.com/design/iG6yecFGAcwTH4rUos3Juk?node-id=5-2). Verification and a disposable preview fixture are documented in [tests/TESTING.md](tests/TESTING.md).

## Self-update

Ringer checks `origin/main` at process start, before it dispatches the requested command. Checks are throttled to once per hour by default. You can also run `./ringer.py self-update` for an immediate, human-readable check that ignores the throttle.

An automatic update applies only when the checkout containing `ringer.py` is on `main`, has no tracked changes, and `origin/main` can be reached with a fast-forward-only update. Untracked files do not block it. After applying, Ringer restarts the original invocation so the requested command runs on the new code.

Ringer never creates a merge commit, never rebases, never stashes or deletes changes, and never updates a dirty tracked tree. Regular commands do not update in the middle of a run: their only check happens at process start before dispatch.

The persistent `hud` command is the exception for long-running code. It checks on the configured interval and restarts itself after an ff-only update. It also restarts when the checkout's on-disk HEAD changes after a manual pull. Before restarting it closes the HTTP server, whose socket is configured for immediate reuse. If an update is available but blocked, Ringside keeps serving the running code and shows the reason in a dismissible banner.

Disable automatic checks for one invocation with `--no-self-update`, for an environment or service with `RINGER_NO_SELF_UPDATE=1`, or permanently in config:

```toml
[update]
auto = false
check_interval_s = 3600
```

## The eval loop

![Timed, verified, logged](docs/eval-loop.png)

Every worker attempt — pass, fail, timeout, retry — is logged with its spec, engine, duration, token count, and the raw check output. Local JSONL by default; point `[eval.postgres]` at a database to aggregate across machines. Failure rows are the point: they tell you which spec styles, engines, and task shapes actually work, so the swarm gets better on evidence instead of vibes.

## Failure classes and provider retries

Failed attempts have one of seven classes: `model`, `rate_limited`,
`provider_error`, `quota_exhausted`, `provider_policy`, `sandbox_denied`, or
`harness_error`. Model failures use the task's `max_attempts` budget and retry
with that attempt's worker and check output as failure context. Rate limits and
provider errors retry the original spec without consuming that budget, including
for `ask` (`max_attempts=1`). The parallel slot is free while the task is
`waiting_provider`; the terminal and Ringside report the wait. Exhausted provider
retries and the other four infrastructure classes stop the task immediately.

Optional config settings (defaults shown):

```toml
[retry]
infra_max = 3
infra_base_delay_s = 30
infra_max_delay_s = 300
```

`infra_max` is a nonnegative integer counting retries after the initial failure.
Delays are nonnegative seconds, doubling each time up to `infra_max_delay_s`.
Signals interrupt the wait through the normal run cancellation path.

Attempt rows add `failure_class` (null on PASS), `failure_evidence` (a sanitized,
single-line excerpt, at most 300 characters), `model_attempt` (numbered from 1,
null for infrastructure attempts), and `run_family`. The manifest's optional
`family` selects `"work"` (default) or `"audition"`. `retry` means the attempt's
spec included failure context; a provider retry uses `false`. The Postgres sink
keeps the class only as `failure_class=<class>` in `notes`; JSONL keeps all new
fields.

State version 2 retains total `attempts` and adds `model_attempts`,
`infra_retries`, `end_reason`, `wait_reason`, `wait_s`, and `wait_until` (ISO time).
The summary displays model attempts and any infrastructure retries. Steering
observations retain total `attempt` and add `model_attempt`.

## Model performance log

### Model identity taxonomy

The scoreboard keeps the trained model, its lab, the invoking harness, the access plan, and any explicit reasoning effort as separate fields. Reserved test names never render, and historical rows without a stamped model are quarantined instead of being credited to an engine default. Models with a declared canonical access route are enforced at lint and run time — a manifest that reaches a model through a non-sanctioned harness/slug is refused unless you pass `--allow-noncanonical-route`, and historical rows from such routes display as `misrouted` and are never ranked. See the normative [model identity taxonomy](docs/TAXONOMY.md).

Every task attempt is logged **automatically and locally** to `~/.ringer/runs.jsonl` — no setup, no account, nothing leaves your machine. Each row carries the per-attempt verdict straight from the EXECUTED check, plus duration, tokens, the resolved `model`, the task's `task_type` (if the manifest set one), and the `retry` number.

Attempt rows include `cost_usd`, summed from the first capture group of every engine `cost_regex` match, or `null` when cost is unknown. For engines that report tokens per step, such as OpenCode, set `token_aggregate = "sum"` to add every token match within the attempt; the default `"last"` preserves the last reported token count.

Read it with:

```bash
./ringer.py models          # per-(model, task_type) scoreboard across the local log
```

The scoreboard reports, per model and task_type: tasks, attempts, `pass_rate`, `first_try_pass_rate`, median duration and token count, and `last_seen`. The signal for routing is `first_try_pass_rate` — the share of tasks that passed on attempt 1 without a retry; `pass_rate` is the rescued rate after Ringer's single retry, so the gap between the two is the cost of the retry lane. Slice the log with `--log` (a different JSONL), `--task-type`, `--model`, `--engine`, `--since`, or `--json` for piping elsewhere.

Rates count model evidence only: a `PASS` or an attempt with `failure_class = "model"` (legacy rows without a failure class retain their previous behavior). Infrastructure failures do not consume a model attempt or reduce these rates. Each model's detail shows counts such as `rate_limited ×3, provider_error ×1`; the CLI prints them below the tables. Models with only infrastructure failures appear separately as “no model evidence yet.”

Run families keep real work and auditions separate. `models --family work` is the default; use `models --family audition` for auditions or `models --family all` to show both. Audition evidence does not promote a model's work tier. The registry at `registry/model-identity.toml` supports `slug_aliases = ["<engine>:<slug>", ...]` on a model entry to combine spelling variants under the same canonical model identity and evidence counts.

History from before the `model` / `task_type` / `retry` columns existed can be seeded in one pass:

```bash
./scripts/backfill_model_log.py \
  --log ~/.ringer/runs.jsonl \
  --runs-dir ~/.ringer/runs \
  --mapping mapping.json
```

The `--mapping` file joins old log rows to a `task_type`. Each line uses one of three key forms, applied in order:

- `run_id:task_key` — names one task in one run (most specific).
- `run_id` — names every task in that run.
- `name:prefix` — names every task whose key begins with `prefix`, across all runs (least specific, the usual way to cover a whole kit's keys).

Rows that match nothing keep their old `task_type` (empty); rows whose run-state JSON can't be found keep their old `model`.

`docs/MODEL-NOTES.md` is where the human-readable judgment lives on top of these numbers — the scoreboard tells you the pass rates; the notes tell you why a model shines or chokes on a given task shape.

This fork requires evidence citations on new or edited dated notes. Before committing, run `./ringer.py notes check --base upstream/main --log ~/.ringer/runs.jsonl`: it checks each citation against a model-evidence attempt and the model heading. Omit `--log` to check citation format and heading only; use `--notes-file PATH` for another notes file. See the [citation format and evidence rules](docs/MODEL-NOTES.md).

### Evidence-based routing

The scoreboard only knows models you've already run. To reason about models you *haven't* tried yet, Ringer keeps a local snapshot of the OpenRouter catalog and a change log alongside the runs log:

```bash
./ringer.py catalog                  # fetch/refresh ~/.ringer/openrouter-catalog.json
```

| Flag | What it does |
|---|---|
| `--refresh` | Force a re-fetch even if the snapshot is fresh |
| `--source URL_OR_PATH` | Pull from a non-default URL or local file instead of the live OpenRouter API |
| `--file PATH` | Read a catalog document you already have on disk, no network |
| `--free` | Filter to models with a $0 price — promo models included |
| `--changes` | Print the recorded add/remove/price_change/went_free/went_paid events from `.changes.jsonl` |
| `--json` | Emit the snapshot (or, with `--changes`, the event log) as JSON for piping |

The snapshot lives at `~/.ringer/openrouter-catalog.json`; the change log sits beside it as `~/.ringer/openrouter-catalog.changes.jsonl`, appending one row per added, removed, price-changed, went-free, or went-paid event between snapshots. Free promos get their own call-out (`went_free`) because a temporarily-free model is a zero-cost experiment — the cheapest way to audition a new model is to catch it while someone else is paying for it.

Catalog fetches are throttled to once per 24 hours. A `run` triggers that refresh in the background on its way up; it never blocks or fails a run — if the fetch is slow or the network is down, Ringer carries on with the snapshot it has. The throttle and the auto-refresh-on-run are both documented in `./ringer.py run --help` and can be turned off there.

Once you have a catalog and a log, `models --explore` joins them into a routing recommendation:

```bash
./ringer.py models --explore                 # tiers across all task types
./ringer.py models --explore --task-type docs # tiers for one task shape
```

`--explore` skips catalog candidates without tool support and models whose latest attempt within the past seven days was blocked by provider policy (`failure_class = "provider_policy"`).

Models with local evidence are sorted into tiers:

- **proven** — 3+ tasks of this `task_type` logged, with `first_try_pass_rate >= 0.67`. The lane you trust with heavy work.
- **probation** — some attempts logged but not enough volume or not enough first-try passes. Use it; don't lean on it.
- **untested** — nothing in the log yet. Pulled from the catalog: text→text, 32k+ context window, up to 10 candidates, FREE models first then cheapest. These are your audition queue.

The promotion ladder is the point. A model enters as **untested**. You spend a small slice of suitable runs — about one task per run — auditioning cheap or free candidates on small, low-stakes work where the executed check is strong and the single retry absorbs the failure: docs sweeps, mechanical edits, persona reviews. While evidence accumulates the model sits on **probation**. At 3+ tasks with `first_try_pass_rate >= 0.67` it's **proven** for that task type and earns a lane on the heavy work. The recommendation flow is the same one this ladder implies: exploit proven models for the load-bearing tasks, and keep spending that small slice auditioning untested candidates so the bench refills itself.

The per-user philosophy, stated plainly: every user's workload is different, so the scoreboard learns what works for *your* tasks on *your* machine. A model that's proven in someone else's log is untested in yours until you've run it. The numbers are not portable between users, and the routing recommendations get personal as the log grows — which is exactly why the catalog and the change log stay local and the explore tiers are computed from your own `runs.jsonl`, not from anyone's aggregate.

## Auditions

`ringer.py audition` runs the bundled repair, implementation, and review tasks
against tool-capable OpenRouter text models. It favors models with no audition
evidence, then those with fewer audition rows, then cheaper models. Each model
gets every task whose task type has no prior audition row for that model.
Recent provider-policy blocks are excluded. Auditions record the `audition`
run family and **never set work tiers**.

Give auditions a dedicated OpenRouter credential file and a weekly budget:

```toml
[audition]
weekly_budget_usd = 5.0
credential_file = "~/.config/ringer/audition.key"
max_models = 5
concurrency = 2
engine = "opencode"
token_estimate = 40000
check_timeout_s = 120
# set_dir = "/absolute/path/to/ringer/templates/audition"
```

Store only the key in `credential_file`, restrict its permissions (`chmod 600`),
and use the sandboxed OpenCode engine. The default `set_dir` is the bundled
`templates/audition` directory. Its fixtures are copied into fresh task
workspaces, while the worker sandbox hides the set's checks and references.
Checks run with the resolved Python interpreter through the offline Linux
check sandbox (requires bwrap). `check_timeout_s` bounds each check; tasks get
one attempt, including provider failures. Active auditions appear in Ringside.
The command temporarily merges the credential into `OPENCODE_CONFIG_CONTENT`
and appends the set directory to `RINGER_SANDBOX_HIDE`.

```sh
./ringer.py audition --dry-run
./ringer.py audition --max-models 2
# Use an existing snapshot without a catalog refresh:
./ringer.py audition --dry-run --catalog-file ~/.ringer/openrouter-catalog.json --no-refresh
```

By default the command refreshes the catalog synchronously, falling back to the
snapshot if refresh fails. Dry runs print `PLAN <task_key> <model> est=$<x>`,
`SKIP <task_key> budget`, and total estimates without running workers or writing
spend. The estimate uses the model's median earlier audition cost when available;
otherwise it prices the task's `token_estimate` (falling back to the config) at
85% input and 15% output tokens. Free models have zero estimated cost.

The ledger is `$RINGER_HOME/audition-spend.jsonl` (`~/.ringer` by default), with
weeks defined by local-time ISO weeks. Completed batches record actual costs,
or their estimates if the provider reports no cost. Actual costs can exceed
estimates; the runner checks the remaining budget between batches and stops
starting batches after a quota-exhausted result. A nonblocking lock prevents
overlapping auditions. Results are written to the configured local eval JSONL
journal, including when ordinary runs use Postgres. The summary separates
model verdicts from infrastructure failures and shows weekly spend and budget left.

To schedule a Sunday run, create `~/.config/systemd/user/ringer-audition.service`
with absolute paths to your Python 3.12+ interpreter, checkout, and config:

```ini
[Unit]
Description=Weekly Ringer model auditions

[Service]
Type=oneshot
Environment=RINGER_NO_SELF_UPDATE=1
ExecStart=/absolute/path/to/python3 /absolute/path/to/ringer/ringer.py --config %h/.config/ringer/config.toml audition
```

Create `~/.config/systemd/user/ringer-audition.timer`:

```ini
[Unit]
Description=Run Ringer auditions on Sunday

[Timer]
OnCalendar=Sun 03:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable it with `systemctl --user daemon-reload` and
`systemctl --user enable --now ringer-audition.timer`. `Persistent=true` catches
up a missed run when the user timer becomes active again.

## Steering profiles

Ringer can optionally load per-model steering profiles, prepend applicable worker rules to both first-attempt and retry prompts, print driver guidance for the orchestrator, and collect one local observation row per attempt. The feature is fail-open: missing or malformed steering data never blocks a run. Setup, the profile contract, and the observation schema are documented in [`docs/STEERING.md`](docs/STEERING.md).

## Hard-won invariants

Four rules are baked into every worker invocation. They all cost us real debugging hours; you get them for free:

1. **stdin is always closed** (`< /dev/null`) — headless CLI agents hang forever waiting on a TTY that isn't there.
2. **Sandbox mode is always explicit** — default sandboxes silently resolve to read-only in temp directories and block every artifact write.
3. **Verification executes the artifact** — an agent's own "done" is not evidence. Exit codes are.
4. **Raw output only** — logs and eval rows carry verbatim worker output, never a summary. Anything that needs judgment reads the raw data.

## Contributors

Every community PR that lands in main is credited here — that's a project rule, enforced by a test. Thank you:

- [@Fiddlehead-MB](https://github.com/Fiddlehead-MB) (Melinda Byerley) — exact-byte demo checks, explicit newline instructions, and regression coverage (#101)
- [@oceanonline](https://github.com/oceanonline) — portable `python3` in template checks + lint quickstart path fix (#24)
- [@davekopecek](https://github.com/davekopecek) (Dave Kopecek) — committed the design-reference fixture so the design-token guard runs on every machine (#30)
- [@snapsynapse](https://github.com/snapsynapse) (Sam Rogers) — graceful shutdown on SIGINT/SIGTERM with worker-tree cleanup and finished state, plus the 14-test end-to-end CLI regression suite (#4)
- [@mlava](https://github.com/mlava) (Mark Lavercombe) — named setup failures across every diagnostic surface (#37), `run --baseline`, the no-workers check preflight (#38), guidance on check-writing failure modes (#57), early warnings for missing worker commands (#59), and preserving fix-swarm patches across retries (#56)

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the philosophy and what gets a PR merged fast. The short version: small and scoped, rebased on current main, every claim backed by an executed test. Authorship is always preserved — where a maintainer pushes a mechanical fix to your branch, you remain the commit author.

## License

[PolyForm Shield 1.0.0](LICENSE.md) — free to use, modify, and share, including inside your own commercial work. The one thing you can't do is offer Ringer or Ringside (or a derivative that competes with them) as a product or service of your own. Commercial rights to the tool itself belong to Nate Jones Media LLC.

## Requirements

- Python 3.12+ (stdlib only; `psycopg` needed only for the optional Postgres eval backend)
  - **Changed:** the supported floor moved from 3.11 to 3.12. CI has only ever run 3.12, so 3.11 was a promise nothing enforced — the honest fix is to state the version we actually test. Today's code still happens to run on 3.11; that is no longer guaranteed, and 3.11 breakage won't be treated as a bug.
- At least one agent CLI (Codex works out of the box)
- Rust toolchain, only if you're building Ringside from source

![Between rounds](docs/between-rounds.png)

---

Built by [Nate Jones](https://natejones.com) and maintained by [LEJ](https://limitededitionjonathan.com) — a Claude orchestrator wrote the specs and reviewed the diffs, Codex swarms wrote the implementation, and this repo's own eval table caught its first three bugs. The tool is its own proof of concept.
