#!/usr/bin/env bash
# Read-only inspection of a local macOS GUI session.
set -u
[[ "$(uname -s)" == Darwin ]] || { printf 'Run this on macOS.\n' >&2; exit 2; }
target="${1:-$(id -un)}"
if [[ ! "$target" =~ ^[a-zA-Z_][a-zA-Z0-9_.-]*$ ]]; then
  printf 'Usage: %s [local-account]\n' "$0" >&2
  exit 2
fi
uid=$(id -u "$target" 2>/dev/null) || { printf 'Unknown user: %s\n' "$target" >&2; exit 2; }
console=$(stat -f '%Su' /dev/console 2>/dev/null) || console=unknown
printf 'SSH/shell user: %s\nConsole user: %s\nTarget user: %s (UID %s)\n' "$(id -un)" "$console" "$target" "$uid"
if launchctl print "gui/$uid" >/dev/null 2>&1; then
  printf 'GUI domain: visible\n'
else
  printf 'GUI domain: absent or not readable to this session\n'
fi
for proc in loginwindow Finder Dock SystemUIServer; do
  if pgrep -x -u "$uid" "$proc" >/dev/null 2>&1; then
    printf '%s: running for target\n' "$proc"
  else
    printf '%s: not found for target\n' "$proc"
  fi
done
printf 'An active GUI domain is not proof that a VNC client can view or control it.\n'
