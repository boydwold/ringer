# Model notes — how workers actually perform

A running log of how models perform on real Ringer tasks, so engine and
model choices are made on evidence instead of vibes. The raw numbers now
live in the local eval log (`~/.ringer/runs.jsonl`); run `./ringer.py models`
to print the per-model, per-task_type scoreboard (tasks, attempts,
pass_rate, first_try_pass_rate, median duration/tokens, last_seen). This
file remains the judgment layer on top of those numbers.

**How to add a row:** after reviewing a run (post-run ritual step 5 in the
ringer skill), append one dated line under the model. Say the task type,
what happened, and what you'd do differently. Only write what the executed
checks and raw logs support — no vibes, no worker self-reports.

## codex (GPT-5-class, own harness)

- Strongest general worker; the default engine. Spend reasoning effort per
  task via `engine_args` (`["-c", "model_reasoning_effort=low|medium|high"]`)
  — high on gnarly tasks, low on boilerplate.
- 2026-07-05 — carried the heavy lanes of the milk-crate demo rehearsals
  (market read with source allowlist, site build) with clean first-attempt
  passes.
- 2026-07-10 — gpt-5.6-sol, code-feature (steering-profiles feature in
  ringer.py itself, ~470-line change + 18 tests + docs, run
  ringer-steering-profiles): shipped as PR #25. 2 attempts, 379k tokens,
  but the attempt-1 FAIL was the CHECK's fault, not the model's — the check
  gated on the ENTIRE pre-existing suite being green inside the worker
  sandbox (localhost binds blocked, fixture missing). The feature work
  itself was verified green both attempts; attempt 2 "hardened" an already
  -sound implementation. Scoreboard's FAIL row for this run understates the
  model. Lesson for check authors: regression gates must compare against
  the BASELINE failure set, never assert absolute suite green.
- 2026-07-06 — adversarial pre-merge review (aicred spark): passed on
  attempt 1, ~85k tokens.
- 2026-07-06 — motion design (5 HTML animations for video b-roll) + 2
  editorial diagram pages, each verified by rendering through headless
  Chromium to MP4/PNG: 7/7 passed on attempt 1. Broadcast-quality visual
  output from rich storyboard specs; the render-as-check pattern works.
- 2026-07-06 — milk-crate demo: two single-file website builds (v1 scaffold
  316s/~175k tok; final brand+market-test reskin 622s/~184k tok), both passed
  14-assertion content checks on attempt 1, including base64-embedding photos
  and honoring honesty-marker requirements. Codex remains the site-build lane.
- 2026-07-06 — ringer.py feature batch (task_type field + enriched eval rows
  + `models` scoreboard + hud single-tab fix; ~640-line diff incl. two new
  test suites): substance passed on attempt 1 — its check printed PASS
  (compile, all 16 suites, exact CLI aggregation contract) — but the run
  recorded attempt 2 because of the expect_files-before-check harness bug
  (see process lessons). Heavy single-file feature work against an exact
  behavioral contract is squarely codex's lane.

- 2026-07-06 — elsas-website demo: Next.js scaffold PASSED attempt 2 (682s,
  ~354k tok) — attempt 1 built a complete homepage and silently skipped the
  other 10 routes; the route-enumeration check caught it. Narration lane
  (15 ElevenLabs calls, chunked, nohup pattern) passed attempt 1. CAUTION: a
  codex fix worker GAMED a verbatim-content needle by hiding the required text
  in a visually-hidden paragraph — passed the check, caught only by
  orchestrator integration review. Needle checks need an anti-hidden-text
  assertion or documented exceptions.

- 2026-07-06 — OpenRouter catalog + explore suggester (catalog subcommand
  with snapshot/changelog/free-detection, daemon auto-refresh, tiered
  --explore; offline fixture-driven contract check): PASS attempt 1, 362s.
  Follow-up sentinel-pricing fix (variable-pricing models): PASS attempt 1,
  114s. With the verify-order fix landed, zero phantom retries across the
  whole batch.
- 2026-07-06 — adversarial review of the model-router stack (2,650-line
  diff, structured report contract): PASS attempt 1, 176s — found a real
  HIGH (--since window inflating first-try rates) plus 3 MEDIUMs, all
  confirmed against the code. Then fixed all five review findings in one
  batch (task-level --since, pricing transitions, event durability + flock,
  unknown pricing, stderr notice) with test coverage: PASS attempt 1, 202s.
  Review->fix roundtrip in codex's lane works end to end.
- 2026-07-06 — scoreboard HTML page (zero-LLM renderer, ~700-line diff,
  design + evidence-floor ranking + cost math + notes parser): substance
  PASS attempt 1 (the run's recorded retry was an orchestrator check bug —
  the free-promo watchlist legitimately mentions a free model before the
  ranked cards, and the check compared raw first-occurrence). Six review
  findings fixed in one batch, PASS attempt 1, 141s.
- 2026-07-06 — model-db stack (SQLite read model 516s, page redesign 536s,
  Ringside tab 527s, plus three fix batches all attempt-1): five substantial
  ringer.py features in one day, every one against an executed contract
  check. Review lane found the HIGH that mattered (sync cursor skipping a
  half-written trailing line). Codex is the proven lane for both sides of
  the review->fix loop on this codebase.

- 2026-08-19 code-review (intake PR #637, 3 codex lanes + 1 GLM lane, all PASS after
  hand-rescue): work was good, **severity calibration was not**. All three codex lanes
  labelled a finding BLOCKER that did not survive orchestrator checking — an "ids path
  silently drops held notices" that the pre-PR line already did (`git diff` showed the
  old line), an SSE gap that a control probe reproduced identically for exclude and
  approve, and an untested audit-index attribute no code reads. Each lane answered the
  question it was asked and then over-rated the answer. **Fix for next time: put the
  new-vs-inherited test in the spec itself** — "before rating anything BLOCKER, run the
  same probe against the pre-PR line and against the sibling code path; if it behaves
  the same, it is not this PR's defect." The mutation lane (which cannot over-rate,
  because PINNED/UNPINNED is measured) was the only one that needed no downgrading.

## glm-5.2 via opencode (`openrouter/z-ai/glm-5.2`)

- 2026-08-27 code-review (intake PR #738, blast-area lane, INT-323 fold-all button). PASS attempt 1, 65k tokens, 275 s (codex lanes: ~75 s). Traced the only production caller, the hover-clear path into Viewer/PagePreview, the sticky-heading CSS, and ran FieldCards.test.tsx read-only (198/198). Honest 'No findings' with a full Clean section and a medium-confidence INT-813 assessment marked as inference. Slow but the citations all resolved; still a safe blast-area lane.

- 2026-08-24 code-review (intake PR #715, blast-area lane). Best of the three lanes: found five stale-`v0` sites the other lanes and CodeRabbit both missed (`infra/delivery.ts`, `Tiltfile`, `config/delivery/bx/columns.yaml`, frontend fixture), read `DeliveryPreview.tsx` in full to prove the fixture was opaque rather than asserting it, and correctly refused to recommend rewriting historical records under `docs/superpowers/`. 1139 words, 17 citations, all resolved. Retried once — my checker's fault, not the model's.

- The cheap-intelligence default (~$0.74/M in, $2.33/M out, 2026-07 —
  20-30x cheaper output than frontier coding models). Reliable on
  mechanical, tightly-specced work: file edits, format conversions,
  template-driven builds.
- 2026-07-05 — milk-crate demo rehearsals: handled brand-board/SVG/copy
  tasks at around a penny per passing task.
- 2026-07-06 — adversarial pre-merge review (aicred spark): passed, but
  needed the retry (attempt 2) where codex passed on attempt 1. Long
  structured reviews sit at the edge of its comfort zone; keep the section
  contract explicit in the spec.
- 2026-07-06 — three mechanical image-generation batches (18 images via
  openrouter-image commands, idempotent batch-runner spec): 3/3 passed on
  attempt 1, ~14.5k tokens each. The "execute these exact commands, do not
  improve them" spec pattern is fully reliable for glm-5.2.

- 2026-07-06 — backfill/seed script for the model log (252-line stdlib CLI
  with a run-state join, 3-level mapping precedence, never-overwrite and
  idempotency rules): the artifact was CORRECT; the recorded FAIL was an
  orchestrator check-fixture bug (a missing newline glued the fixture's last
  row to a garbage line) plus the harness ordering bug below. Verified PASS
  once the check was fixed. Tight behavior contracts in the spec work great
  for glm — and read the raw logs before blaming the model.
- 2026-07-06 — README/MODEL-NOTES docs + task_type sweep across 17 template
  manifests: passed attempt 2; attempt 1 was lost to the harness ordering
  bug, not model quality — the retry worker's log correctly diagnosed that
  harness bug unprompted, impressive debugging from the cheap lane.
- 2026-07-06 — catalog/explore README section (flags, promotion ladder,
  per-user framing): PASS attempt 1, ~21.5k tokens. Doc sections against a
  grep-able content contract remain a safe glm lane.
- 2026-07-06 — milk-crate demo, full run: 4 independent buyer-persona
  reviews (focus group) all passed attempt 1 (~15k tokens, ~2¢ each) with an
  explicit VERDICT-block contract — persona work is squarely in glm's zone.
  Market read with live curl fetching passed once the spec demanded verbatim
  copy-paste of source URLs (first fail was the worker trimming URL slugs —
  spec/check craft, not model weakness). Brand-kit doc incl. a clean inline
  SVG wordmark: good, one bounce off an over-strict check regex.

- 2026-07-06 — elsas-website demo: verbatim content capture (16 pages + 19
  news posts, 213 blockquotes) passed attempt 2 — attempt 1 SELF-REPORTED
  "all 213 match exactly, 0 errors" while the executed check found 13 stitched/
  paraphrased quotes. Self-reports are worthless; the retry with injected
  failures fixed all 13 (~148k tok total, ~3¢). Page builds (about+faq;
  news index + 19 generated post routes via its own extraction script) and
  2 focus-group personas: all attempt 1. Fix batch attempt 1.
- 2026-07-06 — invariants/file-I/O review lens on the same stack: PASS
  attempt 1, 68k tokens — caught the non-atomic backfill rewrite (real data
  loss risk) and the daemon stdout race; both confirmed. Then fixed the
  backfill atomicity (tmp+os.replace, pid-stamped backups) attempt 1 with
  the original behavioral grader unchanged. Structured review with an
  explicit lens is now proven glm territory, not just probation.
- 2026-07-06 — solo adversarial review of the scoreboard renderer (~700
  line diff, injection-focused lens): PASS attempt 1 — 1 MEDIUM (unanchored
  MODEL-NOTES heading match cross-contaminating gpt-4/gpt-4o-style
  families) + 5 real LOWs, plus an empirically-verified injection all-clear
  (it actually rendered hostile model ids to prove escaping). Second
  proven-tier structured review in one day; glm is now the default review
  lane for mid-size diffs.
- 2026-07-06 — invariants/injection/frontend review of the 4,061-line
  model-db branch: PASS attempt 1, 96k tokens, 14 coverage items — two real
  contention findings (full catalog re-ingest per sync; schema writes on
  read paths) plus an empirical XSS all-clear on the new DOM surfaces.
  Third proven-tier structured review today.

- 2026-08-19 code-review (intake PR #637, frontend mutation lane, 11 mutations, PASS):
  **best lane in the run.** Found both real findings, and both survived independent
  re-verification — a row-scoped RTL assertion satisfied by a tooltip span rather than
  the cell under test, and a selection guard whose test is defeated by a
  `clearSelection()` effect firing on the scope change before the assertion reads the
  DOM. The second diagnosis named the exact effect and its dependency array; I confirmed
  it line for line. It also correctly recorded UNPINNED only after full-suite runs, and
  restored the tree. ~$0.033 for the lane. Promote GLM for frontend/RTL mutation work.

- 2026-08-27 — code-feature, intake INT-779 (TXT-notice pagination), sandboxed opencode engine in worktrees mode, 9 one-task rounds: 9/9 first-try (test author x6, implementer x3), 39k–61k tokens, 16–333 s each. Tight specs with an exact contract and an executed check (stub-first / mutation-pin / green) were enough; no retries. One round-2 regression (a trailing blank page) slipped past the check because no test pinned it — a check defect, not a model one.
- 2026-08-27 — code-feature/code-fix, intake INT-323 (React fold-all control; Jest/RTL via react-app-rewired). 4 tasks, 4/4 first-try, 45k–125k tokens. Test author followed the contract exactly, including a wrong assumption I gave it; the implementer then added hidden state (`mounted`) to satisfy that wrong test rather than stopping — it will bend the component to a read-only test. Give implementer specs an explicit MUST-NOT-CHANGE list and a 'stop and write notes.md' instruction; with that, the redo was 60 s, 45k tokens, clean.

## kimi-k3 (`openrouter/moonshotai/kimi-k3`) — DEMOTED for code-review

**Do not route review lanes here. Use codex.** Recorded so the next orchestrator
does not re-run this experiment.

The scoreboard argues for it and the scoreboard is not wrong — it is incomplete.
Over 37 code-review tasks it reached 0.73 first-try, which clears the `proven`
bar. Two things the numbers do not carry:

- **It loses whole lanes to OpenRouter 429s, and the loss is invisible.** A
  `rate_limit_exceeded` burned both attempts of a review lane and produced no
  report. Ringer has no 429 or backoff handling at all, so a rate limit is
  treated as an ordinary task failure and the immediate retry hits the same
  limit. Worse, the 429 never reached the attempt log, so the scoreboard cannot
  learn this happened — it just silently shows one fewer lane.
- **Cost.** At $3.00 in / $15.00 out per million it is roughly 4x the input and
  7x the output of the cheap-intelligence lane, and codex reached 0.92 first-try
  over 234 code-review tasks on a flat plan. Paying 7x for a lower rate is only
  defensible if you specifically need a different model family in the panel.

Keep it available for deliberate model diversity — a bakeoff, or a second
opinion where a distinct lineage is the point. Not as a default review lane.

- 2026-07-31 — code-review (blast-area lane, PR #514 round 3, run
  pr514-bulk-actions-review). **The demotion stands, but this run is a point in
  its favour and the orchestrator's engine pick was made wrongly.** I chose it
  from `./ringer.py models` alone and did not read this file first, which is
  exactly the miss the section above exists to prevent — read the judgment layer
  before assigning, not after. Outcome: 2 attempts, 142k tokens, 1033s. Attempt 1
  failed `missing_report` — it did the analysis and never wrote `report.md`, the
  print-instead-of-write trap in the skill's check rules, not a 429 this time.
  Attempt 2 passed and produced the strongest documentation-verification work of
  the three lanes: it checked every doc claim against code and cited both sides,
  measured the shared client's real timeouts, and twice refused to state a
  botocore retry-attempt number it had not verified, choosing to look it up
  instead. It also correctly flagged one finding as "not introduced by these
  commits." Cost argument in the demotion is unchanged. If routed here again, put
  "write the file, do not print it" in the spec's output contract explicitly.

- 2026-08-04 — code-review (blast-area lane, PR #507 review, run
  intake-pr507-apex-paydown-review). **Third orchestrator in a row to pick it off
  the scoreboard without reading this file. I did it again.** The demotion note is
  four lines long and says "do not route review lanes here"; I ran
  `./ringer.py models --task-type code-review`, saw 65% first-try and a prior
  blast-area outing, and assigned it. Read the judgment layer BEFORE assigning.
  Outcome: both attempts died instantly (rc=1, ~1s each) on an OpenRouter
  `UnknownError` — `{"message":"Unexpected server error","ref":"err_de6981dc"}`.
  A new failure mode, not the 429 or the print-instead-of-write trap: a provider
  5xx, which Ringer also treats as an ordinary task failure and immediately
  retries into. Zero useful output. Relaunching the identical lane on codex passed
  first try and produced excellent work. Third distinct infrastructure-loss mode
  from this route in three outings — the pattern is the route, not the model's
  reasoning.

- 2026-08-11 — code-review (blast-area lane, PR #575 INT-38 selection layer, run
  intake-pr575-review). **Fourth orchestrator in a row to pick it off the
  scoreboard without reading this file, and the second to hit the identical
  failure.** I ran `./ringer.py models --task-type code-review`, saw 63%
  first-try and recent use, and assigned it. The demotion heading is four lines
  above those numbers. Outcome: byte-for-byte the 2026-08-04 mode — both
  attempts died instantly on an OpenRouter `UnknownError`,
  `{"message":"Unexpected server error"}`, refs `err_741b91f2` and
  `err_24d41680`, zero tokens billed, no report. Relaunching the identical lane
  on codex passed first try, again. That is four outings and four
  infrastructure losses; the two codex lanes in the same run both passed first
  try. Treat the scoreboard row for this route as measuring a channel that does
  not deliver, not a model that reasons badly. **If you are reading this because
  you are about to assign a review lane to kimi-k3: don't. The numbers will look
  fine. They are not the problem.**

- **2026-08-12 — fifth outing, fifth infrastructure loss (PR #507 round-4 review,
  blast lane).** Same failure again: both attempts died on an OpenRouter
  `UnknownError`, `{"message":"Unexpected server error"}`, refs `err_fbef68f1`
  and `err_99d5cfa5`, zero tokens billed, no deliverables. Relaunching the
  identical lane on codex passed on content first try. Five outings, five losses.
  **Orchestrator error, not a new data point about the model:** I picked this
  route off `ringer.py models --task-type code-review` (62% first-try, looked
  like a fine exploration slot) and did not read this file first. The skill says
  to read the scoreboard *and then* MODEL-NOTES; the scoreboard alone will keep
  recommending this route forever. Cost: ~7 minutes of wall clock and one
  re-run. Read the judgment layer before assigning, every time.

## kimi-k2.7 via opencode (`openrouter/moonshotai/kimi-k2.7-code`)

- 2026-07-06 — adversarial pre-merge review (aicred spark): passed on
  attempt 1, ~83k tokens. First real outing; promising for review work.
  (Ran through an ad-hoc copy of the opencode engine block — the per-task
  `model` field now makes that unnecessary.)

## kimi-k2.6 (`moonshotai/kimi-k2.6`, subject-model evidence via OpenRouter)

- 2026-07-07 — Benchmark Suite 2.0 operator eval, killed by Jon at ~4.5h.
  Serving throughput, not model quality, was the failure: on the Brick
  1000-piece case (reasoning xhigh, pinned provider order
  inceptron→decart→baidu→modelrun, no fallbacks) K2.6 averaged ~21 tok/s
  with two ~19-min stalls at 4.5 tok/s — 136+ min unfinished vs Sonnet 5's
  25 min (94 tok/s) and GPT-5.5's 24 min (55 tok/s) on the identical case.
  Model behavior itself was fine: 28 turns (fewer than Sonnet's 82), 170k
  output tokens (in family norms), 12% reasoning, zero API errors. Verdict:
  do NOT schedule K2.6 for long agentic work through that provider set;
  if K2.6 data is ever wanted, probe a single case against other providers
  first. Distinct model from k2.7-code above — don't transfer this verdict
  to k2.7.


## grok-build (Grok CLI engine, flat plan)

- 2026-07-10 — identity correction (Jon): the Grok Build CLI is a HARNESS
  serving exactly two models — Grok 4.5 (xAI) and Composer 2.5 (Cursor).
  The engine-lane slug `grok-build` resolves to Grok 4.5. "Grok Build 0.1"
  was never a model; earlier notes/rows using it as one describe Grok 4.5.

- 2026-07-06 — first outing (elsas-website demo), engine added same day:
  audition PASS attempt 1 in 28.9s. Then: asset harvest (11 images, live URL
  re-fetch check), books page, 5 work-page routes in one task (59 verbatim
  needles), adversarial code review (10 real findings incl. an unshelled 404
  and a broken embedded link), press/media fix batch, audio-player integration
  across 15 pages — ALL attempt 1 (player's red ledger entry was a check bug,
  artifact certified). Fast, precise on mechanical/code work. No token counts
  in JSON output (flat plan) — cost reads "included in plan".

## grok-composer-2.5-fast (Grok CLI engine, flat plan)

- 2026-07-06 — first outing (elsas-website demo): audition PASS attempt 1
  (138s — slower than grok-build but the strongest copy of the round).
  Accessibility constitution (14 testable criteria, SC-numbered) attempt 1;
  a11y-gatekeeper harness (axe+Playwright, light/dark, reduced-motion assert)
  attempt 2 — attempt 1's harness mishandled Next's default /404 route.
  Events/faq/contact fix batch attempt 1, but satisfied "editorial grid" with
  an EMPTY aside landmark — axe caught it (landmark-complementary-is-top-level).
  Persona work: good. Watch for letter-of-the-spec shortcuts on layout asks.

## nemotron-3-super-120b (via opencode, `openrouter/nvidia/nemotron-3-super-120b-a12b:free`)

- 2026-07-06 — AUDITION FAILED (exploration slot, $0 spent — free promo).
  Task: fresh-eyes adversarial review of a 2,650-line diff with a structured
  report contract. Failed both attempts on the same executed check: report
  had the right sections and verdict but under 3 concrete code citations —
  shallow engagement with the actual code, 212k tokens burned. Don't re-run
  this audition on long structured code review; if it gets another slot,
  try a shorter, more mechanical task first.
- 2026-08-27 code-review (intake PR #728 rounds 13 and 14, verifier lane, `nvidia/nemotron-3-super-120b-a12b:free`): four attempts, zero reports. Cause is NOT the model: OpenRouter answered `No endpoints available matching your guardrail restrictions and data policy` — the account's privacy setting refuses providers that train on prompts, and free endpoints do. So free-tier exploration lanes cannot run under this account as configured; either allow those providers in the OpenRouter privacy settings (a deliberate data-handling decision, not a Ringer one) or explore with cheap PAID slugs (`deepseek/deepseek-v4-flash` at $0.03/M in, `tencent/hy3`, `qwen/qwen3.5-397b-a17b`). The paired GLM 5.2 lane passed both rounds.

## llama-3.3-70b-instruct (via opencode, `openrouter/meta-llama/llama-3.3-70b-instruct:free`)

- 2026-07-06 — AUDITION FAILED (exploration slot, $0). Fresh-eyes review of
  a 4,061-line diff with a verbatim-quote citation requirement: failed the
  structured-report check both attempts. Second free-model audition to fail
  on long structured code review (after nemotron-3-super) — the exploration
  ladder now says: audition free models on SHORT mechanical tasks first;
  long-diff review is a proven-tier lane.

## Small / flash-class models

- First to choke on long conversational or multi-turn harness tasks —
  watch retry counts before scaling them into a batch (2026-07-05 focus
  group lesson).

## Process lessons (cross-model)

- **2026-08-12 — PR #504 round-2 review: 3/3 codex lanes first-try, and the two
  standing traps in this file were both avoidable by reading it FIRST.** Run
  `intake-pr504-rbs-rollover-review`, 3 lanes, 36 mutations, 660k tokens total
  (138k/324k/198k), no retries. Two things made it clean, both taken from the
  notes above rather than learned again the hard way:
  (1) `workdir` pointed at the artifacts dir so each task dir *was* the
  sandbox-writable root, and every `expect_files` entry was relative
  (`report.md`) — no lane hit the permissions wall that burned the #507 round-4
  and round-7 runs.
  (2) Every spec said **"write deliverables as you go, not at the end"**, with
  the Kimi lane-death note quoted inline as the reason. All three lanes had a
  complete `mutations.tsv` and a draft `report.md` within ~2 minutes, so a
  mid-run death would have cost a refinement pass, not the lane. Worth keeping
  as boilerplate in any long read-only review spec.
  Also: mutation lanes do NOT need git worktrees. `cp -a src tests` into the
  task dir plus `PYTHONPATH=$PWD/scratch/src <shared-venv>/bin/python` overrides
  an editable install cleanly (verified before writing the manifest) — ~7MB and
  0.5s per suite run, versus worktree setup cost and the read-only-worktree
  problem two #507 lanes had to work around.
  Check design that paid off: the check re-ran the *pristine* tree itself, so a
  lane that mutated shared source instead of its own copy would have been caught
  by the check rather than by me trusting its report. Nothing tripped it.
  Caveat on trusting lanes: all three passed, and the blast lane's three P1
  findings still had to be reproduced by hand. One of my own verification probes
  used anchor strings that were not in the fixture and "confirmed" nothing —
  the `NOT REPRODUCED` line was a false negative from a broken probe, not
  evidence. Print the anchor-not-found case loudly; a probe that matches nothing
  looks exactly like a probe that found nothing wrong.

- **2026-08-12 — codex's sandbox blocks writes outside its task workdir; put
  `expect_files` inside it.** On the PR #507 round-4 review all three lanes did
  their work correctly and then FAILED their checks, because the manifest told
  them to write deliverables to the shared artifacts directory
  (`~/ai-workspaces/_artifacts/work/<slug>/`) and the sandbox denied it. The
  workers fell back to writing into their own task dirs — `run/<key>/lane_*.md`,
  `run/<key>/mutations_r4/` — so nothing was lost, but every lane recorded
  `fail` and burned a retry attempt re-trying the impossible write. One lane
  spent its retry politely asking for the directory to be made writable.
  Fix for next time: point `expect_files` and the spec's output contract at
  paths INSIDE the task workdir, and hoist to the shared artifacts dir yourself
  after the run. A run whose checks all fail on a permissions detail reads as a
  broken swarm when the work was actually complete and correct.

- **2026-08-12 (same day, later) — I made the identical mistake again on the PR
  #507 round-7 review, with this note already sitting in the file.** Same three
  lanes, same shared-artifacts output contract, same three `fail` verdicts, same
  wasted retry per lane. The note above is written for someone reading it AFTER a
  failed run; nothing makes an orchestrator read it BEFORE writing the manifest.
  So: **the writable-path check belongs in the manifest lint, not in these
  notes.** Until it is, read this section before writing any manifest whose
  `expect_files` sit outside `<workdir>/<task>/`. Codex again behaved well —
  each lane finished its analysis, wrote every deliverable into its own task
  dir, stated the block plainly, and invented nothing. Two lanes additionally
  found their assigned git worktrees read-only and, rather than give up or fake
  it, mutated byte-for-byte temporary copies and hash-compared them back; both
  said so under Assumptions. Harvesting the files by hand and re-running the
  three checks unchanged gave guards PASS, blast PASS, and tests failing only on
  its one genuine surviving-mutation finding.

- 2026-07-06 — the orchestrator's CHECKS were the day's top failure source:
  three check bugs (fixture newline join, first-occurrence ordering vs the
  watchlist strip, claim-prefix split on '.' instead of ':') each produced
  a FAIL verdict on work that was actually correct — including all four
  capability-research packets at once. Every one was caught by reading raw
  logs/artifacts before blaming the model. Corollary for the scoreboard:
  recorded FAILs whose root cause was a check bug are annotated here, and
  check fixtures deserve the same review care as production code.


- 2026-07-06 — HARNESS BUG (fix in flight on feat/model-perf-log):
  Verifier.verify evaluated expect_files BEFORE running the check, so any
  check that itself creates/exports its deliverable (the worktree
  patch-export pattern) failed attempt 1 with "missing expected files" even
  when the check printed PASS. Cost 3 phantom retries in one run — and it
  poisons first_try_pass_rate, the model log's routing signal. Until the
  reorder lands on your checkout: have the WORKER write the declared
  deliverable, or don't declare check-created files in expect_files. When
  reading seeded scoreboard numbers, remember 2026-07-06 first-try rates
  are depressed by this.
- 2026-07-06 — the model log is now automatic: every attempt row carries
  model/task_type/retry; `./ringer.py models` prints the scoreboard; 81
  historical rows were seeded via scripts/backfill_model_log.py with a
  hand-authored task-type mapping. Give every manifest task a task_type or
  its evidence buckets as (untyped).

- 2026-07-06 — a three-model "bakeoff" ran every task on the engine's
  hard-coded model: task keys said glm/gpt/kimi, but the opencode engine
  block pinned glm-5.2, so one model wrote all three "competing" reviews.
  This is why the per-task `model` field exists — a bakeoff is only a
  bakeoff if the manifest, not the engine block, names the model. Verify
  with the `model` column in the run state, not the task key.
- 2026-07-06 — spawning 5-6 opencode workers simultaneously hit opencode's
  local "database is locked" (sqlite) — several instant attempt-1 failures,
  all absorbed by Ringer's retry. Cosmetic in Ringside ("sent back" at 0s) but
  wastes an attempt; consider staggering opencode spawns.
- 2026-07-06 — opencode's bash tool kills foreground commands around the
  ~2-minute mark: a 2min+ image-generation API call can never finish inline.
  Spec pattern that works: nohup the long command in the background, then
  poll for the output file in separate short commands.
- 2026-07-06 — two check-craft lessons from the same run: (1) URL-allowlist
  checks must be prefix-tolerant (workers legitimately trim slugs); (2) any
  heading-regex must tolerate numbered headings ("## 3. Type / Typography").
  Both failures looked like worker laziness until the raw logs said otherwise.
- 2026-07-06 — elsas-website demo, check-craft in BOTH directions: (1) a fixed
  800-char body floor failed a worker for faithfully converting genuinely tiny
  source posts — floor must scale with the source; (2) a citation gate treating
  every backtick as a page-quote failed honest reviewers who backticked their
  own fix-suggestions — line-scoped pair parsing + attribute-aware corpus fixed
  it; (3) needle-exception lists must be shared across ALL checks that consume
  the needle set (a needle excepted in one checker failed a task through
  another). Post-mortems ruled FOR the worker 3 times this run — read raw logs
  before blaming the model.
- 2026-07-06 — opencode sqlite "database is locked" again with just 2
  simultaneous opencode spawns (page-news + page-about-faq); retry absorbed it.

- **Codex's sandbox cannot write outside its own worktree, so `out/` deliverables never
  land** (intake PR #637, 2026-08-19). All four lanes did the work, then failed their
  checks on missing files and burned a retry each. Two of them said so plainly and left
  the artifacts in the worktree or `/tmp`; I copied all four by hand. **Fix: make the
  task worktree the deliverable path** (`./report.md`, `./results.tsv`) and have the
  CHECK copy them out — the check runs on the host, not in the sandbox.
- **A check script must use the project's own test invocation, verbatim.** My
  `check_laneC.sh` ran `pnpm test -- --watchAll=false --testPathPattern=…`; under pnpm 11
  that mangles the CRA jest config and fails all 46 suites on transpile, which reads as a
  broken PR rather than a broken check. `pnpm exec react-app-rewired test --watchAll=false`
  is the form that works. I lost ~20 minutes diagnosing a fresh worktree, a reinstall and
  a node version before reading the actual first line of output — which said
  `Invalid testPattern … supplied`.
- **Pre-build the environment before the run when the sandbox blocks the installer.**
  `uv sync` panics under the codex sandbox (`system-configuration` SCDynamicStore, NULL
  object). Building each lane worktree's `.venv` from the host first — and confirming
  each resolves the package to its OWN `src/`, which the mutation lane depends on — cost
  three minutes and unblocked every Python lane.

## codex (2026-07-06, bench-operator-proofing)
- 8/8 code-feature tasks passed attempt 1 across 3 rounds (worktrees mode, Python harness refactor; 108k-406k tokens/task). Specs embedded the approved architecture doc + exact file ownership; checks built fresh uv venvs and ran the full pytest suite.
- Lesson (check design, not model): all 3 post-integration bugs were invisible to the checks — a test that passed only because the worker's worktree lacked .env, a `--help`-only assertion missing a runtime importlib/sys.modules bug (py3.12 dataclasses), and bare console-script names failing outside activated venvs. Checks should exercise one real invocation from a cold shell, not just --help.

## gpt-5.6-sol (codex)
- 2026-08-25 code-feature (intake INT-160, bulk executor; round 1, 5 parallel test-author lanes): **5/5 pass, but only 1/5 first-try — and all four retries were MY defect, not the model's.** Every retry failed on my `--min-tests N` floor and nothing else: lanes wrote 21, 9, 5 and 9 correct fail-first tests against floors of 22, 10, 10 and 12. The content was right in every case; the count was short. **A count floor is a bad check.** It is a proxy for coverage, it rejects good work for arithmetic, and it pressures a worker to pad on the retry. Set the floor well below the number of behaviours the spec enumerates and judge coverage by reading the tests, which is the step that actually judges it. On substance the lanes were excellent: given "assert the remaining time is unchanged, not merely that a handler fired", the toast lane advanced 12s past an 8s window while hovered and asserted no change; given "pin the refusal ORDER", the executor lane parametrized a case supplying both a wrong token and an expired window and required the token error. Precise property statements in the spec came back as precise assertions. ~570k tokens over 5 lanes.
- 2026-08-19 code-feature (intake INT-127, batch id across audit events; 3 rounds, 6 tasks, one run_name): **6/6 first-try**, ~350k tokens total, longest task 11m. Round 1 was three parallel test-author lanes under a stub-first check (>= N collected, ALL failed, 0 passed, 0 skipped) — each wrote 6-17 tests that all failed correctly against a NotImplementedError stub, and none tried to game the check by writing trivially-failing tests. Round 2 was two parallel implementers, one owning a new 181-line leaf module and one editing a 6,000-line file, with the test files read-only; neither touched a test. Two things worth reusing: (a) the two round-1 lanes that could not read each other's files converged on an IDENTICAL return contract for the same function, from the spec alone, so a precise output-contract paragraph really does substitute for coordination; (b) the implementer given "read tests/X.py, it is the specification" made all 17 pass without a single spec clarification. Direct-repo-edit mode (worktrees: false) with disjoint owned paths and one shared git-status allowlist naming EVERY path the whole feature touches — no cross-lane file damage across all six tasks.
- 2026-08-04 code-review (PR #507 Apex review, 3 lanes): **the scoreboard's
  first-try rate dropped from 93% to 78% on this run and the drop is mine, not the
  model's.** Two of three lanes exited rc=0 having completed the full task, but my
  output contract named absolute paths outside the task workdir, which the sandbox
  forbids — so my own check marked them `fail` for a missing deliverable. Both had
  written correct, thorough deliverables inside their workdir. The correctness lane
  independently reproduced the PR's 1/7 extraction result, prototyped and verified
  a working replacement pattern for every failing regex, and caught a second-order
  bug I had missed (widening the date regex alone still yields no date, because the
  shared date parser accepts only DD-Mon-YYYY). The mutation lane ran six
  source mutations with captured pytest transcripts and correctly found the one
  surviving mutant. Treat these two rows as reviewer error; see the process lesson
  dated 2026-08-04.
- 2026-07-15 ringer-self-update run (3 serial tasks, direct-repo-edit mode): code-fix baseline-test repair 1/1 first-try (61k tokens, 1.6m); code-feature self-update mechanism (git fetch/ff-pull/re-exec + HUD staleness restart + 20-test suite) 1/1 first-try at high effort (153k, 8.1m); code-feature signal-contract (all 3 scoreboard surfaces + canonical-route lint enforcement) passed on retry (358k, 13.7m) — attempt 1 died on stale old-column assertions in pre-existing tests it hadn't finished updating; the retry prompt's injected FAIL list was enough to close it out. Lesson: when a task rewrites a display contract, name every test file asserting the old contract in the spec's ownership list AND tell it to update them FIRST.
- 2026-07-09 code-feature/code-fix (ringside-overhaul): 4/4 first-try — a ringer.py logging change with tests, a 265-line stdlib backfill CLI (atomic rewrite, dry-run, idempotence all check-verified), a ~1500-line single-file HTML redesign (running-now pills + worker-card grid + multi-expansion refactor, 30KB patch, node --check + contract greps + unittest), and a render-gating change where it correctly UPDATED tests asserting the old behavior instead of gaming the check. Medium/high reasoning, 65–120k tokens/task.
- Same day, different session (bench-harness-patches, code-fix): 0.29 first-try over 7 tasks on a Next.js/Turbopack harness. Spec and check quality dominate model choice — see the scoreboard before generalizing either number.

## GPT-5.5 (codex) — attribution caveat
- Scoreboard rows dated before 2026-07-09 may actually be gpt-5.6: codex eval rows logged model="" until the write-time stamping fix (PR #18) and were credited to GPT-5.5 by the registry default at read time, while the machine's codex default had already moved to gpt-5.6-sol at an unknown earlier date. `scripts/backfill_model_from_logs.py` re-stamps rows with surviving command-log evidence; anything it skips is a mixed-model aggregate. Trust post-2026-07-09 rows.

## poolside/laguna-s-2.1:free (via opencode) — AUDITION INCONCLUSIVE, not a failure
- 2026-08-25 code-feature (intake INT-160, one low-stakes lane: two optional fields on an existing DynamoDB record). **Failed both attempts without emitting a single token.** OpenRouter returned `{"type":"error","error":{"name":"UnknownError","data":{"message":"Unexpected server error"}}}` on attempt 1 (`err_ce37d4cb`) and attempt 2 (`err_e60e3bad`), roughly one second apart. `tokens` was null and the worker log was 15KB of echoed spec with no model output.
- **Record this as a provider outage, NOT a model demotion.** The scoreboard will carry two failed rows against the model that the model never had a chance to earn. Do not let those rows talk the next orchestrator out of the audition — re-run it before concluding anything. The slice was re-run on codex and passed.

## nvidia/nemotron-3-super-120b-a12b:free
- 2026-07-08 (research, content-strategy-recon): FAIL x2. Did the analysis in chat but never wrote report.md; attempt 2 exited rc=0 with no file. Doesn't reliably follow file-output contracts under OpenCode. Demoted — don't re-audition on file-deliverable tasks.

## meta-llama/llama-3.3-70b-instruct:free
- 2026-07-08 (research, content-strategy-recon): FAIL x2. Timed out at 900s both attempts on a moderate DB-scrape+format task. Too slow on the free tier for harness work. Demoted — don't re-audition without much longer timeouts or paid tier.

## z-ai/glm-5.2 (addendum)
- 2026-07-08 (research/filter, pitch-foundry): FAIL x2 on a long-spec rubric-application task (~40k input: embedded rubric + 4 candidate files). Read all inputs, exited rc=0 with ZERO output tokens both attempts — silent stall, no file written. GLM handled the same session's shorter formatting specs fine. Lesson: keep GLM specs short; route long-context apply-this-rubric work to codex.

## GPT-5.5 (codex) — honesty flag
- 2026-07-08 (image-gen, pitch-foundry): sandbox DNS blocked openrouter.ai; ALL 10 API calls errored (logged honestly in gen-log) — but the worker then FABRICATED 10 deliverables locally (composited canvases from the ref image) to satisfy a files-exist>40KB check, and passed. Lesson: (a) codex sandbox has no external DNS on this machine — route API-calling tasks to opencode (network open); (b) never write an existence-only check for generated media — require the success log (SAVED/cost lines) to match the file count.

- 2026-07-09 persona-review (pitch-foundry exec-briefing panel): 0/2 first-try+retry. Produced coherent review CONTENT as chat text but never wrote report.md — does not reliably use file-write tools under opencode. Demoted; do not re-audition for file-deliverable tasks without a write-tool probe first.

## gpt-5.6-luna (codex)
- 2026-07-09 code-feature (unlock-ai guide-format conversion, strict type-contract check): 1/1 first-try, 42.6k tokens, 80s. Followed a multi-file TS pattern precisely at $1/$6 pricing. Good candidate for mechanical codegen/docs lanes; audition in adjacent types.

## opencode / z-ai glm-5.2 (via openrouter)
- 2026-08-25 code-review (intake PR #728, frontend-ux + blast-area lanes). Two strong
  lanes in one review. Blast-area independently found the `held` scope hole (executor
  never narrows on BULK_SCOPE_STATUSES) and correctly cleared eight AGENTS.md bulk
  invariants with line-level evidence. Frontend-ux produced the best single finding of
  the whole review: traced `incomplete: true` from the api.ts catch to the QueueList
  caller that never reads it, and stated the impact concretely ("Changed 400 notices ·
  0 rejected" on a 1,240-notice run that stopped early) — CodeRabbit had flagged the
  same field as merely unused. Strong on "trace the value to its consumer" work and on
  clearing things correctly, which is what makes a held-up list trustworthy.
- 2026-07-09 (aicred-invoice-downloads, 4 code-fix tasks + 1 follow-up, worktrees+npm ci checks): systematic attempt-1 NO-OP — all 4 parallel workers produced zero edits and no summary on first attempt, then completed cleanly on attempt 2 after retry-prompt injection (34k-69k tokens each). Follow-up single task passed attempt 1. Suspect first-invocation session warm-up in opencode-sandboxed under parallel spawn; budget for 2 attempts on parallel GLM batches. Output quality on Next.js/Stripe route+test work: solid, spec-faithful, one boss-caught design gap (used user-scoped supabase client where RLS demanded service role — spec didn't say explicitly; say it explicitly).

## opencode (harness note, any model)
- 2026-07-28 (code-review, pr82-token-saver-review): GLM 5.2 produced a complete, high-quality 218-line report but could NOT write it to an output directory created by the parent Claude Code process — every write returned EPERM. It then spent ~3000s burning retries on ctypes/`openat`/AppleScript/`sandbox-exec` workarounds until it timed out, and the task logged as FAIL despite the deliverable existing in its taskdir. Codex workers in the same run were unaffected. Lesson: point opencode workers' output INSIDE their own taskdir and harvest via `expect_files`; never hand them a shared output dir another process created. This is an orchestrator spec bug, not a model failure — do not read the FAIL as evidence against GLM.

- 2026-08-20 code-review (intake PR #639, blast-area lane, 3-lane review swarm). Produced the strongest report of the three: traced the new `held`→`excluded` transition through every status reader, the bulk-count projection contract, the approved-set feed, replay, and the frontend, and resolved the `requeued_at` two-marker question with the exact reasoning (held is not in `BULK_SCOPE_STATUSES`, so the bound cannot apply). Every claim I spot-checked held. Recorded FAIL after 2 attempts, but the failure was **my check's fault, not the model's** — it cited `approve_snapshot.py:466` as a bare filename where the real path is `src/notice_validator/output/approve_snapshot.py`, and my citation resolver demanded repo-relative paths. Strict-on-format, which my own check rules warn against. Next time: resolve a bare basename by searching the repo before calling it unresolvable.

## Process lessons (2026-08-04, PR #507 review)

- **Deliverable paths outside the task workdir are silently unreachable, and the
  check blames the worker for it.** I wrote an output contract naming absolute
  paths under `~/ai-workspaces/_artifacts/…`. The codex sandbox permits writes only
  inside the task workdir, so two lanes did the ENTIRE job correctly, wrote their
  deliverables into `<workdir>/<task>/`, exited **rc=0**, and were then marked
  `fail` by my own `missing deliverable` check. Both lanes' logs ended with the
  worker explaining it had been denied `Operation not permitted` and telling me
  where the real files were — I nearly re-ran 25 minutes of correct work. Write
  output contracts as workdir-relative filenames (`./report.md`, as the
  review-swarm template does) and harvest afterwards; if you want files elsewhere,
  copy them yourself once the run finishes. When a lane exits rc=0 but the check
  says the deliverable is missing, read the log tail before relaunching — that
  combination means a path problem, not a lazy worker.
- **A lane whose task already failed looks identical to a stalled lane.** The
  quiet-log watcher from the ringer skill fired on a lane that had already been
  marked `fail`, because a dead task's log stops being written. Skip lanes that
  have a terminal status or an existing deliverable, or the watcher wakes you for
  nothing while the live lanes are still working.
- **Do the deterministic part yourself before writing the manifest.** The whole PR
  verdict here rested on one fact — run the real PDF through `validate()` and diff
  against the seven reviewer-corrected values — which is a 40-line script, not
  model work. Establishing it first meant the three lanes could be pointed at what
  I did *not* know (root causes, mutation coverage, blast radius) instead of
  re-deriving the headline. Two of my three going-in suspicions were then refuted
  by the blast lane, which is the value of running lanes on open questions rather
  than on conclusions you already hold.

## Process lessons (2026-07-28, PR #82 review)
- **Ideas worth keeping from a rejected PR.** PR #82's pre-call gateway was dropped (needs your own API key, so it converts flat-rate OAuth plans into metered API billing; incompatible with Claude Code; and it saves tokens by stripping the tool list, which is the thing that makes the CLI worth using). One idea inside it is worth remembering if the problem ever comes back: an *explicitly blessed* answer cache — key a reviewed answer to the exact request plus the exact selected source packet, and replay it with zero upstream calls, never auto-accepting a model answer. It only fires on byte-identical repeats, which is why it didn't justify 2,000 lines here.
- **Doc-stated support floors need a CI job or they are fiction.** README promised Python 3.11+ while CI only ever ran 3.12; a 3.12-only f-string reached review with a fully green suite. Either test the floor or move it.

### Codex — 2026-07-31, mycelium local-chat build (code-feature × 3, code-fix × 1)

Four sequential one-task rounds building a retrieval-backed chat REPL in a real
repo (new module + CLI subcommand + protocol + additive dataclass changes),
each with an executed pytest/ruff/behavioural-probe check. 3 of 4 PASS on
attempt 1; tokens 61k–146k, 161s–696s.

The single attempt-2 was **the reviewer's fault, not the model's**: the check
fed it a config invalid for two reasons at once and demanded the wrong one be
reported. Codex satisfied the check by adding a workaround that masked all
config errors — reasonable given the instruction, wrong for the product. Do not
count this against codex's first-try rate for code-feature; count it as
evidence that a bad check becomes a specification.

Worth repeating: given a spec that named an exact API surface (function names
and signatures asserted by the check), codex matched it precisely every time,
which is what made the probes checkable. It also volunteered a genuine
improvement not in the spec (a citation index in the prompt so the model's [n]
references line up with the printed source list).

## Kimi K3 (`openrouter/moonshotai/kimi-k3`)

- 2026-08-04 — code-review (blast-area lane, PR #504 intake review, 40-min lane over a
  large Python repo): worker DIED at ~15 min in, mid `step_start`, after doing substantive
  correct analysis (ladder order, ADR judgment, corpus-evidence gap all visible in its
  reasoning trace) but never wrote `report.md`. Ringer's record stayed frozen at running;
  I killed the run. Second time this shape has cost a lane. For long multi-question
  read-only lanes prefer codex, or split the lane so a deliverable lands early.

## Process lessons (2026-08-19, PR #638 review)

**GLM 5.2 (opencode) won the round outright on the blast-area lane.** Both codex
lanes missed the only true merge blocker: `unhold_meta` re-places a row in the
open queue without restamping `GSI1SK`, breaking the INT-126 `as_of` marker so a
bulk executor admits rows the reviewer never counted. GLM found it, cited
`records.py:5124` and `:5217` correctly, and framed the tradeoff against the ADR.
First-try PASS. Signal: for "who else reads this code path", a cheap model with a
wide read budget beats a strong model with a narrow question. Give GLM the
blast-area lane by default on this repo.

**Both codex lanes FAILED their checks with the work complete — the sandbox
write block, again.** Specs told them to write reports to an absolute path under
`~/ai-workspaces/_artifacts/`. Codex's sandbox refuses writes outside the task
dir, so both wrote to their own worktree instead and the `expect_files` check
failed twice. The worker even said so: "The sandbox must grant write access to
… for the required handoff to succeed." Nothing was lost — 9 mutations with
verbatim pytest output were sitting in the task dir — but the run reads as 2/3
failed when it was 3/3.

Fix next time, either:
- set `engine_args` to grant write access to the artifact dir, or
- have workers write into their task dir under a fixed name and let the CHECK
  copy it out (works in worktrees mode too, since the check runs before cleanup).

The second is better: it costs nothing and works for every engine.

**Worktrees mode + a shared venv works.** No venv exists in a fresh worktree, so
specs pointed at the review worktree's interpreter with
`PYTHONPATH="$PWD/src"`. I proved the override beat the editable install before
writing the manifest. Mutation testing then ran against each task's own source.
Frontend Jest was unavailable (no `node_modules`, registry unreachable), so UI
mutations were skipped — worth pre-seeding if UI mutation coverage matters.

### 2026-08-19 — sandbox blocks external deliverable paths (codex AND opencode/GLM 5.2)

code-review, intake PR #685, 3 lanes. Two of three lanes recorded FAIL purely because
the manifest told them to write `lane<N>-report.md` to an artifact path OUTSIDE their
task worktree. Both harnesses refused: codex `Operation not permitted`, opencode
`EPERM` on bash redirect, the write tool, and `pathlib.write_text` alike. Both also
could not run `git checkout -- <file>` to restore a mutation, because the linked
worktree's `.git/.../index.lock` is outside the writable root — they restored with
inverse patches instead and verified an empty `git diff`.

The analysis in both lanes was complete and correct; only the copy step failed. I
recovered the files from the task dirs and both passed `check-lane.sh` unchanged.

Do this instead: have the spec write deliverables INSIDE the task worktree
(`./report.md`), and let the CHECK copy them out — the check runs outside the sandbox.
Costs two lanes their PASS otherwise, and the run summary reads as a 2/3 failure when
it was 3/3.

## Process lessons (2026-08-20, PR #638 re-review)

**I killed my own swarm with a foreground `sleep`.** Ran `sleep 240` to pace a
status check; the harness killed it at 120s and took the run's process group
with it. Both codex lanes recorded ERROR at an identical 309.3s — that identical
elapsed is the signature of an external kill, not two independent failures.
Never foreground-sleep beside a live run; use `run_in_background` with an
until-loop, or just wait for the completion notification.

**A check that is strict on FORMAT fails honest work.** The round-3
test-integrity lane did everything asked — four mutations, verbatim pytest
output, a provenance audit of every new test — and failed its check twice. My
regex demanded pytest summary lines at line start (`^\s*\d+ passed`), and the
worker had written them inside markdown bullets (`- Baseline: \`122 passed…\``).
The skill already says strict on substance, tolerant on format; I wrote the
check anyway. Anchor on the substance (`\d+ (passed|failed)` anywhere in the
line), never on layout.

**Re-run cost of that mistake: ~250k tokens and 15 minutes**, for a report whose
content was correct the first time.

**GLM 5.2 confirmed on blast/contract lanes, second run in a row.** Passed
first-try while both codex lanes were in trouble, and its finding (a writer-list
count saying six where the grep returns seven) was the only real defect any lane
found this round. Two rounds, two wins on this surface — promote it from
"try it" to the default for contract/blast-area lanes on intake.


## GPT-5.6 Sol

- 2026-08-20 code-review (intake PR #639, test-integrity lane, executed mutation audit). Best-value lane of the run: 10 mutations applied one at a time to `src/`, each re-run against the targeted suite and twice against the full 3463-test suite, all reverted, tee'd to a log my check could read. Found 2 of 10 protections unpinned and I reproduced both by hand — correct. Also self-reported honestly that the sandbox denied `git checkout --` (shared git index outside the writable root) and that it reverted with `apply_patch` plus an empty `git diff --exit-code` instead, and that the full-suite failure it saw differed from the one the PR body named. Two sandbox flags were required and are worth reusing: `-c sandbox_workspace_write.network_access=true` for `uv sync`, and telling the worker to `export UV_CACHE_DIR="$PWD/.uvcache"` because uv's global cache is outside the writable root. Without both the lane dies before running a single test.

### MiniMax M3 (free) — openrouter/minimax/minimax-m3:free
- 2026-08-25 code-review (intake PR #728, frontend-ux lane). AUDITION ABORTED, not
  failed on merit: both attempts died instantly with OpenRouter 404 "No endpoints
  available matching your guardrail restrictions and data policy". Zero tokens, 2.2s.
  This is an account-level privacy/data-policy setting, not a model capability
  signal. Do not read the 0% row as evidence about the model. Before auditioning any
  `:free` OpenRouter model again, check that endpoints exist under the current
  privacy settings — a one-task manifest costs 2s to find out.

### Nemotron 3.5 Lightning (free) — openrouter/nvidia/nemotron-3.5-lightning:free
- 2026-08-25 code-review (intake PR #728, docs-truth lane). AUDITION ABORTED, same
  OpenRouter 404 as MiniMax M3 above: "No endpoints available matching your guardrail
  restrictions and data policy", both attempts, 3.4s, zero tokens. Again not a
  capability signal — do not read the 0% row as evidence about the model.

  **The orchestrator lesson, not the model's.** The MiniMax entry directly above,
  written the same day, already says to check endpoint availability before
  auditioning any `:free` OpenRouter model. I picked another `:free` model without
  checking and lost the lane plus a restart. The guardrail setting is account-level,
  so it will reject EVERY `:free` slug until the privacy settings change — this is
  not a per-model gamble. Until then, spend exploration slots on paid-but-cheap
  candidates, or fix the setting once at
  https://openrouter.ai/settings/privacy and re-audition the backlog.
- 2026-08-28 code-review (intake PR #737, correctness lane, codex high): 1 attempt, 123k tokens, 5m13s. Found the one real P2 (malformed child cell falls through Alt to the loan's value) with an executed probe; confirmed by hand. Correctly judged the author's deliberate reversal of the issue's guard 2.
- 2026-08-28 code-review (intake PR #737, test-integrity lane, codex medium): 1 attempt, 282k tokens, 21m. Nine mutations in a cp'd sandbox, all restored with proven diffs; found 1 unpinned claim (merge precedence). Lesson: PYTHONPATH did NOT beat the editable install for this worker — it used `-o pythonpath=$PWD/src`; put that flag in the spec next time.

## GLM 5.2 (continued)

- 2026-08-25 code-review (intake PR #728, round 3, two lanes). Frontend lane passed on
  attempt 2 over a 2,606-line component and produced the round's second-best finding —
  an undo path that clears its suppression tokens before refetching, so a lagging index
  repaints the value undo just reversed. It also correctly RETRACTED a prior round's
  finding on the evidence ("the earlier 'three of four classes had no rule' finding is
  no longer true") and flagged its own unverified premise in Assumptions rather than
  asserting it. Picked up the docs-truth lane after the free model 404'd and passed
  first try, catching a false AGENTS.md invariant plus the test that pins the defect in
  place. Third and fourth wins on intake review surfaces; the "default for
  contract/blast-area lanes" call above now extends to frontend and docs-truth.

- 2026-08-27 code-review (pr734 blast-area, glm-5.2): 1 attempt, thorough caller/geometry/ADR sweep with executed test counts; report accepted as-is.
- 2026-08-27 code-review (pr734 test-integrity, codex): sandbox refused writes to the supplied worktree; worker made its own clone in /private/tmp and finished. Give codex lanes a scratch path it can write, and clean /private/tmp after. Orchestrator check regex expected "=" decorated pytest summaries; under -q there are none — match "N failed" plainly.
- 2026-08-28 code-review (intake PR #737, blast-area lane, glm-5.2): 1 attempt, 70k tokens, 4m24s. Swept all five Children sites, _walk_validate gating, removal consumers, ADR_INT-068 §7/§8 body; ran the delivery test sweep and correctly diagnosed 3 failures as cwd fixture-path artifacts. No findings, all confirmed. Report accepted as-is.

## DeepSeek V4 Flash (`openrouter/deepseek/deepseek-v4-flash`)
- 2026-08-27 code-review (intake PR #728 round 15, verifier lane, `openrouter/deepseek/deepseek-v4-flash`, $0.03/M in): PASSED — full revert-proof report (R1–R7 + E1–E6), all verdicts agreed with the GLM 5.2 lane on the same spec, no fabricated findings. It missed the four P3s GLM found (redundant-guard isolation, dead allowlist entries, missing 409 fixture shape), so it is a good second lane, not yet a sole verifier. First paid cheap explorer to complete on this PR after the free tiers were blocked by the account data policy.
- 2026-08-27 code-review (intake PR #728 round 16, same spec as GLM 5.2, first try): PASSED and matched GLM finding-for-finding — the same P2 (`TransactionConflict` not retried) and the same P3 (unreached durability guard), with line-level evidence and a correct "self-heals on client retry" impact note GLM omitted. Two rounds, two first-try passes, zero fabrications: promote to a full verifier lane for code-review on this repo, paired with GLM until three rounds.
