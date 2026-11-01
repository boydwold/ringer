# Mac model notes, saved 2026-11-01 (not yet cited)

These 109 dated notes were written on the Mac copy of Ringer and were never
committed. On 2026-10-08, `main` reset `docs/MODEL-NOTES.md` (commit
`500fefe`) and started to require an evidence citation on every new note
(commit `8ceea1a`, `./ringer.py notes check`). These notes have no
citations, so they are kept here word for word instead.

They are not evidence. Two client names were removed before commit; the rest is unchanged. To move a note into `docs/MODEL-NOTES.md`, find its
attempt in `~/.ringer/runs.jsonl`, add the `[evidence: ...]` citation, and
run `./ringer.py notes check --base upstream/main --log ~/.ringer/runs.jsonl`.

Each block shows the heading it sat under and its line numbers in the Mac
file (`docs/MODEL-NOTES.md` at commit `5a5a0f6`, the pre-rebase commit).

<!-- from Mac MODEL-NOTES.md lines 16-19, under: ## codex (GPT-5-class, own harness) -->
## codex (GPT-5-class, own harness) (Mac addition)

- 2026-09-26 — gpt-6-astra, watcher cloud reads: initial 254-test pass still rejected ordinary data and inherited ambient TLS key logging. Independent review identified all three gaps. Correction retained 33 old-source failures; 330 final checks passed per native host and final review accepted the interface. Keep valid-input controls beside refusal tests and inspect standard-library environment side effects.

- 2026-09-26 — gpt-6-astra, verification source review and correction: full review found a cross-collection stale-profile false pass. A focused three-file correction passed 202 checks, then 795 native checks per host. Focused independent review accepted it. The original outer invocation omitted its required phase and failed before tests; preserve that wrapper failure separately from worker test results.

<!-- from Mac MODEL-NOTES.md lines 103-103, under: ## glm-5.2 via opencode (`openrouter/z-ai/glm-5.2`) -->
## glm-5.2 via opencode (`openrouter/z-ai/glm-5.2`) (Mac addition)
- 2026-08-28 code-feature (intake INT-128, test-author lane, shared-checkout mode): FAIL ×2 but NOT a model failure — `opencode-sandboxed.sh` confines writes to the task dir, so the worker wrote correct-looking test files under `<taskdir>/frontend/...` and the stub-first check saw 0 tests; attempt 2 hit the same wall. Route opencode repo-edit lanes through worktrees mode only (INT-157 pattern) or use codex with writable_roots. Don't count these two against GLM's first-try rate.

<!-- from Mac MODEL-NOTES.md lines 483-484, under: ## gpt-5.6-sol (codex) -->
## gpt-5.6-sol (codex) (Mac addition)
- 2026-09-25 code-feature (ai-harness historical regression evidence), GPT-5.6 Sol medium: first-attempt PASS, 97471 tokens, 329.6 seconds. Six expected assertion failures and six controls; all 41 inherited tests still pass. Stale-source proof covers the absence of a final-source gate, not a promise made by the round-limit function.
- 2026-09-25 code-feature (ai-harness legacy verification staging), GPT-5.6 Sol medium: first-attempt PASS, 147397 tokens, 598.7 seconds. Preserved 64 execution inputs and 10 installed sources; 41 legacy tests passed. Raw output retained an initial AST-normalizer error before correction. Characterization preserves known defects; it does not accept them.

<!-- from Mac MODEL-NOTES.md lines 541-541, under: ## opencode (harness note, any model) -->
## opencode (harness note, any model) (Mac addition)
- 2026-08-28 (code-review, intake PR #746 round 2, blast-area lane): GLM 5.2 was the slowest lane by far (still running after both codex lanes finished and the review was posted) and produced ONE high-confidence finding that did not reproduce. It claimed the round-2 basis fix silently changed behaviour for another loan-statement import path, rated `Confidence: high`, reasoned entirely from reading the resolution chain. Testing every fixture in `tests/test_rollover_liq_webprint.py` showed no period row carrying `loan_id` without `contract_id` and no per-loan `accrual_basis` cell to index, so the map is empty and resolution is identical either way. Its other work was genuinely good — it correctly cleared the catalog/crosswalk question, the ADR consistency question, and confirmed the AGENTS.md wording matches the code. Lesson: on THIS model, treat a code-reading inference rated high-confidence as a hypothesis to execute, not a finding; its verified claims (ones with a command behind them) held up fine. It also breached a read-only boundary — the spec said never install anything in the source repo, and it ran `uv pip install -e .`, briefly repointing an editable install (uv re-synced it, no harm). Next time put the prohibition in the CHECK, not only the spec.

<!-- from Mac MODEL-NOTES.md lines 689-691, under: ## GPT-5.6 Sol -->
## GPT-5.6 Sol (Mac addition)
- 2026-09-25 code-review/probe (ai-harness): watcher plan review passed its diagnostic check on attempt 1, 322,002 tokens, 621 seconds, with two confirmed planning gaps. The Mac isolation investigator timed out at 720 seconds after useful controls but before its final checker. Repeated untracked-file diffs expanded raw logs. A separate deterministic baseline completed OS controls and native acceptance without another model worker. Keep bounded diagnostic checks small and require the checker early; these figures do not establish a total-job cost saving.
- 2026-09-25 probe (ai-harness memory sync, medium): first-attempt PASS, 76,982 tokens, 318 seconds, 15 synthetic cases. The command traces reproduced, but the report recommended indexing only after remote sync succeeds. Independent review did not accept that recommendation because local indexing can support offline work. Treat policy recommendations separately from executed observations.
- 2026-08-31 code-review (intake PR #742, two lanes at reasoning_effort=high): the mutation lane is the pattern to reuse — 6 real mutations, each with raw pytest output tee'd to a log, plus a base-src/head-src pair. It routed around a sandbox block on `git checkout -- <path>` (index.lock, operation not permitted) by applying exact reverse patches, and said so in Assumptions rather than silently skipping. The correctness lane over-ranked two findings: a "period lost" P1 where no figure was actually lost, and a P0 replay defect that base reproduces identically. Both were real observations with wrong severity — treat its priorities as a hypothesis and re-run the base comparison yourself.

<!-- from Mac MODEL-NOTES.md lines 693-694, under: ## GPT-5.6 Sol -->
## GPT-5.6 Sol (Mac addition)
- 2026-08-28 code-review (intake PR #745, test-integrity lane, frontend Jest). `--add-dir <sandbox>` in `engine_args` is the clean way to give a codex lane a mutable worktree outside its taskdir — no config-key guessing, and the header prints the extra writable root so you can confirm it took. 7 mutations, 6 red, all reverted, sandbox left clean; the one green was a real unpinned claim and I reproduced it by hand. Two setup notes for a React repo: symlink `node_modules` from an installed checkout and tell the worker to call `./node_modules/.bin/react-app-rewired` directly, because `pnpm test` refuses a symlinked modules dir (ERR_PNPM_UNSAFE_MODULES_DIR) and would burn the lane on a reinstall.
- 2026-08-28 code-review (intake PR #745, correctness lane) and GLM 5.2 (blast-area lane) BOTH rated the same hardcoded frontend allow-list a P1 silent refusal at high confidence. Neither checked the server registry, where the only no-param actions were exactly the allow-listed three, so it could refuse nothing. Agreement between two lanes on different models is not verification — they shared the same missing lookup. Reproduce a P1 before it reaches a review comment.

<!-- from Mac MODEL-NOTES.md lines 724-724, under: ## GLM 5.2 (continued) -->
## GLM 5.2 (continued) (Mac addition)
- 2026-08-31 code-review (intake PR #742 blast-radius lane, worktree-isolated, ran the full 4207-test suite): best lane of the three. Traced the minted key through projection/catalog/delivery and proved it is never emitted in the delivered JSON, and that re-delivery of stored approvals is byte-identical — both load-bearing for the verdict, neither asked for by name. Corrected the PR author's test count (799+2xfail for the named files, not 1006) instead of repeating it, and correctly labelled two flipped tests as intended re-pinnings. One first-try pass, 138k tokens, 17m. Prefer it for wide read-only tracing lanes.

<!-- from Mac MODEL-NOTES.md lines 744-972, under: ## DeepSeek V4 Flash (`openrouter/deepseek/deepseek-v4-flash`) -->
## DeepSeek V4 Flash (`openrouter/deepseek/deepseek-v4-flash`) (Mac addition)

- 2026-08-29 code-feature (feature-loop build, loop_gate modules, stdlib TDD from a plan with tests written out): GLM 5.2 first-try PASS on the ledger lane (2 tests, 67k tokens). Codex ×4 all produced green modules first try; their check FAILs were my check calling a python without pytest — not a model failure. Lesson: pin the pytest path in check scripts.

## Process lessons (2026-09-15, memory-audit-fixes: 3 runs, 9 tasks)

- **OpenRouter workspace guardrails block every `:free` model.** `openrouter/nvidia/nemotron-3-super-120b-a12b:free` failed both attempts in 3 s (404, "free-model-training"/ZDR policy). This is the same block recorded 2026-08-27. Do not audition a `:free` slug in this workspace until the OpenRouter privacy settings change. Cheap paid explorers (DeepSeek V4 Flash, GLM 5.2) are the exploration lane.
- **Two OpenCode lanes started in the same second can die with "database is locked".** v3 (DeepSeek V4 Flash) attempt 1 exited in the harness before the model ran; the retry worked. Harness fault, not a model fault. If a run has 2+ opencode tasks, expect one such retry or stagger the start.
- **My check trap, twice: `pyproject` `addopts = "-q"` plus a `-q` in the command hides the `N passed`/`N failed` summary line.** Two of my checks grepped for that line and failed honest work. Check scripts should accept pytest's `FAILED tests/...` lines, or run without `-q`.
- **A verifier lane caught a wrong finding from a scout lane.** GLM 5.2's round-0 scout counted the intake CI jobs as ten (it counted the `pull_request`/`push` triggers). My round-1 check counted nine from `ci.yaml`, and the GLM round-2 verifier confirmed nine. The memory file was correct; a fix on the scout's word alone would have made it wrong.
- **The `ruff format --check` gate forced a reformat of an unrelated file.** The repo's test file was not formatted to its own `line-length = 100`, so the worker's minimal fix carried 100 lines of format-only hunks. Run `ruff format --check` on the baseline first; if the baseline fails, drop the gate or scope it to the changed hunks.

## GLM 5.2 (continued)
- 2026-09-15 docs (t1-memory-edits: three memory files staged, gh evidence for five PRs, hook lines under 260 chars): first-try PASS, 263 s. Read the check script first and satisfied every assertion. No invented PR numbers.
- 2026-09-15 code-review (v1-memory-verify, read-only verifier with gh + chezmoi diff + a Python check): first-try PASS, 105 s, five sections all with quoted evidence. Corrected the round-0 scout's CI count.
- 2026-09-15 research (scout-memory-state, round 0): substance good (24 k chars, every item with commands quoted) but it miscounted CI jobs (see process lessons). The recorded FAIL was my report check's heading parser; fixed the same day.

## codex (continued)
- 2026-09-15 code-feature (t5-memory-read-hook, medium effort): first-try PASS in 69 s. 30-line bash hook, exact settings.json diff, all six synthetic stdin cases. Wrote its own notes with the check output quoted.
- 2026-09-15 code-fix (t3-scanner-file-hardening, medium, worktrees mode): first-try PASS in 106 s. Minimal try/except, parametrized test, stash-based must-fail proof recorded in fix-summary.md.
- 2026-09-15 code-review (v2-hook-verify, medium): first-try PASS in 99 s. Wrote its own payloads (including a path with a quote and spaces) and read the live telemetry log.
- 2026-09-15 research (scout-mycelium-crash, round 0): substance good; the recorded FAIL was my report check's heading parser.

## DeepSeek V4 Flash (continued)
- 2026-09-15 code-review (v3-mycelium-verify, mutation test in a scratch copy + patch review): substance PASS on attempt 2 (attempt 1 was the OpenCode "database is locked" harness fault). Ran the mutation test correctly and noted that the markdown variant cannot fail because that branch had its own guard. Recorded FAIL is my check's fault: it demanded a fenced block in a prose-only section and the hidden pytest count line. Still a good second verifier lane.

## gpt-5.6-sol / gpt-6-astra / GLM-5.2 (INT-1071 grouping build, 2026-09-24)
- code-feature (gpt-5.6-sol, codex, worktrees): the wave-1 attempts were lost to my broken check, not the model. Waves 2–4 passed on attempt 1 or 2.
- code-fix (gpt-5.6-sol): fix-records and fix-typechange passed first-try; fix-events took 2 attempts. The fail-first check (swap the owned source to HEAD bytes and require N failures) worked well.
- code-review: gpt-5.6-sol (correctness, with mutation proof) and gpt-6-astra (test integrity) passed first-try in both rounds. GLM-5.2 (opencode, blast area) passed first-try in round 1 and took 2 attempts in round 2. The round-2 review found 4 real blockers that round 1 missed, so a second review round earns its cost.

- 2026-09-25 probe (ai-harness/Mycelium), GPT-5.6 Sol medium: six synthetic cases completed on attempt 1, 94,564 tokens, 328.6s. The worker corrected one wrong module path. A separate deterministic check reproduced all three reported gaps. Keep synthetic stores and named source hashes; do not infer Linux or broad search quality from this result.

- 2026-09-25 code-fix (execution evidence), GPT-5.6 Sol high: 275,223 tokens, 1,425.8s, first-attempt FAIL. Both tool corrections passed351 Mac tests, but the external check rejected a private Mac artifact dependency that would skip Linux regression coverage. Require portable generated test data in the initial check. A one-file follow-up uses medium reasoning. No claim of total token savings.

- 2026-09-25 code-fix (execution test portability), GPT-5.6 Sol medium: first-attempt PASS, 178,083 tokens, 881.5s. One test module now generates portable evidence;351 Mac tests passed with zero skips and39 protected hashes matched. An initial full run lacked loopback permission and was repeated with permission; both logs remain. Native checks remain separate.

- 2026-09-25 probe (Mycelium message fetch), GPT-5.6 Sol medium: first-attempt PASS, 65,736 tokens, 214.5s. The synthetic MCP case exposed backing-database text instead of the selected burst. A separate deterministic check confirmed it. No live Messages or Contacts access.

- 2026-09-25 probe (Linux test boundary), GPT-5.6 Sol medium: first-attempt PASS, 157,048 tokens, 659.3s. The worker reproduced interpreter ownership refusal under Bubblewrap and passed14 Landlock controls plus synthetic profile capture. One strict check first rejected a ctypes warning; the corrected layout passed. The executed checker repeats controls, while diagnosis details are supported by retained raw worker commands. No production changes or full native acceptance in this diagnostic.

- 2026-09-25 probe (watcher source assessment), GPT-5.6 Sol medium: first-attempt PASS,130,910 tokens,461.3s. Three installed sources matched inventory. The worker recorded tests by reference; an independent deterministic follow-up retained the two test/evidence files and checked nine Git history references. Scheduler ownership and separate installed client variants remain unresolved. A source copy does not accept inherited behavior.

- 2026-09-25 code-review (coordination plan), GPT-5.6 Sol medium: diagnostic PASS on attempt 1, 113,453 tokens, 318.5s. Actual verdict was not ready. Six executed state-model traces supported four design gaps. These models do not test product implementation. Require a separate follow-up after architecture changes.

- 2026-09-25 code-feature (verification validation), GPT-5.6 Sol medium: first-attempt check PASS, 175,133 tokens, 773.4s, 82 tests. Main review found relative PATH resolution and parser-error gaps. Task acceptance remains open pending executed regressions and correction. A passing worker suite does not replace review.

- 2026-09-25 probe (Codex persisted hook trust), GPT-5.6 Sol medium: TIMEOUT at 1200.1s; tokens unavailable. Final raw native cases succeeded, but the preserved checker refused changed live configuration. The writer is unknown. Keep the run unaccepted; reuse the reviewed driver in a fresh deterministic baseline instead of another model retry.

- 2026-09-25 code-fix (verification validation refinement), GPT-5.6 Sol medium: first-attempt PASS, 164,948 tokens, 573.1s. Ninety tests passed. Executed red cases covered wrong PATH identity, malformed input, nonregular files and bounded reads. One initial nesting assertion was too specific and remains preserved. Main review accepted task2.1 only; complete verification remains open.

- 2026-09-25 code-review (coordination journal), GPT-5.6 Sol medium: first-attempt diagnostic PASS, 98,959 tokens, 335.7s. Actual verdict remained not ready, with terminal-refusal replay and joint-restore gaps. Thirteen design traces are not product tests.

- 2026-09-25 code-review (coordination recovery rules), GPT-5.6 Sol medium: first-attempt PASS, 70,010 tokens, 272.5s. No blocking findings remain under the declared recovery boundary. Six design traces and three negative controls support the rule review; implementation and production recovery remain unverified. Bound a follow-up to changed rules to avoid repeating the entire investigation.

- 2026-09-25 deterministic native audit (no model): fresh Mac Codex hook-trust records preserved live configuration, but the old checker required handler completion order to equal registration order. A separate audit validated configured order, both handlers, stronger denial, raw identity, UI trust and negative controls. Keep original failure evidence; distinguish concurrent completion order from registration order.

- 2026-09-25 code-feature (bounded verification process), GPT-5.6 Sol medium: first-attempt FAIL, 146,299 tokens, 740.6s. The private test suite passed120tests, but the final checker queried pytest metadata in the bootstrap interpreter and raised PackageNotFoundError. Main review also identified process-error and cleanup hypotheses for separate reproduction. Always execute the exact manifest check command before reporting success; private-suite success does not override the final task verdict.

- 2026-09-25 code-feature (coordination schemas), GPT-5.6 Sol medium: first-attempt checker PASS, 147,324 tokens, 830.7s, 74 tests. Main review found unknown-key diagnostic exposure, unchecked response states, and unchecked typed serialization. Task1.2 remains unaccepted pending targeted regression and correction. Test public encoders as well as decoders; private content can appear in keys.

- 2026-09-25 probe (watcher historical regressions), GPT-5.6 Sol medium: first-attempt PASS, 144,342 tokens, 527.3s. Ten intended failures and ten controls reproduced from hash-bound AST nodes. Main review checked actual assertion failures and raw hashes. Accepted historical task1.3 only; this does not test corrected provider endpoints, live mutations, durable delivery, or portability.

- 2026-09-25 code-fix (process error handling), GPT-5.6 Sol medium: checker PASS, 155,359 tokens, 739.5s, 127 tests. Main review required two more input/ownership cases. Preserve passing intermediate evidence without claiming final acceptance.
- 2026-09-25 infrastructure: three correction workers and the alternate built-in route failed with service401 before source edits. Treat this as service failure, not model reasoning evidence. Later Ringer runs resumed after the runtime restart.
- 2026-09-25 code-fix (process resume), GPT-5.6 Sol medium: FAIL,79,587tokens,71.4s. The worker stopped for design approval despite standing implementation authority. State approved design and APPLY mode at the start of follow-up specifications.
- 2026-09-25 code-fix (coordination schema refinement), GPT-5.6 Sol medium: first-attempt PASS,177,120tokens,551.5s,108tests. Main review accepted fixed diagnostics, response states and typed encoding. Correlation-lifetime concern was refuted by existing stable logical identity; preserve refutations as evidence.
- 2026-09-25 code-feature (source manifests), GPT-5.6 Sol medium: first-attempt checker PASS,130,518tokens,615.4s,136tests including46source tests. Main review required executable-bit, encoding and input-bound checks before acceptance. One suggested chmod example changed read bits only; the correction worker correctly rejected that example.
- 2026-09-25 code-fix (process final correction), GPT-5.6 Sol medium: first-attempt PASS,95,848tokens,402.0s,131tests. Two new regressions failed before correction. Main review checked cleanup code, test assertions, structured verdict and exact hashes; task2.3 accepted. Linux and complete change acceptance remain separate.

- 2026-09-25 code-fix (source manifests), GPT-5.6 Sol medium: PASS,142,333tokens,594.1s,151tests. Main audit then reproduced four typed-input and pre-conversion bound failures. The checker also hashed owned files only after tests. Require before/after identities and invalid element types before set/sort operations.
- 2026-09-25 code-fix (source final boundaries), GPT-5.6 Sol medium: PASS,146,502tokens,511.8s,160tests. Seven red assertions and two controls preceded correction. Main review accepted task3.1 after code, checker and exact raw/source hashes matched. A separate deterministic Linux check passed70source tests.
- 2026-09-25 code-feature (collection adapters), GPT-5.6 Sol medium: PASS,181,012tokens,937.2s,154tests. Main audit reproduced wrong venv invocation, Boolean schema acceptance, malformed-element and huge-number errors, valid Jest single-test rejection, and actual test-body execution through an operator -- separator. Keep task2.2 unaccepted pending correction; test real runnable-only controls and pre-dispatch flags.
- 2026-09-25 probe (Linux process validation), GPT-5.6 Sol medium: TIMEOUT,910.7s, token total unavailable. The driver adopted descendants without timely reaping; three process assertions failed. A separate deterministic run with ordinary Linux handling passed131tests on exact unchanged source. Record generated Python bytecode as explicit exclusions instead of treating it as source mutation. Preserve the failed driver and test evidence.
- 2026-09-25 code-feature (Ringer record adapter), GPT-5.6 Sol medium: PASS,161,322tokens,800.2s,155tests. Main review found invented pending shapes: actual live records use state live and summary null. Actual worker TIMEOUT was also unsupported. Supply observed live, queued, mixed-progress and terminal records before implementation. Main audit also reproduced unhandled huge-number and malformed-status inputs; tasks4.1/4.2 remain open.

- 2026-09-25 — GPT-5.6 Sol medium, code-fix, `verification-evidence-20260926T035041Z-p60193`: PASS first attempt, 212,464 tokens, 953.0 seconds. The checker passes 196 tests and preserves 23 earlier-source assertion failures. Main review accepts the virtual-environment invocation correction. Collection remains open for pre-conversion length limits and portable test prerequisite paths; the worker fixed the six assigned failures but did not establish Linux acceptance.

- 2026-09-25 — GPT-5.6 Sol medium, code-feature, `verification-evidence-20260926T035925Z-p81222`: PASS first attempt, 197,241 tokens, 998.5 seconds. Store checks pass 46 tests. The worker captured owned source hashes only after tests despite the requested before/after check. Main retained that limitation and ran separate deterministic Mac and Linux acceptance: 46 tests per host, unchanged source. Task 3.2 accepted; storage provides no verification authority.

- 2026-09-25 — GPT-5.6 Sol medium, code-fix, `verification-evidence-20260926T041113Z-p4194`: PASS first attempt, 131,723 tokens, 481.9 seconds. Collection bounds and test portability pass 204 tests, with two preserved red assertions. Main then made the validation fixture interpreter portable and executed the final 204 tests on both hosts. Initial independent Mac environment omitted LANG/private Python PATH and failed four tests; separate corrected environment passes, unchanged product source. Task 2.2 accepted.
- 2026-09-25 — GPT-5.6 Sol medium, code-fix, `verification-evidence-20260926T040933Z-p99968`: PASS first attempt, 139,227 tokens, 529.1 seconds; 87 reader tests. Main independently reproduced rejection of retrying/verifying states that retain a prior check timeout. Tasks 4.1/4.2 remain open. The checker also lacks built-in before/after source identity enforcement; the next focused correction requires it.

- 2026-09-25 — GPT-5.6 Sol medium, code-fix, `verification-evidence-20260926T042500Z-p28879`: PASS first attempt, 127,552 tokens, 394.8 seconds. Exact reader/wait passes 93 tests, with four old-source assertion failures. Main reviewed actual Ringer retry semantics and source/raw evidence hashes. All93 also pass on Linux. Tasks4.1/4.2 accepted.
- 2026-09-25 — GPT-5.6 Sol medium, code-feature, `verification-evidence-20260926T041756Z-p16509`: PASS first attempt, 196,066 tokens, 731.0 seconds,45 outcome tests. Independent audit found valid cleanup_failed results rejected when output_limited=true or returncode=None. A deep-JSON refusal control passed. Task3.3 remains open for focused correction.

- 2026-09-25 — GPT-5.6 Sol medium, code-fix, `verification-evidence-20260926T043249Z-p44432`: PASS first attempt, 123,985 tokens, 317.1 seconds,56 Mac outcome tests and two old-source red assertions. Main confirms the narrow cleanup-failure fix. Linux executes56 with one failure from an existing Mac-specific /private/tmp test fixture; product source refuses nonexistent workspace correctly. Test-only portability correction follows; task3.3 remains open.

- 2026-09-25 — GPT-5.6 Sol medium, code-fix, `verification-evidence-20260926T044105Z-p66119`: FAIL first attempt,69,278 tokens,184.4 seconds. Test-only workspace fix passes56 tests manually, but the checker refuses existing outputs on Ringer's repeated invocation. Exact structured check_returncode=1 is preserved. Independent deterministic Mac/Linux checks subsequently pass56 each on the same frozen source; task3.3 accepted from those new checks. Future worker checks must be rerunnable.
- 2026-09-25 — GPT-5.6 Sol medium, code-feature, watcher package-profile-foundation: PASS first attempt,185,587 tokens,686.8 seconds,52 tests. Independent review reproduces mutable data under stale profile identity, valid workspace path exclusions, impossible calendar acceptance, remote local-snapshot completion, unbounded CLI allocation and FIFO blocking. Tasks1.2/2.1 remain open; focused correction follows.

- 2026-09-25, gpt-5.6-sol medium, code-fix: `verification-evidence-20260926T043831Z-p58232` passed first attempt (177,559 tokens, 835.4 seconds). Invalid-Unicode refusal added 27 cases; 231 tests passed. Separate combined acceptance passed 496 tests on each host. Preserve early text bounds and valid Unicode controls.

- 2026-09-25, gpt-5.6-sol medium, code-fix: `watcher-correction-20260926T045206Z-p90913` passed first attempt (202,321 tokens, 741.9 seconds). Eighteen old-source failures became 89 passing foundation tests. Independent Linux acceptance passed the same final 89 tests. A last test-path edit required a new exact snapshot; wait for worker completion before final platform snapshots.

- 2026-09-25, gpt-5.6-sol medium, code-review: `verification-evidence-20260926T050812Z-p17853` passed first attempt (174,250 tokens, 615.6 seconds). Independent executable probes confirmed a contradictory Jest-suite false pass and a pytest-rootdir false refusal. Probe-authoring errors remain in earlier raw attempts. Review PASS means reproducible evidence, not defect-free source.

- 2026-09-25, gpt-5.6-sol medium, code-feature: `verification-evidence-20260926T050211Z-p7342` passed first attempt (227,083 tokens, 1073.5 seconds), 42 binding tests. Main reproduced an stdin-mode identity gap in an intermediate revision; the final worker revision independently fixed it. Independent final audit and Linux 42-case acceptance pass. Compare final hashes before requesting another correction.

- 2026-09-25, gpt-5.6-sol medium, code-review: `verification-evidence-20260926T052502Z-p50591` FAIL (131,800 tokens, 278.0 seconds). The provider flagged generated probes for possible cybersecurity risk; no review/check artifacts completed. Treat all candidate findings as unverified. Do not count this as a completed independent review or retry the blocked probe request.

- 2026-09-25, gpt-5.6-sol medium, code-fix: `verification-evidence-20260926T052101Z-p41287` passed first attempt (205,705 tokens, 754.7 seconds), 93 collection tests. Combined Mac/Linux checks passed 560 each. A later scalar-type audit still found false/0.0 accepted as integer zero; collection remains open for strict type correction.

- 2026-09-25, gpt-5.6-sol medium, code-review: `verification-evidence-20260926T053452Z-p75534` FAIL (54,280 tokens, 73.6 seconds). The source-only request prohibited all commands and thereby blocked source reads. The worker correctly reported every area incomplete. Correct the task instruction to allow named read-only file commands; do not attribute this failure to review quality.

- 2026-09-25, gpt-5.6-sol medium, code-review: `verification-evidence-20260926T054730Z-p96877` PASS (107,834 tokens, 167.7 seconds). Explicit read-only file permission enabled complete binding source inspection; no source-proven findings. This does not replace executed behavior evidence or the earlier provider-blocked probe review.

- 2026-09-25, gpt-5.6-sol medium, code-review: `memory-session-sync-20260926T055512Z-p10725` PASS (43,996 tokens, 122.1 seconds), with ready=false and five planning findings. Main confirmed full publication-range identity, explicit resume authority, staged-index ambiguity, capture/index ordering, and profile-change acceptance gaps. Revisions preserve the original verdict; literal unchanged index bytes after an authorized fast-forward was not adopted.

- 2026-09-26, gpt-5.6-sol medium, code-feature: `verification-evidence-20260926T054102Z-p86215` PASS first worker attempt (432,644 tokens, 1372.0 seconds),119 focused tests. Independent Linux integration exposed a hardcoded Mac example path; a two-line test-only configuration fix led to580 passing tests per host. A later source review reopened integration for final aggregate preflight validation and loaded declaration/manifest identity gaps. Prefer smaller implementation units and verify portable fixture inputs explicitly.

- 2026-09-26, gpt-5.6-sol medium, code-review: `verification-evidence-20260926T060911Z-p36317` PASS (92,992 tokens,171.7 seconds), two source-only findings. Main confirmed preflight has no final aggregate consumption and loaded declaration bytes are not compared with the first measured manifest. New executable regressions are required before correction acceptance; source inspection is not an executed reproduction.

- 2026-09-26, gpt-5.6-sol medium, code-fix: `verification-evidence-20260926T061511Z-p50286` passed on one worker attempt (240,932 tokens, 1160.1 seconds). It reproduced two CLI integration defects, corrected collection/final consumption and loaded-input binding, and passed 178 focused tests with 77 protected files unchanged. Retained raw runs include an assertion-reason correction and an invalid test-plan correction before passing tests. Main inspected the reproduced failures and new checks. Separate Mac integration passes 597 tests; Linux verification remains pending at this entry.

- 2026-09-26, gpt-5.6-sol medium, code-review: `launch-receipts-20260926T123903Z-p91246` passed report-structure and six-file preservation checks on one attempt (113,164 tokens, 242.8 seconds). Its planning verdict was ready=false with five blocking gaps: digest capture, exact receipt schema, replay results, durability barriers, and path policy. Main confirmed the cited source behavior. Source-only review; no runtime probes. A worker jq scope error was corrected before the final check. Preserve the distinction between checker PASS and plan readiness.

- 2026-09-26, gpt-5.6-sol medium, code-review: `launch-receipts-20260926T132407Z-p70934` passed its six-file/report check (115,124 tokens, 294.3 seconds), but retained ready=false. Five more concrete design gaps concerned nested descriptor fields, additional launch options, SQLite pathname access, HUD discovery, and conflict precedence. Main confirmed the source paths and revised the plan. The next review uses frozen source copies. No runtime implementation or behavior probes were part of either review.

- 2026-09-26, gpt-5.6-sol medium, code-review: `launch-receipts-20260926T133318Z-p89419` passed report/source checks (142,671 tokens, 289.0 seconds), with ready=false. Three blocking gaps concerned explicit namespace location, shell/Git identity immediately before later effects, and local-filesystem classification. One nonblocking finding clarified consumer fixture ownership. Main revised those points and started a targeted resolution review. No runtime behavior was executed by the reviewer.

- 2026-09-26, gpt-5.6-sol medium, code-review: `launch-receipts-20260926T134103Z-p8671` passed report/source checks (100,077 tokens, 179.9 seconds). It confirmed prior resolutions and found one remaining exact cleanup-result mapping gap. Main resolved that mapping against the existing producer and consumer fields: delay terminal PASS until cleanup, use fail/ERROR and a fixed output marker, preserve actual check evidence. Original ready=false evidence remains retained; main accepted the planning review task. Runtime acceptance remains open.

### 2026-09-26 — launch receipt foundation

GPT-5.6 Sol medium completed one code-feature attempt: 260277 tokens, 1727.6 seconds, 40 native Mac tests passed. Main found unresolved replay, record compatibility, and test isolation defects despite the passing checker. A separate source review used 131775 tokens and 413.2 seconds and returned six findings with ready=false. Retain source review and actual result-format tests as acceptance gates. The report-structure check is not code acceptance. Correction remains active.

### 2026-09-26 — receipt corrections and native acceptance

GPT-5.6 Sol medium completed the first correction in one attempt: 236426 tokens, 958.6 seconds, 54 focused Mac tests passed. The complete Mac suite passed 315 tests after test history was supplied. Native Linux exposed a btrfs device-identity assumption that Mac tests could not detect. A separate code review used 146411 tokens and found four remaining defects. A bounded storage-decision review used 48055 tokens and accepted the btrfs clarification with no findings. Keep native checks and independent malformed-input review before acceptance.

### 2026-09-26 — guarded native correction

GPT-5.6 Sol medium completed the hooks-disabled correction in one attempt: 152012 tokens and 350.5 seconds. All 62 focused Mac tests and 323 full Mac tests passed. Native Linux still found a valid-journal size assumption and two noncanonical fixture paths. A separate source review used 136230 tokens and found five more boundary defects. A 61964-token decision review accepted the bounded allowance but required an exact shared contention deadline. Passing tests remain insufficient for acceptance; keep native concurrency and malformed-state review.

- 2026-09-26: GPT-5.6 Sol, code-feature/code-review, hooks disabled. The CAP-005 late-only correction passed 52 tests but review found the full-boundary gap. A separate correction passed 67 tests in one attempt (149747 tokens, 475.7 seconds); targeted review found no remaining issue (53203 tokens, 112.7 seconds). Both hosts passed 422 combined checks. Next time specify every call boundary in the first correction brief. Counts exclude other runs and orchestrator work.

- 2026-09-26: GPT-5.6 Sol medium, code-feature, `runner-integration`: capacity error after 317521 tokens and 488.4 seconds. Partial edits are preserved; the checker failed (431 tests, 13 failure entries, 23 error entries). Do not retry the saturated model automatically. GPT-6 Sol is listed locally, but its source-only assessment launch needs specific disclosure approval after automatic review rejected the substitution. No alternate-model outcome exists yet.

- 2026-09-26: GPT-6 Sol medium, code-review: a bounded resume assessment passed exact source-citation/preservation checks in one attempt (66507 tokens, 106.8 seconds). Main confirmed the three cited integration gaps. This verifies routing and a small source review, not implementation quality.

- 2026-09-26: GPT-6 Sol medium, code-feature, runner resume: stopped at a protected capture dependency after 204944 tokens and 378.3 seconds. The outer checker had three failures and two errors across 431 tests; seven worker-sandbox port-bind errors did not recur outside that sandbox. The source-ownership stop was correct. Main assigned a separate narrow parser correction, then will resume missing integration coverage.

## GPT-6 Astra — launch receipts, 2026-09-26

- Code-feature: discovery used one attempt, 163190 tokens, and 1273.2 seconds. The outer suite ran 516 tests: all 59 new tests passed, but two existing scenarios produced eight errors. The implementation was not accepted.
- Code-review: discovery review used 77452 tokens and 125.9 seconds; final-report review used 63281 tokens and 83.4 seconds. Main confirmed four blocking findings across both reviews. Report checks passed; their planning verdicts remain ready=false.
- Keep regression checks and artifact-enabled finalization in acceptance. Hooks were disabled for each run. GPT-5.6 Sol and GPT-6 Sol capacity failures were not retried.

- Launch-receipts follow-up, 2026-09-26: correction run used 121084 tokens and 661.9 seconds; all 527 outer tests passed. Final review used 82699 tokens and 117.9 seconds with no findings. Main verified both native 550-check runs and archived the 14-task change. Earlier failures remain preserved.

- 2026-09-26, gpt-6-astra medium, code-feature: `watcher-correction-20260927T020225Z-p50025` passed one worker attempt (132406 tokens,1135.2 seconds), with 382 tests on each native host. Independent review `watcher-correction-20260927T022238Z-p96865` used 77740 tokens and 156.2 seconds and returned ready=false for existing-handle state substitution. Main reproduced directory and database replacement. Preserve native passes as test evidence, not acceptance; require object-identity checks and final review.

- 2026-09-26, gpt-6-astra medium, code-fix: `watcher-correction-20260927T022850Z-p11876` passed one attempt (211679 tokens, 932.8 seconds), with 454 Mac tests and 68 retained old-source behavior failures. Omarchy then failed 117 cases because a retained directory description returned an empty listing. Main verified that a fresh relative description sees the correct entries. The final review used 110310 tokens and 203.4 seconds, resolved F1, and found missing parent-directory fsync. Keep native filesystem checks and parent-entry durability controls.

- 2026-09-26, gpt-6-astra medium, code-fix: `watcher-correction-20260927T025234Z-p3949` passed one attempt (149326 tokens, 392.0 seconds). Final native suites pass 468 cases per host. Focused review `watcher-correction-20260927T025959Z-p32370` used 65748 tokens and 116.5 seconds, with ready=true and no findings. Fresh bounded directory scans fix the measured Linux failure; a verified parent flush resolves F2. Keep observed native behavior separate from kernel-cause speculation and power-loss claims.

- 2026-09-26, gpt-6-astra medium, code-feature: `watcher-correction-20260927T030504Z-p51211` passed one worker attempt (129172 tokens, 1025.3 seconds) and 583 Mac tests. Linux failed one unsynchronized closed-stdin test. Review `watcher-correction-20260927T032300Z-p20588` used 75221 tokens and 150.9 seconds and found cleanup interruption, prevalidation allocation, unchecked parent parsing time, and discarded synthetic child exit status. Main reproduced the cleanup defect. Require interruption inside cleanup, bounded parser work, exact child exit propagation, and native synchronization controls before acceptance.

- 2026-09-26, gpt-6-astra medium, code-review: `memory-session-sync-20260927T033050Z-p39964` passed one attempt (34934 tokens, 82.2 seconds). Final static planning review independently resolved all five earlier findings and returned ready=true. Main verified seven frozen/current input hashes and accepted task1.4 only; scanner, implementation, native compatibility and activation remain pending.

- 2026-09-26, gpt-6-astra medium, code-fix: `watcher-correction-20260927T032749Z-p32326` passed one attempt (147052 tokens, 1100.6 seconds) and 661 tests on each native host. Review `watcher-correction-20260927T034830Z-p3366` used 109538 tokens and 232.8 seconds; BR-02/BR-04/N1 resolved, BR-01/BR-03 remain. Test cleanup handlers and transitions, not only operations. Main chose to keep provider-body validation in the already bounded fixed child and remove duplicate parent body conversion; parent protocol validation stays strict.
- 2026-09-26, gpt-6-astra medium, research: `memory-session-sync-20260927T033554Z-p55566` passed one attempt (71039 tokens, 394.9 seconds), reproducing 32 legacy/scanner behaviors. Main found an assessment-probe signal-after-reap defect. Correction `memory-session-sync-20260927T034334Z-p85093` used 89975 tokens and 532.5 seconds, retained all 32 case bodies/substitutes, and passed 42 cases. Main verified 298 raw evidence files and accepted tasks1.1–1.3 assessment only. Retain identities until signaling ends; raw test passes do not accept the unchanged scanner as a publication gate.

- 2026-09-26, gpt-6-astra medium: watcher correction `watcher-correction-20260927T035754Z-p42424` used 99858 tokens and 628.7 seconds. Both hosts pass 697 tests. Review `watcher-correction-20260927T041543Z-p6691` used 112384 tokens and 245.3 seconds; BR-03 is resolved, but BR-01 still escapes through cleanup entry and final handlers. Native passes do not accept the component. Design assessment `watcher-correction-20260927T042143Z-p28510` used 72043 tokens and 210.6 seconds. It recommends complete native ownership, rather than more Python exception guards. The compiled dependency and deferred Python cancellation await the user’s architecture decision.

- 2026-09-26, gpt-6-astra medium: memory foundation `memory-session-sync-20260927T040523Z-p66019` used 152914 tokens and 1320.8 seconds. Eight retained checker attempts expose scaffold, input, source-drift, allocation, and overlapping-root failures. The final 679 tests pass on both hosts: 211 new memory cases and 468 accepted watcher controls. Independent review remains pending; documented syntax restrictions are not automatically accepted requirements.

- 2026-09-26, gpt-6-astra medium: memory review `memory-session-sync-20260927T042817Z-p43794` used 91445 tokens and 162.7 seconds. It returned ready=false despite 679 native passes per host. F1 rejects legitimate filesystem names; F2 lacks guaranteed test-thread cleanup and actual concurrent close; F3 does not require its claimed storage-limit refusal. Main confirmed all three and launched a focused correction.

- 2026-09-26, gpt-6-astra medium: capture assessment `memory-session-sync-20260927T043705Z-p67508` used 62310 tokens and 253.7 seconds. Main verified 11 frozen inputs and retained its bounded manifest/queue proposal. It exposes source/schema compatibility and measured-consistency limits; it does not implement or accept capture. Main separately observed a larger-record allocation refusal that leaves the journal API unavailable below the total byte limit. Preserve that case for the next correction rather than relying only on smaller-row tests.

- 2026-09-26, gpt-6-astra medium: memory path/test correction `memory-session-sync-20260927T043316Z-p56126` used 163077 tokens and 1055.9 seconds. Local754 passed; native Mac failed one longer-path case and Linux passed. Larger valid profiles exposed a distinct allocation/read refusal. Independent allocation review used 72268 tokens and 201.8 seconds. Do not replace demanding rows with smaller rows or infer filesystem limits from logical SQLite pages.

- 2026-09-26, gpt-6-astra medium: storage/path correction `memory-session-sync-20260927T045734Z-p25109` used 134276 tokens and 776.0 seconds. Final761 checks pass on both native hosts. Main verified exact source and retained evidence. Reads/replay no longer need insertion reserve; new-write admission has a stated conditional allocation guarantee. Independent review has not run because automatic approval review requires explicit Astra payload permission. Test counts do not establish component acceptance or a universal filesystem quota.

- 2026-09-26, gpt-6-astra medium: D7 source assessment used 65618 tokens and 175.1 seconds. Main verified eight frozen inputs and18 literal citations. It confirms Teams and automatic-sync guidance conflicts but does not establish agents-copy origin or broader external-action authority. Limit the next separate proposal to proved policies; do not import complete inherited skills.

- 2026-09-27, gpt-6-astra medium: final memory review `memory-session-sync-20260927T114253Z-p77479` used 113143 tokens and 184.4 seconds. It resolved F1–F4/N1 with no blocking source findings. Main matched the exact source to761native checks per host and accepted task2.1 only. Preserve the distinction between bounded logical state/advance reserves and an unproved universal physical-allocation quota.

- 2026-09-27, gpt-6-astra medium: native watcher ownership `watcher-correction-20260927T114257Z-p77635` used210353tokens and1739.6seconds. Final838tests pass on each separately built native host. The first full frozen check exposed missing LC_UUID despite earlier focused passes; new load-and-execute checks bind tests to produced binaries. Unicode trust-path cases also caught a narrowed byte limit. Main verified229scenario mappings and retained all failures. Independent review remains active; passing native tests do not accept a new cleanup allowance.

- 2026-09-27, gpt-6-astra medium: native ownership review `watcher-correction-20260927T121249Z-p54076` used 136207 tokens and 300.6 seconds. Five findings reject the candidate despite 838 native passes per host. Main verified all 35 review inputs. Deadline extension, descriptor reuse, numeric callbacks, missing real cleanup-failure coverage, and pipe inheritance require disposition. A test-case mapping does not prove semantic replacement.

- 2026-09-27, gpt-6-astra medium: platform assessment `watcher-correction-20260927T122724Z-p82225` used 110560 tokens and657.1seconds. The outer run failed because its checker rejected two additive decision fields; the executed probe passed. Main verified40result records and source/binary identities, retaining the failed run. Header-only search missed public macOS27 pipe2 in an included header; compile/link/call checks corrected that assumption. Injected close/EINTR models remain distinct from real OS interruption evidence.

- 2026-09-27, gpt-6-astra medium: NO-03 numeric correction `watcher-correction-20260927T123654Z-p994` used66516tokens and308.3seconds, one attempt. The isolated two-file change retained838cases and added222 numeric admission cases; old source produced112failures. Main reviewed and integrated exact files. Mac/Linux each passed1060checks. Four separate lifecycle findings remain open; do not report whole-component acceptance from this scoped correction.

- 2026-09-27, gpt-6-astra medium: collection integration assessment passed in one attempt with94062tokens and338.6seconds. Main verified10frozen inputs and45literal citations. It identified retry reservation and permanently partial retention gaps. Main retained the plan as provisional; backward-clock operator recovery and pruning/migration policies are not accepted merely because the report labels them routine.


### 2026-09-27 [10:35] — Watcher runtime and independent review

GPT-6 Astra medium delivered the runtime correction in one attempt: 344896 tokens, 1846.6 seconds. Hooks were disabled.
Main verified 1084 checks per host and 640 retained evidence files from 13 failed attempts.
The independent Astra review used 140686 tokens and 251.2 seconds. Its report checker passed; its acceptance verdict was not ready.
Review found the stale total-runtime table label and test rescue that could signal a reaped child's reused PID.
The production correction survived source review within the approved limits. Test teardown needs the same identity discipline as production cleanup.
A focused follow-up owns test rescue and documentation; no whole-watcher acceptance follows from passing counts.


### 2026-09-27 [11:06] — Safe test rescue accepted

Astra medium's first rescue correction used124892tokens/585.0seconds. Its review used85524tokens/148.9seconds and found early host destruction.
The completion correction used105147tokens/574.0seconds. The independent review used106597tokens/154.4seconds and found no required correction.
Main verified1093checks on each host,532delivery/evidence identities and44review inputs. Production preprocessing changed only assertion line numbers.
Ordinary rescue must retain the owner through cleanup; an acknowledgment or timeout does not permit host destruction.
The independent collection design assessment used56858tokens/156.8seconds. Main verified15inputs/15citations; recommendations remain distinct from policy approval.


### 2026-09-27 — Pure watcher retry state

GPT-6 Astra, medium, hooks disabled: implementation 75,198 tokens / 485.6 seconds; review 57,642 / 112.7.
The review found constructor field-name callbacks after 632 checks passed on each host.
Focused correction: 68,223 tokens; final review: 47,875 / 101.4 seconds.
Final source passes 636 checks per host, including four retained failing cases for C01.
Check field-name types before comparisons. Positional-only self also avoids keyword matching before validation.
Keep caller-controlled mapping expansion outside the guarantee. Source review and executed failures both matter.
A concurrent installed instruction edit invalidated blanket preservation claims; retain the edit and report its exact hash separately.


### 2026-09-27 — Capture recovery and watcher input reviews

Astra medium, hooks disabled: memory capture used 177,436 tokens / 1609.3 seconds; review used 92,501 / 208.7.
All 356 local controls passed, but independent review found four defects. Main reproduced each with synthetic data.
A pending record needs a real resume path. Also test runtime state inside selected content and canonical stored rows outside measurement bounds.
Watcher input correction used 224,337 tokens / 645.0 seconds. Its review used 97,554 / 114.7.
Main verified 813 tests per host, then reproduced three remaining path and JSON conversion defects.
Check bounds before conversion, expansion, or protocol dispatch. An OS path limit does not bound work done before the OS call.
Both corrections remain unaccepted. The passing report checker means valid report structure, not a positive review verdict.
