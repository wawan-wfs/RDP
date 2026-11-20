#!/usr/bin/env bash
set -uo pipefail
export DEBIAN_FRONTEND=noninteractive
distro="$1"; ide="$2"; editor="$3"; mt="$4"; router="$5"; coding="$6"; ai="$7"; bundle="$8"; art="$9"
sys='/opt/wfs/apps'
mkdir -p "$sys" /usr/local/bin /usr/local/share/applications
pkg() {
  if command -v apt-get >/dev/null; then apt-get -o Acquire::Retries=1 install -y --no-install-recommends "$@"
  elif command -v dnf >/dev/null; then dnf install -y "$@"
  elif command -v apk >/dev/null; then apk add --no-cache "$@"
  elif command -v pacman >/dev/null; then pacman -Sy --noconfirm --needed "$@"
  else return 2; fi
}
bounded() { timeout --kill-after=10s "$@"; }
choose() { [[ "$1" == "$2" || "$1" == both || "$1" == all ]]; }
row() { printf 'WFS_APP\t%s\t%s\t%s\n' "$1" "$2" "$3"; }
app() {
  local name="$1" rc; shift
  echo "Starting $name"
  "$@"; rc=$?
  case "$rc" in
    0) row "$name" installed 'Verified executable or package';;
    9) row "$name" 'pending interactive' 'Run the provided desktop entry from the remote session';;
    2) row "$name" unsupported 'No verified package for this distro or architecture';;
    124|137) row "$name" 'timed out' 'Bounded installer timeout';;
    *) row "$name" failed 'Installer or verification failed; see setup output';;
  esac
}
desktop() {
  local key="$1" label="$2" cmd="$3" terminal="${4:-false}"
  printf '[Desktop Entry]\nType=Application\nName=%s\nExec=%s\nTerminal=%s\nCategories=Utility;\n' "$label" "$cmd" "$terminal" > "/usr/local/share/applications/wfs-$key.desktop"
}
download() { curl --proto '=https' --proto-redir '=https' -fLsS --max-time 105 --retry 1 "$1" -o "$2"; }
version() { command -v "$1" >/dev/null; }
if command -v apt-get >/dev/null; then bounded 100s apt-get -o Acquire::Retries=1 update || true; fi
if ! version curl; then pkg curl ca-certificates || true; fi
extensions='{"ExtensionInstallForcelist":["hlkenndednhfkekhgcdicdfddnkalmdm;https://clients2.google.com/service/update2/crx","fdpohaocaechififmbbbbbknoalclacl;https://clients2.google.com/service/update2/crx"]}'
for dir in /etc/chromium/policies/managed /etc/chromium-browser/policies/managed; do
  mkdir -p "$dir"
  printf '%s\n' "$extensions" > "$dir/90-wfs-extensions.json"
done
row 'Chromium extensions' configured 'Cookie-Editor and GoFullPage policy; verify actual activation in the user profile'
chromium() {
  if version chromium || version chromium-browser; then return 0; fi
  if grep -q '^ID=ubuntu$' /etc/os-release; then
    # Ubuntu chromium-browser is a Snap wrapper; fall back to upstream Playwright Chromium.
    pkg python3 python3-venv || return 1
    python3 -m venv "$sys/chromium-venv" || return 1
    bounded 100s "$sys/chromium-venv/bin/pip" install --retries 1 'playwright>=1.56,<2' || return $?
    export PLAYWRIGHT_BROWSERS_PATH="$sys/browser"
    bounded 240s "$sys/chromium-venv/bin/playwright" install --with-deps chromium --no-shell || return $?
    browser="$(find "$sys/browser" -type f -path '*/chrome-linux64/chrome' -perm -111 -print -quit)"
    [[ -n "$browser" ]] || return 1
    printf '#!/bin/sh\nexec "%s" "$@"\n' "$browser" > /usr/local/bin/chromium
    chmod 0755 /usr/local/bin/chromium
    desktop chromium 'Chromium' 'chromium %U'
  else
    export -f pkg
    bounded 150s bash -c 'pkg chromium' || return $?
  fi
  version chromium || version chromium-browser
}
app Chromium chromium
case "$distro" in igos-nusantara) distro=ubuntu;; esac
arch="$(uname -m)"
code_app() {
  version code && return 0
  url= path=
  case "$distro:$arch" in
    ubuntu:x86_64|debian:x86_64) url='https://update.code.visualstudio.com/latest/linux-deb-x64/stable'; path="$sys/code.deb";;
    ubuntu:aarch64|debian:aarch64) url='https://update.code.visualstudio.com/latest/linux-deb-arm64/stable'; path="$sys/code.deb";;
    fedora:x86_64) url='https://update.code.visualstudio.com/latest/linux-rpm-x64/stable'; path="$sys/code.rpm";;
    fedora:aarch64) url='https://update.code.visualstudio.com/latest/linux-rpm-arm64/stable'; path="$sys/code.rpm";;
    arch:*) bounded 180s pacman -Sy --noconfirm --needed code && version code; return $?;;
    *) return 2;;
  esac
  download "$url" "$path" || return 1
  export -f pkg
  bounded 180s bash -c 'pkg "$1"' _ "$path" || return $?
  version code
}
antigravity() {
  [[ "$distro" != alpine ]] || return 2
  local target
  case "$arch" in x86_64) target=linux-x64;; aarch64) target=linux-arm;; *) return 2;; esac
  local prefix='https://edgedl.me.gvt1.com/edgedl/release2/j0qc3/antigravity/stable/2.8.0-6733682917113856'
  download "$prefix/$target/Antigravity%20IDE.tar.gz" "$sys/antigravity.tgz" || return 1
  mkdir -p "$sys/antigravity"
  tar -xzf "$sys/antigravity.tgz" --no-same-owner --no-same-permissions -C "$sys/antigravity" || return 1
  local binary
  binary="$(find "$sys/antigravity" -maxdepth 4 -type f -iname antigravity -perm -111 -print -quit)"
  [[ -n "$binary" ]] || return 1
  ln -sfn "$binary" /usr/local/bin/antigravity-wfs
  desktop antigravity 'Antigravity IDE' 'antigravity-wfs'
}
install_bundle() {
  export -f pkg
  bounded 150s bash -c 'pkg "$@"' _ "$@"
}
if choose "$ide" vscode; then app 'VS Code' code_app; fi
if choose "$ide" antigravity; then app 'Antigravity IDE' antigravity; fi
if choose "$editor" shotcut; then app Shotcut install_bundle shotcut; fi
if choose "$editor" capcut; then row CapCut unsupported 'No native Linux package; use Windows workspace'; fi
case "$bundle" in
  developer|all) app 'Developer bundle' install_bundle git jq python3 make;;
esac
case "$bundle" in
  office|all) app 'Office bundle' install_bundle libreoffice;;
esac
case "$bundle" in
  media|all) app 'Media bundle' install_bundle ffmpeg audacity;;
esac
meta() {
  [[ "$arch" == x86_64 && "$distro" != alpine ]] || return 2
  local m="$1" url
  case "$m" in
    mt4) url='https://download.terminal.free/cdn/web/exness.technologies.ltd/mt4/exness4setup.exe';;
    mt5) url='https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe';;
  esac
  if ! version wine; then
    if command -v dpkg >/dev/null; then
      dpkg --add-architecture i386 && bounded 90s apt-get update || return 1
      install_bundle wine wine32 wine64 || return $?
    else install_bundle wine || return $?; fi
  fi
  download "$url" "$sys/$m.exe" || return 1
  [[ "$(head -c 2 "$sys/$m.exe")" == MZ ]] || return 1
  printf '#!/bin/sh\nexport WINEPREFIX="$HOME/.wine-wfs-%s"\nexec wine "%s"\n' "$m" "$sys/$m.exe" > "/usr/local/bin/wfs-install-$m"
  chmod 0755 "/usr/local/bin/wfs-install-$m"
  desktop "$m" "Install MetaTrader ${m#mt} (Wine)" "wfs-install-$m"
  return 9
}
if [[ "$mt" != none ]]; then desktop webterminal 'MetaTrader WebTerminal' 'xdg-open https://web.metatrader.app/'; fi
if choose "$mt" mt4; then app 'MetaTrader 4' meta mt4; fi
if choose "$mt" mt5; then app 'MetaTrader 5' meta mt5; fi
node_ready() {
  if version node && version npm && node -e 'process.exit(parseInt(process.versions.node,10)<22?1:0)'; then return 0; fi
  if [[ "$distro" == alpine ]]; then
    install_bundle nodejs npm && node -e 'process.exit(parseInt(process.versions.node,10)<22?1:0)'
    return $?
  fi
  local a
  case "$arch" in x86_64) a=x64;; aarch64) a=arm64;; *) return 2;; esac
  local rel='https://nodejs.org/dist/latest-v24.x' filename
  download "$rel/SHASUMS256.txt" "$sys/node-shasums" || return 1
  filename="$(awk -v a="$a" '$2 ~ ("^node-v[0-9.]+-linux-"a"[.]tar[.]xz$") {print $2;exit}' "$sys/node-shasums")"
  [[ "$filename" =~ ^node-v[0-9.]+-linux-(x64|arm64)\.tar\.xz$ ]] || return 1
  download "$rel/$filename" "$sys/$filename" || return 1
  (cd "$sys" && awk -v n="$filename" '$2==n' node-shasums | sha256sum -c -) || return 1
  tar -xJf "$sys/$filename" --no-same-owner --no-same-permissions -C "$sys" || return 1
  local dir="$sys/${filename%.tar.xz}"
  ln -sfn "$dir/bin/node" /usr/local/bin/node
  ln -sfn "$dir/bin/npm" /usr/local/bin/npm
  version npm && node -e 'process.exit(parseInt(process.versions.node,10)<22?1:0)'
}
npm_cli() {
  local bin="$2" p="$sys/npm-$2"
  node_ready || return $?
  bounded "${3:-240}s" npm install --global --prefix "$p" --include=optional --no-audit --no-fund --fetch-retries=1 --fetch-timeout=45000 "$1" || return $?
  [[ -x "$p/bin/$bin" ]] || return 1
  ln -sfn "$p/bin/$bin" "/usr/local/bin/$bin"
  desktop "$bin" "$bin" "$bin" true
}
vendor() {
  local appname="$1" url="$2" file="$sys/$1-install.sh"
  download "$url" "$file" || return 1
  bash -n "$file" || return 1
  # Per-user installers must run within the actual desktop profile.
  local options=""
  [[ "$appname" != OpenClaw ]] || options="--no-onboard"
  [[ "$appname" != Hermes ]] || options="--non-interactive"
  desktop "$appname" "Install $appname" "bash $file $options" true
  return 9
}
if choose "$router" 9router; then app 9Router npm_cli 9router 9router; fi
if choose "$router" omniroute; then app OmniRoute npm_cli omniroute omniroute 360; fi
if choose "$coding" codex; then app Codex npm_cli @openai/codex codex; fi
if choose "$coding" claude; then app 'Claude Code' vendor Claude-Code https://claude.ai/install.sh; fi
if choose "$ai" hermes; then app 'Hermes Agent' vendor Hermes https://hermes-agent.nousresearch.com/install.sh; fi
if choose "$ai" openclaw; then app OpenClaw vendor OpenClaw https://openclaw.ai/install.sh; fi
if [[ "$ai" == opencode || "$ai" == all ]]; then app OpenCode npm_cli opencode-ai opencode; fi
artcraft() {
  [[ "$distro" != alpine ]] || return 2
  version python3 || install_bundle python3 || return $?
  download https://api.github.com/repos/craft-launcher/craft-launcher/releases/latest "$sys/artcraft.json" || return 1
  local meta url hash
  meta="$(python3 - "$sys/artcraft.json" "$arch" <<'PY'
import json,re,sys
v=json.load(open(sys.argv[1]))
sel=[x for x in v.get('assets',[]) if re.search('-linux-'+sys.argv[2]+r'\.AppImage$',x.get('name','')) and re.fullmatch('sha256:[a-f0-9]{64}',x.get('digest','') or '') and re.match(r'https://github.com/(craft-launcher|storytold)/craft-launcher/releases/download/',x.get('browser_download_url',''))]
assert len(sel)==1
print(sel[0]['browser_download_url'],sel[0]['digest'][7:])
PY
)" || return 1
  read -r url hash <<< "$meta"
  download "$url" "$sys/ArtCraft.AppImage" || return 1
  printf '%s  %s\n' "$hash" "$sys/ArtCraft.AppImage" | sha256sum -c - || return 1
  chmod 0755 "$sys/ArtCraft.AppImage"
  printf '#!/bin/sh\nexec "%s" --appimage-extract-and-run "$@"\n' "$sys/ArtCraft.AppImage" > /usr/local/bin/wfs-artcraft
  chmod 0755 /usr/local/bin/wfs-artcraft
  desktop artcraft 'ArtCraft Launcher' 'wfs-artcraft'
}
if [[ "$art" == true ]]; then app 'ArtCraft Launcher' artcraft; fi
igos() {
  [[ -r /opt/igos.iso ]] || return 2
  install_bundle qemu-system-x86 qemu-system-gui || return $?
  command -v qemu-system-x86_64 >/dev/null || return 1
  desktop igos 'Boot IGOS Nusantara ISO (QEMU)' 'qemu-system-x86_64 -m 2048 -smp 2 -boot d -cdrom /opt/igos.iso'
}
if [[ "$1" == igos-nusantara ]]; then app 'IGOS ISO frontend' igos; fi
exit 0
