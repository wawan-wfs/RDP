"""Start/cleanup workflow integration with a fake runtime and a real local RDP probe."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from shared import workspace

@unittest.skipIf(sys.platform != "linux", "Linux host script integration")
class LinuxMock(unittest.TestCase):
    def test_both_is_not_blocked_by_missing_web_secret(self):
        with tempfile.TemporaryDirectory() as tmp, socket.socket() as s:
            t = Path(tmp)
            b = t / "bin"
            b.mkdir()
            def fake(name, body):
                f=b / name
                f.write_text("#!/bin/bash\nset -eu\n"+body)
                f.chmod(0o755)
            fake("sudo",'if [[ "$1" == "-n" ]]; then shift; fi\nexec "$@"\n')
            fake("tailscale",'''case "$*" in
"ip -4") echo 100.64.0.10;;
"serve status --json") echo '{}';;
*) printf '%s\\n' "$*" >> "$FAKE_LOG";;
esac
''')
            fake("docker",'''case "$1" in
inspect) exit 1;;
exec)
  if [[ "${2:-}" == "-i" ]]; then
    IFS= read -r test_secret
    [[ "$test_secret" == 'synthetic-password' && "${@: -2:1}" == 'RDP' ]]
  fi;;
esac
printf 'docker %s\\n' "$*" >> "$FAKE_LOG"
''')
            try:
                s.bind(("127.0.0.1",13389))
            except OSError:
                self.skipTest("fixture port not free")
            s.listen()
            def wait():
                with s.accept()[0] as conn:
                    conn.recv(19)
                    conn.sendall(bytes.fromhex("030000130ed000000000000200080001000000"))
            tr = threading.Thread(target=wait,daemon=True)
            tr.start()
            state=t/"wfs-remote-12345-1"
            state.mkdir()
            import json,time
            cfg=workspace.config("linux",{"remote_access":"both"},"12345")
            cfg["started"]=int(time.time())
            (state/"config.json").write_text(json.dumps(cfg))
            env=dict(os.environ,PATH=f"{b}:{os.environ['PATH']}",RUNNER_TEMP=str(t),
                     GITHUB_RUN_ID="12345",GITHUB_RUN_ATTEMPT="1",WFS_STATE=str(state),
                     RDP_PASSWORD="synthetic-password",VNC_PASSWORD="",FAKE_LOG=str(t/"commands"))
            started=subprocess.run(["bash","linux/workspace.sh","start"],cwd=ROOT,env=env,capture_output=True,text=True,timeout=12)
            self.assertEqual(started.returncode,0,started.stdout+started.stderr)
            self.assertTrue((state/"remote-ready").is_file())
            self.assertIn('VNC_PASSWORD not configured',(state/"status.jsonl").read_text())
            log=(t/"commands").read_text()
            self.assertIn('127.0.0.1:13389:3389',log)
            self.assertNotIn('13001:3001',log)
            self.assertNotIn('synthetic-password',log)
            self.assertIn('--tcp=3389 tcp://127.0.0.1:13389',log)
            subprocess.run(["bash","linux/workspace.sh","cleanup"],cwd=ROOT,env=env,capture_output=True,check=True,timeout=8)
            self.assertIn('serve --tcp=3389 off',(t/"commands").read_text())
            self.assertIn('docker rm -f wfs-12345-1',(t/"commands").read_text())
            tr.join(2)

if __name__ == '__main__':
    unittest.main()
