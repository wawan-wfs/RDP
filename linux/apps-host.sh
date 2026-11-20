#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ct="wfs-$GITHUB_RUN_ID-${GITHUB_RUN_ATTEMPT:-1}"
[[ -f "$WFS_STATE/container-owned" ]]
get() { python3 shared/workspace.py get "$1"; }
# Application installation runs after remote publication. Its transient output never contains secrets.
set +e
timeout --kill-after=15s 27m docker exec "$ct" timeout -k 15s 25m bash /opt/wfs/install-apps.sh \
  "$(get distro)" "$(get ide_choice)" "$(get editor_choice)" "$(get metatrader_choice)" \
  "$(get router_choice)" "$(get coding_agent_choice)" "$(get ai_agent_choice)" \
  "$(get apps_bundle)" "$(get install_artcraft)" > "$WFS_STATE/linux-apps.log" 2>&1
code=$?
set -e
cat "$WFS_STATE/linux-apps.log"
while IFS=$'\t' read -r mark name state detail; do
  if [[ "$mark" == WFS_APP && -n "$detail" ]]; then python3 shared/workspace.py status "$name" "$state" "$detail"; fi
done < "$WFS_STATE/linux-apps.log"
if ((code)); then python3 shared/workspace.py status 'Linux app worker' warning "Installer worker returned $code; already ready endpoints were left running"; fi
