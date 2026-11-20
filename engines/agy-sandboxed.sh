#!/bin/bash
# Ringer engine wrapper for Google Antigravity's command line (agy), Linux only.
#
# agy's own --sandbox flag does not stop writes outside the task dir: a probe on
# a Linux host (2026-11-19) wrote outside the task folder from inside it. So this wrapper runs agy in
# bubblewrap: the whole filesystem read-only, the home folder and the user
# runtime dir empty, writes only to the task dir, a per-run scratch dir and
# agy's own state dir. The network stays open: agy must reach Google.
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

RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
AGY_INSTALL="$(dirname -- "$AGY_BIN")"

# The whole filesystem read-only, then three things are made empty:
#   $HOME        - so no credential file, token or browser profile is readable.
#                  A hide list missed ~/.homelab-env and ~/.npmrc (refute pass,
#                  2026-11-19), so the home folder is now empty by default.
#   runtime dir  - the user D-Bus lives there. Through it, `systemd-run --user`
#                  starts a process outside the sandbox, and the Secret Service
#                  hands out keyring items.
#   /tmp         - a private, empty /tmp.
args=(--ro-bind / / --dev /dev --proc /proc --tmpfs /tmp
  --tmpfs "$HOME" --tmpfs "$RUNTIME_DIR"
  --die-with-parent --new-session)

# Sockets outside $HOME and the runtime dir.
for p in /run/tailscale/tailscaled.sock /var/run/tailscale/tailscaled.sock; do
  real="$(readlink -f -- "$p" 2>/dev/null)" || continue
  [ -e "$real" ] && args+=(--ro-bind /dev/null "$real")
done

# agy keeps its login in the keyring (service "gemini", user "antigravity").
# The full user bus would also let a worker run `systemd-run --user` (a process
# outside the sandbox) and read every keyring item. So agy gets a filtered bus:
# xdg-dbus-proxy passes only the calls agy makes (logged 2026-11-19), and
# GetSecret only on agy's own item.
command -v xdg-dbus-proxy > /dev/null || {
  echo "agy-sandboxed.sh: needs xdg-dbus-proxy for the agy login; refusing to run" >&2; exit 1; }
SEC=org.freedesktop.secrets
item="$(busctl --user call "$SEC" /org/freedesktop/secrets/aliases/default \
  org.freedesktop.Secret.Collection SearchItems 'a{ss}' 2 service gemini username antigravity \
  2>/dev/null | grep -oE '"/org/freedesktop/secrets/collection/[^"]+"' | head -1 | tr -d '"')"
if [ -z "$item" ]; then
  echo "agy-sandboxed.sh: no agy login in the keyring; run agy once outside Ringer to sign in" >&2
  exit 1
fi
mkdir -p "$SCRATCH/bus"
BUS="$SCRATCH/bus/bus"
xdg-dbus-proxy "$DBUS_SESSION_BUS_ADDRESS" "$BUS" --filter \
  --call="$SEC=org.freedesktop.DBus.Properties.Get@/org/freedesktop/secrets" \
  --call="$SEC=org.freedesktop.Secret.Service.OpenSession@/org/freedesktop/secrets" \
  --call="$SEC=org.freedesktop.Secret.Service.Unlock@/org/freedesktop/secrets" \
  --call="$SEC=org.freedesktop.Secret.Collection.SearchItems@/org/freedesktop/secrets/aliases/default" \
  --call="$SEC=org.freedesktop.Secret.Item.GetSecret@$item" \
  --call="$SEC=org.freedesktop.Secret.Session.Close@/org/freedesktop/secrets/session/*" &
PROXY_PID=$!
trap 'kill "$PROXY_PID" 2>/dev/null; rm -rf -- "$SCRATCH"' EXIT
for _ in $(seq 50); do [ -S "$BUS" ] && break; sleep 0.1; done
[ -S "$BUS" ] || { echo "agy-sandboxed.sh: the bus filter did not start" >&2; exit 1; }

# What agy needs, put back on top of the empty $HOME. Mounted last so the
# tmpfs above cannot cover them.
args+=(--ro-bind "$AGY_INSTALL" "$AGY_INSTALL")
for f in "$HOME/.gemini/settings.json" "$HOME/.gemini/config"; do
  [ -e "$f" ] && args+=(--ro-bind "$f" "$f")
done
args+=(--bind "$AGY_STATE" "$AGY_STATE"
  --bind "$TASKDIR_REAL" "$TASKDIR_REAL"
  --bind "$SCRATCH" "$SCRATCH"
  --chdir "$TASKDIR_REAL"
  --setenv TMPDIR "$SCRATCH"
  --setenv HOME "$HOME"
  --unsetenv SSH_AUTH_SOCK
  --setenv DBUS_SESSION_BUS_ADDRESS "unix:path=$BUS"
  --unsetenv XDG_RUNTIME_DIR)

echo "[ringer-sandbox-note] agy in bwrap: writes limited to the task dir, scratch and $AGY_STATE" >&2
bwrap "${args[@]}" "$AGY_BIN" "$@" < /dev/null
