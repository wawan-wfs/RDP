#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
get() { python3 shared/workspace.py get "$1"; }
status() { python3 shared/workspace.py status "$@"; }
if [[ "$1" == cleanup && ( -z "${WFS_STATE:-}" || ! -d "$WFS_STATE" ) ]]; then exit 0; fi
cfg_user="$(get remote_username)"
if [[ "$1" == cleanup ]]; then
  shared/tailnet.sh cleanup || true
  if [[ -s "$WFS_STATE/preview.pid" ]]; then
    pid="$(cat "$WFS_STATE/preview.pid")"
    if [[ "$pid" =~ ^[0-9]+$ ]] && ps -p "$pid" -o command= | grep -Fq 'macos/gui-preview.py'; then kill "$pid" || true; fi
  fi
  if [[ -s "$WFS_STATE/sshd.pid" ]]; then
    pid="$(cat "$WFS_STATE/sshd.pid")"
    if [[ "$pid" =~ ^[0-9]+$ ]] && ps -p "$pid" -o command= | grep -q sshd; then sudo -n kill "$pid" || true; fi
  fi
  if [[ -f "$WFS_STATE/user-owned" ]]; then sudo -n sysadminctl -deleteUser "$cfg_user" >/dev/null 2>&1 || true; fi
  rm -f "$WFS_STATE/ssh-ed25519" "$WFS_STATE/ssh-ed25519.pub" "$WFS_STATE/ssh-askpass" "$WFS_STATE/ssh-known-hosts"
  exit 0
fi
ip="$(shared/tailnet.sh ip)"
status 'Tailnet' ready "IPv4 $ip"
mode="$(get remote_access)"
ready=0
probe() { python3 shared/workspace.py tcp "$@" >/dev/null 2>&1; }
mac_diag() {
  local console
  console="$(stat -f %Su /dev/console)"
  printf 'Console user present: %s\n' "$([[ "$console" != root && "$console" != loginwindow ]] && echo yes || echo no)"
  printf 'WindowServer process: %s\n' "$(pgrep -x WindowServer >/dev/null && echo present || echo absent)"
  printf 'SSH daemon config and Screen Sharing are independently verified.\n'
}
ssh_setup() {
  if id "$cfg_user" >/dev/null 2>&1; then echo 'Remote user already exists; use a dedicated name'; return 1; fi
  local p fingerprint
  p="$(python3 shared/workspace.py password remote)" || return 1
  printf '::add-mask::%s\n' "$p"
  sudo -n sysadminctl -addUser "$cfg_user" -fullName 'WFS remote workspace' -password "$p" >/dev/null 2>&1 || return 1
  id "$cfg_user" >/dev/null 2>&1 || return 1
  : > "$WFS_STATE/user-owned"
  ssh-keygen -q -t ed25519 -N '' -f "$WFS_STATE/ssh-ed25519" || return 1
  cat > "$WFS_STATE/sshd.conf" <<EOF
Port 12222
ListenAddress 127.0.0.1
HostKey "$WFS_STATE/ssh-ed25519"
PidFile "$WFS_STATE/sshd.pid"
AllowUsers $cfg_user
PermitRootLogin no
PasswordAuthentication yes
KbdInteractiveAuthentication no
PermitEmptyPasswords no
PubkeyAuthentication no
UsePAM yes
AllowTcpForwarding no
X11Forwarding no
PermitTunnel no
MaxAuthTries 4
Subsystem sftp internal-sftp
EOF
  sudo -n /usr/sbin/sshd -t -f "$WFS_STATE/sshd.conf" || return 1
  sudo -n /usr/sbin/sshd -f "$WFS_STATE/sshd.conf" -E "$WFS_STATE/sshd.log" || return 1
  for ((i=0;i<15;i++)); do
    if probe 127.0.0.1 12222 --prefix SSH-; then break; fi
    sleep 1
  done
  probe 127.0.0.1 12222 --prefix SSH- || return 1
  local ask="$WFS_STATE/ssh-askpass" got known="$WFS_STATE/ssh-known-hosts"
  printf '%s\n' '#!/bin/sh' 'printf "%s\n" "$WFS_SSH_PROBE_PASS"' > "$ask"
  chmod 700 "$ask"
  printf '[127.0.0.1]:12222 %s\n' "$(awk '{print $1,$2}' "$WFS_STATE/ssh-ed25519.pub")" > "$known"
  if ! got="$(DISPLAY=:0 SSH_ASKPASS_REQUIRE=force SSH_ASKPASS="$ask" WFS_SSH_PROBE_PASS="$p" \
    ssh -F /dev/null -p 12222 -o ConnectTimeout=5 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" \
    -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 \
    "$cfg_user@127.0.0.1" /usr/bin/id -un </dev/null 2>"$WFS_STATE/ssh-probe.log")" || [[ "$got" != "$cfg_user" ]]; then
    rm -f "$ask" "$known"
    return 1
  fi
  rm -f "$ask" "$known"
  unset p
  shared/tailnet.sh tcp 2222 12222 || return 1
  fingerprint="$(ssh-keygen -lf "$WFS_STATE/ssh-ed25519.pub" | awk '{print $2}')"
  status 'macOS SSH' ready "ssh -p 2222 $cfg_user@$ip; host key $fingerprint; local password authentication verified"
}
if [[ "$mode" == ssh || "$mode" == both ]]; then
  if ssh_setup; then ready=$((ready+1))
  else status 'macOS SSH' failed 'Could not create local standard user, validate SSH, or publish private port'; fi
fi
if [[ "$mode" == vnc || "$mode" == both ]]; then
  if python3 shared/rfb_probe.py 127.0.0.1 5900 --apple > "$WFS_STATE/vnc-probe" && shared/tailnet.sh tcp 5900 5900; then
    status 'Apple Screen Sharing' ready "vnc://$ip:5900; RFB listener only; viewer auth and interactive input unverified"
    ready=$((ready+1))
  else
    status 'Apple Screen Sharing' unavailable 'Enable through authorized System Settings or MDM on a Mac you manage; no override was attempted'
  fi
fi
if [[ "$(get gui_preview)" == true ]]; then
  if p="$(python3 shared/workspace.py password preview)"; then
    printf '::add-mask::%s\n' "$p"
    if ! probe 127.0.0.1 6081; then
      WFS_PREVIEW_USER="$cfg_user" WFS_PREVIEW_PASSWORD="$p" nohup python3 macos/gui-preview.py >"$WFS_STATE/preview.log" 2>&1 </dev/null &
      echo "$!" > "$WFS_STATE/preview.pid"
      for ((i=0;i<12;i++)); do
        if probe 127.0.0.1 6081; then break; fi
        sleep 1
      done
      if kill -0 "$(cat "$WFS_STATE/preview.pid")" 2>/dev/null && WFS_PREVIEW_USER="$cfg_user" WFS_PREVIEW_PASSWORD="$p" python3 macos/verify-preview.py && shared/tailnet.sh tcp 6081 6081; then
        status 'WFS Private Preview' configured "http://$ip:6081/; user $cfg_user; screenshot-only, Screen Recording approval may be required"
      else status 'WFS Private Preview' failed 'Preview authentication or private publication failed'; fi
      unset p
    else status 'WFS Private Preview' unavailable 'Loopback port already in use'; fi
  fi
fi
mac_diag
if ((ready == 0)); then echo 'No requested interactive connection endpoint was ready'; exit 1; fi
: > "$WFS_STATE/remote-ready"
