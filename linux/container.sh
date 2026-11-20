#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
mode="$1"; user="$2"; desktop="$3"
[[ "$mode" == rdp && "$user" =~ ^[A-Za-z][A-Za-z0-9_-]{0,19}$ ]]
IFS= read -r password
[[ -n "$password" ]]
case "$desktop" in
  kde) deb='plasma-desktop'; fed='plasma-desktop plasma-workspace-x11'; alp=''; session='startplasma-x11';;
  xfce) deb='xfce4'; fed='xfce4-session xfwm4 xfce4-panel'; alp='xfce4'; session='startxfce4';;
  mate) deb='mate-desktop-environment-core'; fed='mate-session-manager mate-panel marco'; alp='mate-desktop-environment'; session='mate-session';;
  i3) deb='i3-wm xterm'; fed='i3 xterm'; alp='i3wm xterm'; session='i3';;
  lxqt) deb='lxqt-core openbox'; fed=''; alp=''; session='startlxqt';;
  *) exit 2;;
esac
# Packages are resolved against the container distribution, without host changes.
if command -v apt-get >/dev/null; then
  apt-get -o Acquire::Retries=2 update
  if ! command -v "$session" >/dev/null; then
    # shellcheck disable=SC2086
    apt-get install -y --no-install-recommends $deb
  fi
  apt-get install -y --no-install-recommends xrdp xorgxrdp xserver-xorg-core dbus-x11 procps
elif command -v dnf >/dev/null; then
  # shellcheck disable=SC2086
  dnf install -y xrdp xorgxrdp xorg-x11-server-Xorg dbus-x11 $fed
elif command -v apk >/dev/null; then
  # shellcheck disable=SC2086
  apk add --no-cache shadow xrdp xorgxrdp xorg-server dbus $alp
else echo 'XRDP backend unsupported for this distro'; exit 2; fi
command -v "$session" >/dev/null || { echo "Desktop X11 entry point $session is unavailable"; exit 1; }
if id "$user" >/dev/null 2>&1; then echo 'Remote username collides with an image account'; exit 1; fi
useradd --badname --create-home --shell /bin/bash "$user"
printf '%s:%s\n' "$user" "$password" | chpasswd
unset password
home="$(getent passwd "$user" | cut -d: -f6)"
group="$(id -gn "$user")"
install -d -m 0755 -o "$user" -g "$group" "$home/.local/share/applications" "$home/wfs-project"
cat > "$home/.xsession" <<EOF
#!/bin/sh
unset DBUS_SESSION_BUS_ADDRESS WAYLAND_DISPLAY
export XDG_SESSION_TYPE=x11
export QT_QPA_PLATFORM=xcb
export XDG_RUNTIME_DIR="\$HOME/.wfs-xdg-\$\$"
mkdir -m 700 "\$XDG_RUNTIME_DIR" || exit 1
trap 'rmdir "\$XDG_RUNTIME_DIR" 2>/dev/null || true' EXIT
dbus-run-session -- $session
EOF
chmod 0755 "$home/.xsession"
chown "$user:$group" "$home/.xsession"
# XRDP uses an independent Xorg session, not the Selkies Wayland display.
cat > /etc/xrdp/startwm.sh <<'EOF'
#!/bin/sh
exec "$HOME/.xsession"
EOF
chmod 755 /etc/xrdp/startwm.sh
if command -v adduser >/dev/null && getent group ssl-cert >/dev/null && id xrdp >/dev/null 2>&1; then
  usermod -a -G ssl-cert xrdp
fi
mkdir -p /run/xrdp /run/dbus
if [[ -x /usr/share/xrdp/socksetup ]]; then /usr/share/xrdp/socksetup; fi
if getent group xrdp >/dev/null; then chgrp xrdp /run/xrdp; fi
dbus-uuidgen --ensure
[[ -S /run/dbus/system_bus_socket ]] || dbus-daemon --system --fork
nohup xrdp-sesman --nodaemon </dev/null >/tmp/wfs-sesman.log 2>&1 &
nohup xrdp --nodaemon </dev/null >/tmp/wfs-xrdp.log 2>&1 &
for ((i=0;i<20;i++)); do
  if (exec 9<>/dev/tcp/127.0.0.1/3389) 2>/dev/null; then exit 0; fi
  sleep 1
done
tail -n 20 /tmp/wfs-xrdp.log /tmp/wfs-sesman.log || true
exit 1
