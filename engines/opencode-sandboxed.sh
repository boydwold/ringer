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

# OpenCode 2.x removed `run --dir` and rejects it ("Unrecognized flag: --dir").
# Ringer starts the worker in the task dir already, so a `--dir` naming the
# task dir is redundant on every version: drop it. Any other `--dir` value
# passes through unchanged, and OpenCode reports it. The last argument is the
# prompt (`{spec}`), so it is never read as a flag or removed.
same_dir() {
  [ -d "$1" ] && [ -d "$2" ] && [ "$(cd "$1" && pwd -P)" = "$(cd "$2" && pwd -P)" ]
}
args_in=("$@")
n_args=${#args_in[@]}
filtered=()
i=0
while [ "$i" -lt "$n_args" ]; do
  arg="${args_in[$i]}"
  if [ "$i" -lt $((n_args - 1)) ]; then
    if [ "$arg" = "--dir" ] && [ "$i" -lt $((n_args - 2)) ] &&
       same_dir "${args_in[$((i + 1))]}" "$TASKDIR"; then
      i=$((i + 2))
      continue
    fi
    case "$arg" in
      --dir=*) if same_dir "${arg#--dir=}" "$TASKDIR"; then i=$((i + 1)); continue; fi ;;
    esac
  fi
  filtered+=("$arg")
  i=$((i + 1))
done
set -- ${filtered[@]+"${filtered[@]}"}

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

# OpenCode 2.x runs through a shared background service and records it in
# ~/.config/opencode/service.json, which stays read-only in the sandbox (EPERM).
# `--standalone` gives this worker a private server instead; 1.x lacks the flag.
# RINGER_OPENCODE_STANDALONE=1 or 0 forces the choice. Otherwise the wrapper
# asks `opencode --version` (outside the sandbox, at most 10 s) for the major
# version. The last argument is the prompt and is not checked for the flag.
opencode_major() {
  local out pid tries=0 line
  out="$(mktemp "${TMPDIR:-/tmp}/ringer-oc-version.XXXXXX")"
  "$OPENCODE_BIN" --version > "$out" 2> /dev/null < /dev/null &
  pid=$!
  while kill -0 "$pid" 2> /dev/null && [ "$tries" -lt 50 ]; do
    sleep 0.2
    tries=$((tries + 1))
  done
  if kill -0 "$pid" 2> /dev/null; then
    kill "$pid" 2> /dev/null || true
    echo "[ringer-sandbox] opencode --version did not answer in 10 s; not adding --standalone" >&2
  fi
  wait "$pid" 2> /dev/null || true
  line="$(head -n 1 "$out")"
  rm -f "$out"
  if [[ "$line" =~ ([0-9]+)\.[0-9]+ ]]; then echo "${BASH_REMATCH[1]}"; fi
}
if [ "${1:-}" = "run" ]; then
  add_standalone=0
  case "${RINGER_OPENCODE_STANDALONE:-auto}" in
    1) add_standalone=1 ;;
    0) ;;
    *)
      major="$(opencode_major)"
      if [ -n "$major" ] && [ "$major" -ge 2 ]; then add_standalone=1; fi
      ;;
  esac
  if [ "$add_standalone" = "1" ]; then
    j=1
    while [ "$j" -lt "$#" ]; do
      if [ "${!j}" = "--standalone" ]; then add_standalone=0; fi
      j=$((j + 1))
    done
  fi
  if [ "$add_standalone" = "1" ]; then
    shift
    set -- run --standalone "$@"
  fi
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

# A run killed with SIGKILL skips its EXIT trap, so its scratch dir, with the
# auth.json copy and the provider keys file, stays on disk. Remove such dirs
# from earlier runs in the same parent dir. Each run holds a flock on its own
# scratch dir (the directory itself, which the worker cannot replace), so a
# dir is removed only when no live run holds that lock; the removal runs under
# it. Only real dirs that this user owns and that are named like ours are
# touched. A dir with the .ringer-lock marker was locked by its owner, so a
# free lock means a dead run. A dir without the marker may belong to a wrapper
# that never locks (an older version, or no flock), so it is removed only
# after a day. A dir that cannot be removed never stops this run. The lock is
# taken on "$dir/.", so if a worker swaps the name for a symlink in between,
# the open fails instead of creating the symlink's target.
sweep_dead_scratch() {
  local parent="$1" own="$2" dir
  while IFS= read -r -d '' dir; do
    [ "$dir" = "$own" ] && continue
    if [ ! -e "$dir/.ringer-lock" ] && [ ! -L "$dir/.ringer-lock" ]; then
      [ -n "$(find "$dir" -maxdepth 0 -mmin +1440 2> /dev/null)" ] || continue
    fi
    flock -n "$dir/." rm -rf -- "$dir" > /dev/null 2>&1 || true
  done < <(find "$parent" -mindepth 1 -maxdepth 1 -type d -user "$(id -u)" \
             -name 'ringer-opencode.??????' -print0 2> /dev/null || true)
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
  # Hold a flock on this scratch dir for the whole run. Both bwrap calls
  # close the descriptor, so the worker cannot hold or release the lock, and
  # bwrap dies with this script (--die-with-parent). The lock is on the
  # directory itself: the worker can write inside it but cannot replace it.
  # The marker file is written only after the lock is held, and only says
  # that this run locks; the sweep never opens it. The lock never waits: if
  # another process already holds it, this run goes on like a run without
  # flock (no marker, no sweep). The sweep is skipped when the scratch parent
  # is inside the task dir, because the worker can rename entries there.
  exec {SCRATCH_LOCK_FD}< "$SCRATCH"
  if command -v flock > /dev/null 2>&1 && flock -n -x "$SCRATCH_LOCK_FD"; then
    : > "$SCRATCH/.ringer-lock"
    case "${SCRATCH%/*}/" in
      "$TASKDIR_REAL"/*) ;;
      *) sweep_dead_scratch "${SCRATCH%/*}" "$SCRATCH" ;;
    esac
  fi
  mkdir -p -- "$SCRATCH/cache" "$SCRATCH/data/opencode" "$SCRATCH/state/opencode"
  if [ -f "$OC_SHARE/auth.json" ]; then
    cp -- "$OC_SHARE/auth.json" "$SCRATCH/data/opencode/auth.json"
    chmod 600 "$SCRATCH/data/opencode/auth.json"
  fi

  # OpenCode 2.2.5 also keeps provider keys in opencode.db, which stays hidden
  # here, so a --standalone worker found no provider (provider.no-route, klipsch,
  # 2026-11-01). Write each "type": "api" key from auth.json into a private
  # config file in the scratch dir (provider.<id>.options.apiKey, mode 600) and
  # point OPENCODE_CONFIG at it. Only the path goes into the environment, so the
  # tools the worker runs never inherit a key, and nothing here prints one.
  # OpenCode gives a <PROVIDER>_API_KEY variable and OPENCODE_CONFIG_CONTENT
  # priority over this file, so a key the caller set still wins. A caller's own
  # OPENCODE_CONFIG is kept as it is.
  if [ -f "$OC_SHARE/auth.json" ]; then
    if [ -n "${OPENCODE_CONFIG:-}" ]; then
      echo "[ringer-sandbox] OPENCODE_CONFIG is set; not adding provider keys from auth.json" >&2
    else
      local keys_file="$SCRATCH/ringer-provider-keys.json"
      local keys_status=0
      python3 -I -c '
import json, os, sys
try:
    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)
except Exception:
    sys.exit(3)
if not isinstance(data, dict):
    sys.exit(3)
providers = {}
for provider, entry in data.items():
    if not isinstance(provider, str) or not provider or not isinstance(entry, dict):
        continue
    key = entry.get("key")
    if entry.get("type") == "api" and isinstance(key, str) and key:
        providers[provider] = {"options": {"apiKey": key}}
if not providers:
    sys.exit(3)
fd = os.open(sys.argv[2], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="ascii") as f:
    json.dump({"provider": providers}, f)
' "$OC_SHARE/auth.json" "$keys_file" >/dev/null 2>&1 || keys_status=$?
      case "$keys_status" in
        0) export OPENCODE_CONFIG="$keys_file" ;;
        3) ;;
        *) rm -f -- "$keys_file"
           echo "[ringer-sandbox] could not pass provider keys from auth.json (python3 exit $keys_status); an OpenCode 2.2.5+ worker may fail with provider.no-route" >&2 ;;
      esac
    fi
  fi

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
  # Legacy clients may still write the default paths. If absent, create them
  # only inside the namespace. A read-only host mount cannot accept new mount
  # points, so mirror the nearest existing parents with read-only children.
  local path parent entry link
  local -a private_parents=() missing_state=()
  for path in "$OC_SHARE" "$OC_STATE"; do
    if [ ! -d "$path" ]; then
      missing_state+=("$path")
      parent="${path%/*}"
      while [ ! -d "$parent" ]; do parent="${parent%/*}"; done
      if [ "${private_parents[0]:-}" != "$parent" ]; then
        private_parents+=("$parent")
      fi
    fi
  done
  # Ancestors must be mirrored before descendants, or a later parent mount
  # would hide an already prepared child (e.g. .local and .local/share).
  if [ "${#private_parents[@]}" -eq 2 ] &&
     [ "${#private_parents[0]}" -gt "${#private_parents[1]}" ]; then
    private_parents=("${private_parents[1]}" "${private_parents[0]}")
  fi
  for parent in "${private_parents[@]}"; do
    args+=(--tmpfs "$parent")
    for entry in "$parent"/* "$parent"/.[!.]* "$parent"/..?*; do
      if [ -L "$entry" ]; then
        link="$(readlink -n -- "$entry"; printf '.')"
        args+=(--symlink "${link%.}" "$entry")
      elif [ -e "$entry" ]; then
        args+=(--ro-bind "$entry" "$entry")
      fi
    done
  done
  for path in "${missing_state[@]}"; do args+=(--dir "$path"); done
  for parent in "${private_parents[@]}"; do args+=(--remount-ro "$parent"); done
  # Empty compatibility mounts stay separate from the credential-bearing XDG
  # data directory, so the original auth.json path never reveals its copy.
  for path in "${missing_state[@]}"; do
    parent="${path%/*}"
    mkdir -p -- "$SCRATCH/legacy/${parent##*/}"
    args+=(--bind "$SCRATCH/legacy/${parent##*/}" "$path")
  done
  # Hide shared credentials/history without creating directories in the real home.
  # Restore writable task/scratch mounts afterwards, even if nested under a mask.
  if [ -d "$OC_SHARE" ]; then args+=(--tmpfs "$OC_SHARE"); fi
  if [ -d "$OC_STATE" ]; then args+=(--tmpfs "$OC_STATE"); fi
  args+=(--bind "$TASKDIR_REAL" "$TASKDIR_REAL" --bind "$SCRATCH" "$SCRATCH")
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
  args+=(--setenv TMPDIR "$SCRATCH" --setenv XDG_CACHE_HOME "$SCRATCH/cache"
    --setenv XDG_DATA_HOME "$SCRATCH/data" --setenv XDG_STATE_HOME "$SCRATCH/state")

  # Exercise all mounts/namespaces before starting the worker. A setup error
  # must never fall back to running it directly or masquerade as its exit code.
  if ! "$BWRAP" "${args[@]}" /usr/bin/true < /dev/null {SCRATCH_LOCK_FD}>&-; then
    echo "[ringer-sandbox] bwrap sandbox setup failed (check mounts and namespace support)" >&2
    exit 1
  fi
  local status=0
  "$BWRAP" "${args[@]}" "$OPENCODE_BIN" "$@" < /dev/null {SCRATCH_LOCK_FD}>&- || status=$?
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
