#!/usr/bin/env bash
# Read-only check of local Screen Sharing access and TCP reachability.
set -u
[[ "$(uname -s)" == Darwin ]] || { printf 'Run this on macOS.\n' >&2; exit 2; }
target="${1:-$(id -un)}"
if [[ ! "$target" =~ ^[a-zA-Z_][a-zA-Z0-9_.-]*$ ]] || ! id -u "$target" >/dev/null 2>&1; then
  printf 'Usage: %s [existing local-account]\n' "$0" >&2
  exit 2
fi
printf 'macOS Screen Sharing local diagnosis\nSelected account: %s\n' "$target"
for group in com.apple.access_screensharing com.apple.access_ssh; do
  result=$(dsmemberutil checkmembership -U "$target" -G "$group" 2>/dev/null) || result="${result:-unknown}"
  printf '%s: %s\n' "$group" "${result:-unknown}"
done
if /usr/bin/nc -z -G 2 -w 2 127.0.0.1 5900 </dev/null >/dev/null 2>&1; then
  printf 'Local IPv4 TCP 5900: connection accepted\n'
else
  printf 'Local IPv4 TCP 5900: did not accept connection\n'
fi
printf 'No credentials sent. This does not verify RFB negotiation, VNC login, or screen control.\n'
