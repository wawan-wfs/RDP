"""Terminate a Unix subprocess group if an optional installer overstays."""
import os
import signal
import subprocess
import sys

def run(seconds, argv):
    p = subprocess.Popen(argv, start_new_session=True)
    try:
        return p.wait(timeout=seconds)
    except (TimeoutError, subprocess.TimeoutExpired):
        try:
            os.killpg(p.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        p.wait()
        return 124

if __name__ == "__main__":
    sys.exit(run(int(sys.argv[1]), sys.argv[2:]))
