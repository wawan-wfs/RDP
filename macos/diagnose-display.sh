#!/usr/bin/env bash
# Read-only display and Screen Sharing service summary.
set -u
[[ "$(uname -s)" == Darwin ]] || { printf 'Run this on macOS.\n' >&2; exit 2; }
printf 'macOS %s / %s\n' "$(sw_vers -productVersion)" "$(uname -m)"
for proc in WindowServer ARDAgent screensharingd; do
  if pgrep -x "$proc" >/dev/null 2>&1; then
    printf '%s: seen\n' "$proc"
  else
    printf '%s: not seen\n' "$proc"
  fi
done
# Show display count and resolutions only. Do not emit serial numbers.
if command -v system_profiler >/dev/null 2>&1; then
  LC_ALL=C system_profiler SPDisplaysDataType -detailLevel mini 2>/dev/null |
    awk '/^[[:space:]]+Resolution: / {sub(/^[[:space:]]+/, ""); print; found=1} END {if (!found) print "Resolution: unavailable"}'
fi
