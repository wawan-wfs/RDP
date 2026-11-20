#!/usr/bin/env bash
# Read-only local XRDP status; does not change PAM, users, or packages.
set -u
account="${1:-RDP}"
if [[ ! "$account" =~ ^[a-zA-Z_][a-zA-Z0-9_-]*$ ]]; then
  printf 'Usage: %s [local-account]\n' "$0" >&2
  exit 2
fi
printf 'XRDP/Xorg/Xfce local diagnosis\nAccount requested: %s\n' "$account"
if getent passwd "$account" >/dev/null; then
  printf 'Account: found\n'
else
  printf 'Account: not found (check exact case)\n'
fi
if command -v systemctl >/dev/null 2>&1; then
  for unit in xrdp.service xrdp-sesman.service tailscaled.service; do
    status=$(systemctl is-active "$unit" 2>/dev/null) || true
    printf '%s: %s\n' "$unit" "${status:-unknown}"
  done
fi
for program in Xorg startxfce4 chromium; do
  if command -v "$program" >/dev/null 2>&1; then
    printf '%s: found\n' "$program"
  else
    printf '%s: not in PATH\n' "$program"
  fi
done
if command -v ss >/dev/null 2>&1; then
  listeners=$(ss -H -ltn 'sport = :3389' 2>/dev/null) || listeners=''
  if [[ -n "$listeners" ]]; then
    printf 'Local TCP 3389: listening\n'
  else
    printf 'Local TCP 3389: no visible listener\n'
  fi
fi
printf 'Local checks only. For session errors inspect journalctl -u xrdp -u xrdp-sesman.\n'
