# coderabbit-code-review: where it came from

Copied unchanged on 2026-11-03 from <https://github.com/coderabbitai/skills>, commit
`778c35a36e0afd2549c3fba86ec6e64afe649df3` (2026-10-31, "Clarify shared CLI discovery
and Antigravity sandbox recovery (#76)"), path `skills/code-review/`. MIT licence (see
`LICENSE`, from the same commit).

It was copied by hand, not installed with `npx skills add`. Every file was read first.
They are Markdown only: nothing runs when the skill loads. Besides the CodeRabbit CLI,
the text shows a `curl ... | sh` installer command for the user to run; the Ringer rules
tell the worker not to install anything, and to stop where the skill hands a step to the
user.

| File | sha256 |
|---|---|
| `SKILL.md` | `4fb66b130488c2d3ce940dae693090a19aec23edc425619b3df48d1bbc57480c` |
| `references/auth-recovery.md` | `ce2ac535e72ef198b3ab6e36a6c165b6de9bf6838bafc9232645c89d95ab089b` |
| `references/cli-workflows.md` | `cb480d0089b4aefec6501a5356d2de57d6fca1e9a7e5851fe4e50a68d9d57bb8` |
| `references/antigravity-sandbox.md` | `2259215248a1a6f95faecd2740a79021342c51134d4593d15bffe67adaa09743` |
| `LICENSE` | `eb7e076c386e9863a5309fb30dda1a695c0447e6b1a45325634ab84bfe9377f7` |

`tests/test_worker_skills.py` checks these hashes, so an edit to a copied file fails the
tests. To update, copy the files from a newer commit, read them, and change this table.

## Differences from the Claude plugin copy

The Claude plugin copy (`coderabbit` 1.1.1) is older. This commit adds
`references/auth-recovery.md` and `references/antigravity-sandbox.md`. It also tells the
agent to use the CLI's absolute path, to check `auth status` first, and never to start a
login on its own. The plugin copy lets the CLI start a browser login.

## Left out

- `skills/autofix/` pushes, creates pull requests, posts PR comments, and asks for
  approval of each fix. A Ringer worker runs unattended, and pushes go through Boyd's
  board, so it does not fit.
- The plugin, hook, eval and asset files. Workers need only the skill text.

## How Ringer uses it

A task opts in with `skills = ["coderabbit-code-review"]`. Ringer adds a short block of
Ringer rules, then `SKILL.md`, `references/auth-recovery.md` and
`references/cli-workflows.md`, to the end of that task's spec. The worker may run the
CodeRabbit CLI only in a `worktrees = true` run whose `repo` is listed in `config.toml`:

```toml
[worker_skills]
coderabbit_cli_repos = ["/absolute/path/to/repo"]
```

The list is empty by default. The CLI sends the reviewed code to CodeRabbit, and it uses
the signed-in session of the machine it runs on.

The rule is text in the spec, not a sandbox. Two limits apply. Codex's `workspace-write`
sandbox probably blocks the CLI's network access, so an allowed review may need
`full_access`. The opencode sandbox mounts `/` read-only, so `~/.coderabbit` stays
readable unless it is added to `RINGER_SANDBOX_HIDE`.
