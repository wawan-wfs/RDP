import base64
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import os
from http.client import HTTPConnection
import re
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shared import bounded, rdp_probe, rfb_probe, tailnet_tcp, workspace


def load_script(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mac_preview = load_script("wfs_preview", "macos/gui-preview.py")
PNG = mac_preview.PNG_HEADER + b"fixture"


class Configuration(unittest.TestCase):
    def test_legacy_defaults(self):
        w = workspace.config("windows", {})
        self.assertEqual((w["windows_version"], w["rdp_username"], w["remote_access"], w["install_artcraft"]),
                         ("windows-2025", "RDP", "rdp", True))
        l = workspace.config("linux", {})
        self.assertEqual((l["distro"], l["desktop"], l["rdp_username"], l["web_username"], l["hostname"]),
                         ("ubuntu", "kde", "RDP", "wfs", "rdp-runner"))
        m = workspace.config("macos", {})
        self.assertEqual((m["runner_label"], m["remote_access"], m["duration_hours"], m["gui_preview"]),
                         ("macos-15", "both", "1", "true"))

    def test_strict_choices(self):
        bad = (("windows", {"windows_version": "windows-11-arm", "remote_access": "both"}),
               ("linux", {"distro": "arch", "remote_access": "rdp"}),
               ("linux", {"distro": "alpine", "desktop": "kde", "remote_access": "rdp"}),
               ("linux", {"distro": "igos-nusantara", "desktop": "xfce"}),
               ("macos", {"remote_username": "root"}), ("windows", {"tailscale_hostname": "invalid; command"}))
        for platform, c in bad:
            with self.subTest(platform=platform, c=c), self.assertRaises(ValueError):
                workspace.config(platform, c)
        self.assertEqual(workspace.config("linux", {"distro": "arch", "remote_access": "novnc"})["distro"], "arch")
        ok = workspace.config("linux", {"distro": "igos-nusantara", "desktop": "xfce", "runner_type": "self-hosted"})
        self.assertEqual(ok["distro"], "igos-nusantara")
        self.assertEqual(workspace.config("macos", {"hostname_mode": "unique_each_run"}, "42", "2")["hostname"], "rdp-runner-42-2")

    def test_password_limits_and_legacy_hmac(self):
        secret = "ThisIsAnExample#42"
        config = workspace.config("linux", {"rdp_password_mode": "random_each_run"}, "42")
        self.assertEqual(workspace.derive(config, "rdp", secret), hmac.new(secret.encode(), b"wfs:42:rdp", hashlib.sha256).hexdigest()[:24])
        for role, pw in (("web", "short"), ("rdp", "HasControlChar_1\n")):
            with self.assertRaises(ValueError):
                workspace.derive(workspace.config("windows", {}), role, pw)
        self.assertEqual(workspace.derive(workspace.config("windows", {}), "web", "ABCDEFGH_123"), "ABCDEFGH")
        self.assertIn("&#124;", workspace.show_status([("A|B", "ready", "safe")]))
        self.assertNotIn("ThisIsAnExample", workspace.show_status([("A", "ready", "endpoint")]))

    def test_configured_workflows(self):
        files = sorted((ROOT / ".github/workflows").glob("*.yml"))
        self.assertEqual([p.name for p in files],
                         ["linux-remote-workspace.yml", "macos-remote-workspace.yml", "windows-remote-workspace.yml"])
        for file in files:
            def reject_duplicate(loader, node, deep=False):
                seen = {}
                for k, v in node.value:
                    key = loader.construct_object(k, deep=True)
                    self.assertNotIn(key, seen, f"{file.name}: duplicate YAML key")
                    seen[key] = loader.construct_object(v, deep=deep)
                return seen
            class Strict(yaml.BaseLoader):
                pass
            Strict.add_constructor("tag:yaml.org,2002:map", reject_duplicate)
            d = yaml.load(file.read_text(encoding="utf-8"), Loader=Strict)
            controls = d["on"]["workflow_dispatch"]["inputs"]
            self.assertEqual(set(d["on"]), {"workflow_dispatch"})
            self.assertLessEqual(len(controls), 25)
            c = workspace.config(file.name.split("-")[0], {k:v["default"] for k,v in controls.items()})
            self.assertTrue(c["hostname"])
            job = d["jobs"]["workspace"]
            ids = [x.get("id") for x in job["steps"]]
            self.assertLess(ids.index("remote"), ids.index("apps"))
            self.assertEqual(d["permissions"], {"contents": "read"})
            self.assertEqual(next(x for x in job["steps"] if x.get("id") == "apps")["continue-on-error"], "true")
            self.assertIn("always()", job["steps"][-1]["if"])
            for x in job["steps"]:
                self.assertNotRegex(x.get("run", ""), r"\$\{\{\s*(inputs|secrets)\.")
            for v in controls.values():
                if v["type"] == "choice":
                    self.assertIn(v["default"], v["options"])

    def test_workflow_referenced_paths(self):
        for file in (ROOT / ".github/workflows").glob("*.yml"):
            data = file.read_text()
            for name in re.findall(r"(?:\./)?((?:windows|linux|macos|shared)/[A-Za-z0-9_.-]+\.(?:py|ps1|sh))", data):
                self.assertTrue((ROOT / name).is_file(), name)

    def test_tailnet_boundary(self):
        tailnet_tcp.check_params("100.64.0.1", 3389, 13389)
        for args in [("0.0.0.0", 3389, 13389), ("192.168.1.1", 6082, 13001),
                     ("100.64.0.1", 445, 13001), ("100.64.0.1", 6082, 8080)]:
            with self.assertRaises(ValueError):
                tailnet_tcp.check_params(*args)


class Protocols(unittest.TestCase):
    def mock(self, cb, target):
        with socket.socket() as ls:
            ls.bind(("127.0.0.1", 0))
            ls.listen()
            port = ls.getsockname()[1]
            errors = []
            def server():
                try:
                    with ls.accept()[0] as conn:
                        cb(conn)
                except BaseException as e:
                    errors.append(e)
            t = threading.Thread(target=server, daemon=True)
            t.start()
            try:
                result = target(port)
            finally:
                t.join(4)
            self.assertFalse(errors, errors)
            return result

    def test_rfb_fragmented_security_types(self):
        def cb(s):
            s.sendall(b"RFB 003.")
            s.sendall(b"008\n")
            self.assertEqual(rfb_probe.exact(s, 12), b"RFB 003.008\n")
            s.sendall(b"\x01\x02")
        self.assertEqual(self.mock(cb, lambda port: rfb_probe.probe("127.0.0.1", port)), ("RFB 003.008", [2]))

    def test_rdp_negotiation(self):
        def cb(s):
            self.assertEqual(rdp_probe.read_exact(s, 19), rdp_probe.REQUEST)
            s.sendall(bytes.fromhex("030000130ed000000000000200080002000000"))
        self.assertEqual(self.mock(cb, lambda port: rdp_probe.probe("127.0.0.1", port, True)), 2)

    @unittest.skipIf(os.name == "nt", "Unix process-group utility; native Windows gets PowerShell tests")
    def test_unix_timeout_kills_child(self):
        self.assertEqual(bounded.run(0.15, [sys.executable, "-c", "import time; time.sleep(10)"]), 124)
        self.assertEqual(bounded.run(1, [sys.executable, "-c", "raise SystemExit(17)"]), 17)


class Preview(unittest.TestCase):
    def test_cached_only_on_demand(self):
        now = [0]
        count = []
        p = mac_preview.Preview(lambda: count.append(1) or PNG, cooldown=60, clock=lambda: now[0])
        self.assertFalse(count)
        self.assertEqual(p.frame(), (200, PNG, False))
        self.assertEqual(p.frame(), (200, PNG, True))
        now[0] = 61
        self.assertEqual(p.frame(), (200, PNG, False))
        self.assertEqual(len(count), 2)

    def test_failed_capture_does_not_report_success(self):
        bad = mac_preview.Preview(lambda: b"not PNG")
        self.assertEqual(bad.frame()[0], 503)
        self.assertEqual(bad.frame()[0], 429)

    def test_loopback_http_controls(self):
        with mac_preview.create_server("wfs", "synthetic", lambda: PNG, 0) as s:
            t = threading.Thread(target=s.serve_forever, daemon=True)
            t.start()
            try:
                self.assertEqual(s.server_address[0], "127.0.0.1")
                auth = {"Authorization": "Basic " + base64.b64encode(b"wfs:synthetic").decode()}
                def req(method, path, headers):
                    c = HTTPConnection("127.0.0.1", s.server_port, timeout=2)
                    try:
                        c.request(method, path, headers=headers)
                        resp = c.getresponse()
                        return resp.status, resp.read()
                    finally:
                        c.close()
                self.assertEqual(req("GET", "/frame", {})[0], 401)
                self.assertEqual(req("GET", "/", auth)[0], 200)
                self.assertEqual(req("GET", "/frame", auth), (200, PNG))
                self.assertEqual(req("GET", "/frame", auth | {"Sec-Fetch-Site":"cross-site"})[0], 403)
                self.assertEqual(req("POST", "/input", auth)[0], 405)
            finally:
                s.shutdown()
                t.join(2)


if __name__ == "__main__":
    unittest.main()
