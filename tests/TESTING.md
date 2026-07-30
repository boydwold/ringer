# Test recipes

## Fast tier while you edit

The full suite takes about 50 seconds, and four modules account for over half of
it — `test_ringer`, `test_agent_install`, `test_self_update`, `test_mock_engine`.
Together that is 36 of 253 tests and 27.7 seconds. They are slow because they
spawn real subprocesses, which is correct: you cannot unit-test signal handling
or process-group cleanup by mocking it.

While iterating, skip that tier:

```bash
RINGER_FAST_TESTS=1 python3 -m unittest discover -s tests     # ~20s
```

**CI leaves the variable unset and runs everything.** Nothing about the gate
changes; this only shortens the local edit loop.

**Better still, run only what your change touches.** A one-module run is a
fraction of a second:

```bash
python3 -m unittest tests.test_contributors                   # 0.04s
```

Reaching for the whole suite on every edit is the slow path, and it is a habit
worth breaking before it is a tool worth optimising. A change to `README.md`
cannot break 253 tests — run the tests that read `README.md`.

## `ringer.py ask`

Status: tested

Purpose: verify context-packet selection, one-worker execution, opt-in request
redaction, Ringside state, artifact registration, and the one-attempt contract.

Safe actions:

- Run the unit suite; worker tests use temporary directories and local Python
  fixture workers.
- Run `ask --dry-run` against temporary text or Markdown sources.

Unsafe actions:

- Do not omit `--dry-run` from a smoke command unless a real model call is
  intended.

Verification steps:

1. Run `RINGER_NO_SELF_UPDATE=1 python3 -m unittest discover -s tests`.
2. Create a temporary Markdown source containing a distinctive answer passage.
3. Run `RINGER_NO_SELF_UPDATE=1 python3 ./ringer.py ask "<question>" --source
   <temp-file> --dry-run`.
4. Confirm the packet report names the source passage and stdout says
   `No model call was made.`

Cleanup:

- Remove the temporary source and generated request directory when one was
  supplied explicitly.

Known test-environment constraint:

- Worker tests mock only the dashboard socket bind because restricted test
  sandboxes can reject local listeners. They assert that the run records a
  dashboard port and enters the artifact library.
