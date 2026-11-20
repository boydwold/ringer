#!/bin/bash
# Ringer engine wrapper for Google Antigravity's command line (agy), Linux only.
#
# agy's own --sandbox flag does not stop writes outside the task dir: a probe on
# a Linux host (2026-11-19) wrote outside the task folder from inside it. So this wrapper runs agy in
# bubblewrap: the whole filesystem read-only, writes only to the task dir, a
# per-run scratch dir and agy's own state dir, and the usual credential folders
# hidden. The network stays open: agy must reach Google.
#
# Usage (as a ringer engine bin):
#   agy-sandboxed.sh <taskdir> [--no-sandbox] <agy args...>
# "--no-sandbox" as the second argument skips containment; wire it as the
# engine's full_access_args so ringer's allow_full_access gate still applies.
set -euo pipefail

TASKDIR="${1:?usage: agy-sandboxed.sh <taskdir> [--no-sandbox] <agy args...>}"; shift
SANDBOX=1
if [ "${1:-}" = "--no-sandbox" ]; then SANDBOX=0; shift; fi

AGY_BIN="${AGY_BIN:-$(command -v agy || true)}"
if [ -z "$AGY_BIN" ] || [ ! -x "$AGY_BIN" ]; then
  echo "agy-sandboxed.sh: no executable AGY_BIN or agy on PATH" >&2
  exit 127
fi
AGY_BIN="$(readlink -f -- "$AGY_BIN")"
TASKDIR_REAL="$(cd -P -- "$TASKDIR" && pwd -P)"
cd "$TASKDIR_REAL"

if [ "$SANDBOX" = 0 ]; then
  exec "$AGY_BIN" "$@" < /dev/null
fi

if [ "$(uname -s)" != Linux ] || ! command -v bwrap > /dev/null; then
  echo "agy-sandboxed.sh: needs Linux and bwrap; refusing to run unsandboxed" >&2
  exit 1
fi

AGY_STATE="$HOME/.gemini/antigravity-cli"
mkdir -p "$AGY_STATE"
AGY_STATE="$(cd -P -- "$AGY_STATE" && pwd -P)"
SCRATCH="$(mktemp -d "${TMPDIR:-$HOME/tmp}/ringer-agy.XXXXXX")"
trap 'rm -rf -- "$SCRATCH"' EXIT

args=(--ro-bind / / --dev /dev --proc /proc --tmpfs /tmp
  --die-with-parent --new-session)

# Hide credential folders a worker never needs. A folder is hidden with an
# empty tmpfs, a file or socket with /dev/null.
hide() {
  local p real
  for p in "$@"; do
    [ -e "$p" ] || [ -L "$p" ] || continue
    real="$(readlink -f -- "$p")" || continue
    # A dangling symlink has nothing behind it to hide.
    [ -e "$real" ] || continue
    if [ -d "$real" ]; then
      args+=(--tmpfs "$real")
    else
      args+=(--ro-bind /dev/null "$real")
    fi
  done
}
hide "$HOME/.ssh" "$HOME/.1password" "$HOME/.gnupg" "$HOME/.aws" \
  "$HOME/.config/op" "$HOME/.config/ringer" "$HOME/.config/gh" \
  "$HOME/.local/share/opencode" "$HOME/.local/state/opencode" \
  "$HOME/.codex" "$HOME/.claude" "$HOME/.claude.json" "$HOME/.coderabbit" \
  "$HOME/.local/share/keyrings" "$HOME/.git-credentials" "$HOME/.netrc" \
  "$HOME/.docker/config.json" "$HOME/.kube" \
  /run/tailscale/tailscaled.sock /var/run/tailscale/tailscaled.sock
# The ssh agent sockets in the runtime dir.
for sock in "/run/user/$(id -u)/ssh-agent.socket" "/run/user/$(id -u)/gnupg" \
            "/run/user/$(id -u)/keyring"; do
  hide "$sock"
done
[ -n "${SSH_AUTH_SOCK:-}" ] && hide "$SSH_AUTH_SOCK"

# Writable places, mounted last so a hide above cannot cover them.
args+=(--bind "$AGY_STATE" "$AGY_STATE"
  --bind "$TASKDIR_REAL" "$TASKDIR_REAL"
  --bind "$SCRATCH" "$SCRATCH"
  --chdir "$TASKDIR_REAL"
  --setenv TMPDIR "$SCRATCH"
  --unsetenv SSH_AUTH_SOCK)

echo "[ringer-sandbox] agy in bwrap: writes limited to the task dir, scratch and $AGY_STATE" >&2
bwrap "${args[@]}" "$AGY_BIN" "$@" < /dev/null
