#!/bin/bash
# Ringer engine wrapper: macOS Seatbelt or Linux bubblewrap containment.
#
# OpenCode has no OS-level sandbox of its own — headless permission approval
# (--auto on 1.18.x, --dangerously-skip-permissions on older versions) disables
# interactive prompts. This wrapper supplies containment: network and reads,
# writes confined to the task dir, a per-run scratch/cache dir, and OpenCode's
# own state dirs.
#
# Usage (as a ringer engine bin):
#   opencode-sandboxed.sh <taskdir> [--no-sandbox] <opencode args...>
#
# The first argument is the task directory (pass "{taskdir}" first in
# args_template). "--no-sandbox" as the second argument skips containment entirely
# — wire it as the engine's full_access_args so ringer's allow_full_access gate
# still applies. Linux requires bwrap and working unprivileged namespaces;
# macOS requires sandbox-exec. Other platforms fail closed.
set -euo pipefail

TASKDIR="${1:?usage: opencode-sandboxed.sh <taskdir> [--no-sandbox] <args...>}"; shift
SANDBOX=1
if [ "${1:-}" = "--no-sandbox" ]; then SANDBOX=0; shift; fi

# Resolve opencode without tripping `set -e` (command -v returns nonzero when absent).
if [ -z "${OPENCODE_BIN:-}" ] || [ ! -f "$OPENCODE_BIN" ] || [ ! -x "$OPENCODE_BIN" ]; then
  if ! OPENCODE_BIN="$(command -v opencode)" || [ ! -f "$OPENCODE_BIN" ] || [ ! -x "$OPENCODE_BIN" ]; then
    echo "opencode-sandboxed.sh: no executable OPENCODE_BIN or opencode on PATH" >&2
    exit 127
  fi
fi

if [ "$SANDBOX" = "0" ]; then
  exec "$OPENCODE_BIN" "$@" < /dev/null
fi

run_darwin() {
if [ ! -x /usr/bin/sandbox-exec ]; then
  echo "opencode-sandboxed.sh: /usr/bin/sandbox-exec not available (macOS only)." >&2
  echo "Use the engine's full-access mode (--no-sandbox) or add your own sandbox." >&2
  exit 1
fi

TASKDIR_REAL="$(cd "$TASKDIR" && pwd -P)"

# Per-run scratch root — becomes both TMPDIR and XDG_CACHE_HOME for OpenCode, so
# we never have to open all of /private/tmp or ~/.cache to the sandboxed agent.
# Resolve to the real path (/var/folders symlinks to /private/var/folders);
# Seatbelt subpath matching needs the canonical path or writes EPERM-crash.
SCRATCH="$(cd "$(mktemp -d -t ringer-opencode-scratch)" && pwd -P)"
PROFILE="$(mktemp -t ringer-opencode-prof)"
cleanup() { rm -rf "$SCRATCH" "$PROFILE"; }
trap cleanup EXIT

# Paths are passed to the profile via sandbox-exec -D parameters, NOT string
# interpolation — a task dir containing quotes/parens/newlines can't inject rules.
cat > "$PROFILE" <<'SBEOF'
(version 1)
(allow default)
(deny file-write*)
(allow file-write*
  (subpath (param "TASKDIR"))
  (subpath (param "SCRATCH"))
  (subpath (param "OC_SHARE"))
  (subpath (param "OC_STATE")))
; OC_CONFIG is readable, never writable. On 2026-09-05 two workers edited
; ~/.config/opencode/opencode.jsonc to add "edit": "allow" and "bash": "allow",
; then put it back. A sandboxed worker must not be able to rewrite the
; permission file that governs it. `(allow default)` still permits the read.
; /dev is needed for /dev/null, /dev/urandom, etc.; writes there can't create
; persistent files without root, so a few literals are allowed rather than via param.
(allow file-write-data
  (literal "/dev/null")
  (literal "/dev/dtracehelper")
  (literal "/dev/tty"))
; A file rule alone does not contain this sandbox. `open <bundle>` asks
; LaunchServices to start the process, launchd spawns it, and the new process
; is not our child, so the profile never applies to it. On 2026-09-05 a worker
; used exactly that to write into a herdr worktree. Deny the LaunchServices
; ports and the route closes for every binary, not just /usr/bin/open.
; `launchctl` uses com.apple.xpc.launchd, denied here for the same reason.
(deny mach-lookup
  (global-name "com.apple.CoreServices.coreservicesd")
  (global-name "com.apple.coreservices.launchservicesd")
  (global-name "com.apple.coreservices.quarantine-resolver")
  (global-name "com.apple.lsd.mapdb")
  (global-name "com.apple.lsd.modifydb")
  (global-name "com.apple.lsd.openurl")
  (global-name "com.apple.xpc.launchd"))
SBEOF

# Only generated integer names enter profile text; paths remain -D parameters.
HIDE_ARGS=()
hide_index=0
for hidden in ${HIDDEN_PATHS[@]+"${HIDDEN_PATHS[@]}"}; do
  printf '(deny file-read* (subpath (param "HIDE_%d")))\n' "$hide_index" >> "$PROFILE"
  HIDE_ARGS+=(-D "HIDE_$hide_index=$hidden")
  hide_index=$((hide_index + 1))
done

export TMPDIR="$SCRATCH"
export XDG_CACHE_HOME="$SCRATCH/cache"
mkdir -p "$XDG_CACHE_HOME"

# Run as a child (not exec) so the EXIT trap fires and cleans up the profile +
# scratch dir even on the success path; propagate the child's exit status.
set +e
/usr/bin/sandbox-exec \
  ${HIDE_ARGS[@]+"${HIDE_ARGS[@]}"} \
  -D "TASKDIR=$TASKDIR_REAL" \
  -D "SCRATCH=$SCRATCH" \
  -D "OC_SHARE=$HOME/.local/share/opencode" \
  -D "OC_STATE=$HOME/.local/state/opencode" \
  -f "$PROFILE" "$OPENCODE_BIN" "$@" < /dev/null
status=$?
set -e
exit "$status"
}

run_linux() {
  local BWRAP="${RINGER_SANDBOX_BWRAP:-bwrap}"
  if ! BWRAP="$(command -v "$BWRAP")" || [ ! -f "$BWRAP" ] || [ ! -x "$BWRAP" ]; then
    echo "[ringer-sandbox] bwrap not found or not executable: ${RINGER_SANDBOX_BWRAP:-bwrap}" >&2
    exit 1
  fi

  TASKDIR_REAL="$(cd "$TASKDIR" && pwd -P)"
  OPENCODE_BIN="$(readlink -f -- "$OPENCODE_BIN")"
  local OC_SHARE="$HOME/.local/share/opencode"
  local OC_STATE="$HOME/.local/state/opencode"
  SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/ringer-opencode.XXXXXX")"
  trap 'rm -rf -- "$SCRATCH"' EXIT
  SCRATCH="$(cd "$SCRATCH" && pwd -P)"
  mkdir -p -- "$OC_SHARE" "$OC_STATE" "$SCRATCH/cache"

  local runtime_dir="/run/user/$(id -u)"
  local home_real
  home_real="$(cd "$HOME" && pwd -P)"
  local -a args=(--ro-bind / / --dev /dev --proc /proc
    --tmpfs /tmp --tmpfs "$runtime_dir")
  # Temporary homes and executables must remain readable even when /tmp is
  # masked (also useful for isolated test fixtures). Restore only these inputs.
  case "$home_real" in
    /tmp/*|"$runtime_dir"/*) args+=(--ro-bind "$home_real" "$home_real") ;;
  esac
  case "$OPENCODE_BIN" in
    /tmp/*|"$runtime_dir"/*) args+=(--ro-bind "$OPENCODE_BIN" "$OPENCODE_BIN") ;;
  esac
  args+=(--bind "$TASKDIR_REAL" "$TASKDIR_REAL" --bind "$SCRATCH" "$SCRATCH"
    --bind "$OC_SHARE" "$OC_SHARE" --bind "$OC_STATE" "$OC_STATE")
  local hidden
  for hidden in "${HIDDEN_PATHS[@]}"; do
    if [ -d "$hidden" ]; then
      args+=(--tmpfs "$hidden")
    elif [ -f "$hidden" ]; then
      args+=(--ro-bind /dev/null "$hidden")
    fi
  done
  args+=(--unshare-pid --unshare-ipc --die-with-parent --new-session
    --chdir "$TASKDIR_REAL"
    --unsetenv DBUS_SESSION_BUS_ADDRESS --unsetenv SSH_AUTH_SOCK
    --unsetenv DISPLAY --unsetenv WAYLAND_DISPLAY)
  local variable
  for variable in "${!HERDR_@}"; do
    args+=(--unsetenv "$variable")
  done
  args+=(--setenv TMPDIR "$SCRATCH" --setenv XDG_CACHE_HOME "$SCRATCH/cache")

  # Exercise all mounts/namespaces before starting the worker. A setup error
  # must never fall back to running it directly or masquerade as its exit code.
  if ! "$BWRAP" "${args[@]}" /usr/bin/true < /dev/null; then
    echo "[ringer-sandbox] bwrap sandbox setup failed (check mounts and namespace support)" >&2
    exit 1
  fi
  local status=0
  "$BWRAP" "${args[@]}" "$OPENCODE_BIN" "$@" < /dev/null || status=$?
  exit "$status"
}

OS="$(uname -s)"
case "$OS" in
  Darwin|Linux) ;;
  *) echo "[ringer-sandbox] unsupported platform: $OS" >&2; exit 1 ;;
esac

# Split on colons without treating whitespace, newlines, or glob characters in
# a path as shell syntax. Empty entries are ignored; relative paths are errors.
HIDDEN_PATHS=()
remaining="${RINGER_SANDBOX_HIDE:-}"
while [ -n "$remaining" ]; do
  hidden="${remaining%%:*}"
  case "$remaining" in
    *:*) remaining="${remaining#*:}" ;;
    *) remaining= ;;
  esac
  case "$hidden" in
    '') continue ;;
    /*) HIDDEN_PATHS+=("$hidden") ;;
    *) echo "[ringer-sandbox] RINGER_SANDBOX_HIDE requires absolute paths: $hidden" >&2; exit 1 ;;
  esac
done

case "$OS" in
  Darwin) run_darwin "$@" ;;
  Linux) run_linux "$@" ;;
esac
