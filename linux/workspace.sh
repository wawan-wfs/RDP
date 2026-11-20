#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
get() { python3 shared/workspace.py get "$1"; }
status() { python3 shared/workspace.py status "$@"; }
ct="wfs-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}"
if [[ "$1" == cleanup ]]; then
  [[ -n "${WFS_STATE:-}" && -d "$WFS_STATE" ]] || exit 0
  shared/tailnet.sh cleanup || true
  for file in "$WFS_STATE"/proxy-*.pid; do
    [[ -s "$file" ]] || continue
    pid="$(cat "$file")"
    if [[ "$pid" =~ ^[0-9]+$ ]] && ps -p "$pid" -o command= | grep -Fq 'shared/tailnet_tcp.py'; then sudo -n kill "$pid" || true; fi
    sudo -n rm -f "$file" || true
  done
  [[ -f "$WFS_STATE/container-owned" ]] && docker rm -f "$ct" >/dev/null 2>&1 || true
  exit 0
fi
mode="$(get remote_access)"
distro="$(get distro)"
desktop="$(get desktop)"
rdp_user="$(get rdp_username)"
web_user="$(get web_username)"
want_rdp=false; want_web=false
case "$mode" in rdp) want_rdp=true;; novnc) want_web=true;; both) want_rdp=true;want_web=true;; esac
if [[ "$distro" == igos-nusantara ]]; then
  [[ -f "${WFS_IGOS_ISO:-}" ]] || { echo 'Dedicated runner needs a locally supplied WFS_IGOS_ISO file'; exit 1; }
  iso="$(realpath "$WFS_IGOS_ISO")"
  [[ "$iso" != *:* && "$iso" != *,* ]]
  distro=ubuntu
fi
if [[ "$desktop" == lxqt ]]; then image=lscr.io/linuxserver/webtop:ubuntu-xfce
else image="lscr.io/linuxserver/webtop:$distro-$desktop"; fi
ip="$(shared/tailnet.sh ip)"
status 'Tailnet' ready "IPv4 $ip"
private_tcp() {
  local port="$1" backend="$2" file="$WFS_STATE/proxy-$1.pid"
  if shared/tailnet.sh tcp "$port" "$backend"; then return 0; fi
  sudo -n nohup "$(command -v python3)" shared/tailnet_tcp.py "$ip" "$port" "$backend" "$file"     >"$WFS_STATE/proxy-$port.log" 2>&1 </dev/null &
  for ((i=0;i<10;i++)); do
    if [[ -s "$file" ]]; then
      status "Private TCP $port" configured 'Bound only to tailscale0, without public route'
      return 0
    fi
    sleep 1
  done
  cat "$WFS_STATE/proxy-$port.log" >&2
  return 1
}
ports=()
envs=()
volume=()
if $want_rdp; then ports+=(-p 127.0.0.1:13389:3389); fi
if $want_web; then
  if PASSWORD="$(python3 shared/workspace.py password web)"; then
  printf '::add-mask::%s\n' "$PASSWORD"
  export PASSWORD
  ports+=(-p 127.0.0.1:13001:3001)
  envs+=(-e PASSWORD -e "CUSTOM_USER=$web_user")
  else
    status 'Selkies Webtop' failed 'VNC_PASSWORD not configured or invalid'
    want_web=false
  fi
fi
if ! $want_web && ! $want_rdp; then exit 1; fi
if [[ -n "${iso:-}" ]]; then volume+=(-v "$iso:/opt/igos.iso:ro"); fi
# The host does not expose Docker or GUI ports on LAN interfaces.
if docker inspect "$ct" >/dev/null 2>&1; then echo 'Workspace container already exists'; exit 1; fi
docker pull "$image"
docker run -d --name "$ct" --shm-size=1gb --label wfs.workspace=true \
  "${ports[@]}" "${envs[@]}" "${volume[@]}" "$image" >/dev/null
: > "$WFS_STATE/container-owned"
docker exec "$ct" mkdir -p /opt/wfs
docker cp linux/container.sh "$ct:/opt/wfs/container.sh"
docker cp linux/install-apps.sh "$ct:/opt/wfs/install-apps.sh"
ready=0
if $want_web; then
  if python3 shared/check_web.py 'https://127.0.0.1:13001/' "$web_user"; then
    url=
    transport="$(get transport)"
    if [[ "$transport" != tailnet_tls_tcp ]]; then
      if dns="$(shared/tailnet.sh dns)" && shared/tailnet.sh https 443 13001 https+insecure; then url="https://$dns"; fi
    fi
    if [[ -z "$url" && "$transport" != tailnet_https ]] && private_tcp 6082 13001; then url="https://$ip:6082"; fi
    if [[ -n "$url" ]]; then
      status 'Selkies Webtop' ready "$url; user $web_user; authentication verified locally"
      ready=$((ready+1))
    else status 'Selkies Webtop' failed 'No requested private transport could be published'; fi
  else status 'Selkies Webtop' failed 'Authentication or local HTTPS failed'; fi
  unset PASSWORD
fi
if $want_rdp; then
  # Feed password on stdin, never as command arguments or as a container env variable.
  if pwd="$(python3 shared/workspace.py password rdp)"; then
    printf '::add-mask::%s\n' "$pwd"
    if printf '%s\n' "$pwd" | timeout --kill-after=15s 17m docker exec -i "$ct" timeout -k 15s 16m bash /opt/wfs/container.sh rdp "$rdp_user" "$desktop" &&
      python3 shared/rdp_probe.py 127.0.0.1 13389 && private_tcp 3389 13389; then
      status 'Linux XRDP' ready "mstsc /v:$ip:3389; user $rdp_user; $desktop (X11)"
      ready=$((ready+1))
    else status 'Linux XRDP' failed 'X11 or local XRDP readiness failed; see setup log'; fi
    unset pwd
  else status 'Linux XRDP' failed 'RDP_PASSWORD not configured or invalid'; fi
fi
if ((ready == 0)); then exit 1; fi
: > "$WFS_STATE/remote-ready"
