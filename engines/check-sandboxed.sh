#!/bin/bash
# Run a bounded, offline check with filesystem writes confined to its task.
# Usage: check-sandboxed.sh <taskdir> <timeout_s> <command...>
set -euo pipefail

if [ "$#" -lt 3 ]; then
  echo "usage: check-sandboxed.sh <taskdir> <timeout_s> <command...>" >&2
  exit 1
fi
TASKDIR="$1"
TIMEOUT_S="$2"
shift 2

OS="$(uname -s)"
if [ "$OS" != Linux ]; then
  echo "[ringer-sandbox] check sandbox unsupported on $OS" >&2
  exit 1
fi
BWRAP="${RINGER_SANDBOX_BWRAP:-bwrap}"
if ! BWRAP="$(command -v "$BWRAP")" || [ ! -f "$BWRAP" ] || [ ! -x "$BWRAP" ]; then
  echo "[ringer-sandbox] bwrap not found or not executable: ${RINGER_SANDBOX_BWRAP:-bwrap}" >&2
  exit 1
fi
TASKDIR_REAL="$(cd "$TASKDIR" && pwd -P)"
RUNTIME_DIR="/run/user/$(id -u)"
# Bind first so bwrap can create mountpoint parents in the private tmpfs mounts.
# Then seal those mounts: otherwise writes beside a task under /tmp succeed in
# the private filesystem. Remounting is nonrecursive, keeping the task writable.
args=(--unshare-net --ro-bind / / --dev /dev --proc /proc
  --tmpfs /tmp --tmpfs "$RUNTIME_DIR"
  --bind "$TASKDIR_REAL" "$TASKDIR_REAL"
  --remount-ro /tmp --remount-ro "$RUNTIME_DIR"
  --unshare-pid --unshare-ipc --die-with-parent --new-session
  --chdir "$TASKDIR_REAL")

if ! "$BWRAP" "${args[@]}" /usr/bin/true < /dev/null; then
  echo "[ringer-sandbox] bwrap check sandbox setup failed (check mounts and namespace support)" >&2
  exit 1
fi
status=0
timeout --kill-after=5 "$TIMEOUT_S" "$BWRAP" "${args[@]}" "$@" < /dev/null || status=$?
if [ "$status" -eq 124 ]; then
  echo "[ringer-sandbox] check timed out after $TIMEOUT_S seconds" >&2
  exit 124
fi
exit "$status"
