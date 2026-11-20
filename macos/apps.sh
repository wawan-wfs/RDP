#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/.."
get() { python3 shared/workspace.py get "$1"; }
status() { python3 shared/workspace.py status "$@"; }
run() {
  local app="$1"; shift
  if python3 shared/bounded.py 150 "$@"; then status "$app" attempted 'Command completed; verify desktop or CLI launch in user session'
  else status "$app" warning 'Optional install failed/timed out; remote access unchanged'; fi
}
ide="$(get ide_choice)"
coding="$(get coding_agent_choice)"
bundle="$(get apps_bundle)"
[[ "$ide" == none ]] || run 'VS Code' brew install --cask visual-studio-code
if [[ "$coding" == codex || "$coding" == both ]]; then run Codex brew install --cask codex; fi
if [[ "$coding" == claude || "$coding" == both ]]; then run 'Claude Code' brew install --cask claude-code; fi
if [[ "$bundle" == developer || "$bundle" == all ]]; then run 'Developer bundle' brew install jq cmake; fi
if [[ "$bundle" == media || "$bundle" == all ]]; then run 'Media bundle' brew install ffmpeg; fi
if [[ "$(get trading_choice)" == webterminal ]]; then status 'MetaTrader WebTerminal' configured 'https://web.metatrader.app/; browser only; no desktop EA'; fi
