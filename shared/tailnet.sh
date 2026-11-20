#!/usr/bin/env bash
# Existing signed-in CLI on dedicated machines or ephemeral connection via the Actions step.
set -euo pipefail
cd "$(dirname "$0")/.."
ts() {
  if [[ "$(uname -s)" == Linux ]]; then sudo -n "$(command -v tailscale)" "$@"; else tailscale "$@"; fi
}
ip() {
  local addr
  for ((i=0; i<30; i++)); do
    addr="$(tailscale ip -4 2>/dev/null | head -n1 || true)"
    if [[ -n "$addr" ]] && python3 shared/workspace.py ip "$addr"; then return; fi
    sleep 2
  done
  return 1
}
dns() {
  tailscale status --json | python3 -c 'import json,re,sys; s=json.load(sys.stdin); n=s["Self"]["DNSName"].rstrip("."); assert re.fullmatch(r"[a-z0-9.-]+[.]ts[.]net",n); print(n)'
}
tcp() {
  local public="$1" backend="$2"
  assert_port_free "$public"
  ts serve --bg "--tcp=$public" "tcp://127.0.0.1:$backend" >/dev/null
  printf 'tcp %s\n' "$public" >> "$WFS_STATE/serve.txt"
}
https() {
  local port="$1" backend="$2" scheme="$3"
  assert_port_free "$port"
  [[ "$scheme" == http || "$scheme" == https+insecure ]]
  ts serve --bg "--https=$port" "$scheme://127.0.0.1:$backend" >/dev/null
  printf 'https %s\n' "$port" >> "$WFS_STATE/serve.txt"
}
assert_port_free() {
  ts serve status --json | python3 -c '
import json,sys
x=json.load(sys.stdin) or {}
p=sys.argv[1]
if p in (x.get("TCP") or {}) or any(str(n).endswith(":"+p) for n in (x.get("Web") or {})):
    raise SystemExit("Refusing to replace an existing Serve listener")
if any((x.get("AllowFunnel") or {}).values()):
    raise SystemExit("Close existing public publishing on this dedicated node first")
' "$1"
}
cleanup() {
  [[ -f "$WFS_STATE/serve.txt" ]] || return 0
  while read -r proto port; do
    [[ "$port" =~ ^[0-9]+$ && ( "$proto" == tcp || "$proto" == https ) ]] || continue
    ts serve "--$proto=$port" off >/dev/null || true
  done < "$WFS_STATE/serve.txt"
  rm -f "$WFS_STATE/serve.txt"
}
case "$1" in
  ip|dns|tcp|https|cleanup) action="$1"; shift; "$action" "$@";;
  *) exit 2;;
esac
