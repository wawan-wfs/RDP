"""Keep a specific noVNC error reason when the optional Actions step fails."""
import subprocess, sys
from shared.workspace import state_dir
from windows.legacy_dashboard import rows_in_state

def main():
    rows = rows_in_state(state_dir())
    latest = {name: (status, detail) for name, status, detail in rows}
    previous = latest.get('Windows noVNC')
    if previous and previous[0] == 'failed':
        print(f'[WFS/noVNC] Preserving previous failure diagnostic: {previous[1]}', flush=True)
        return 0
    p = subprocess.run([sys.executable, 'shared/workspace.py', 'status',
                        'Windows noVNC', 'failed',
                        'Timed out or failed before the failure stage could be recorded.'], check=False)
    return p.returncode

if __name__ == '__main__':
    raise SystemExit(main())
