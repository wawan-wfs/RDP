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
from windows import report


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
        bad = (("linux", {"distro": "arch", "remote_access": "rdp"}),
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

    def test_windows_runner_selection(self):
        default = workspace.config("windows", {}, runner_arch="X64")
        self.assertEqual(default["windows_effective_runner"], "windows-2025")
        for mode in ("novnc", "both"):
            with self.subTest(mode=mode):
                requested = {"windows_version": "windows-11-arm", "remote_access": mode}
                routed = workspace.config("windows", requested, runner_arch="X64")
                self.assertEqual((routed["remote_access"], routed["windows_version"], routed["windows_effective_runner"], routed["windows_fallback"]),
                                 (mode, "windows-11-arm", "windows-2025", True))
                with self.assertRaisesRegex(ValueError, "needs an x64 runner"):
                    workspace.config("windows", requested | {"runner_type": "self-hosted"}, runner_arch="ARM64")
        arm = workspace.config("windows", {"windows_version": "windows-11-arm", "remote_access": "rdp"}, runner_arch="ARM64")
        self.assertEqual((arm["windows_effective_runner"], arm["windows_fallback"]), ("windows-11-arm", False))
        x64 = workspace.config("windows", {"windows_version": "windows-2022", "remote_access": "both"}, runner_arch="X64")
        self.assertEqual((x64["windows_effective_runner"], x64["windows_fallback"]), ("windows-2022", False))

    def test_windows_preflight_regression(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            event = root / "event.json"
            event.write_text(json.dumps({"inputs": {"windows_version": "windows-11-arm", "remote_access": "both"}}), encoding="utf-8-sig")
            env = dict(os.environ, GITHUB_RUN_ID="101", GITHUB_RUN_ATTEMPT="1", GITHUB_EVENT_PATH=str(event),
                       GITHUB_ENV=str(root / "environment"), RUNNER_TEMP=temp, RUNNER_ARCH="X64")
            p = subprocess.run([sys.executable, str(ROOT / "shared/workspace.py"), "init", "windows"],
                               env=env, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("::notice title=WFS runner compatibility::", p.stdout)
            self.assertIn("windows-2025 / X64", p.stdout)
            self.assertEqual(json.loads((root / "wfs-remote-101-1/config.json").read_text())["remote_access"], "both")
            env |= {"WFS_WINDOWS_LOG": "1", "GITHUB_STEP_SUMMARY": str(root / "summary"), "WFS_REMOTE": "success"}
            p = subprocess.run([sys.executable, "shared/workspace.py", "status", "Windows RDP", "ready",
                                "mstsc /v:100.64.0.42:3389; user RDP; NLA enabled"], cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("[PASS] Windows RDP", p.stdout)
            p = subprocess.run([sys.executable, "-m", "windows.report", "access"], cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("mstsc /v:100.64.0.42:3389 /f", (root / "summary").read_text(encoding="utf-8"))

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
            if file.name.startswith("windows-"):
                self.assertIn(f"inputs.windows_version == 'windows-11-arm' && inputs.remote_access != 'rdp' && '{workspace.WINDOWS_BROWSER_FALLBACK}'", job["runs-on"])
                summary = next(x for x in job["steps"] if "windows.report access" in x.get("run", ""))
                self.assertEqual(summary["if"], "\u0024{{ !cancelled() }}")
                self.assertLess(job["steps"].index(summary), ids.index("apps"))
                self.assertLess(ids.index("preflight"), ids.index("verify"))
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


class WindowsReports(unittest.TestCase):
    def test_failed_preflight_has_timeline_without_secrets_or_state(self):
        card = report.access_summary({}, [], {"WFS_PREFLIGHT": "failure", "WFS_TAILNET": "skipped", "RDP_PASSWORD": "NeverLogThis!"})
        self.assertIn("Setup failed", card)
        self.assertIn("| Configuration | ❌ Failed |", card)
        self.assertIn("| Tailscale join | ➖ Skipped |", card)
        self.assertNotIn("NeverLogThis!", card)
        self.assertNotIn("## 🔗 Connect", card)

    def test_connection_card_preserves_partial_success_and_private_url(self):
        cfg = workspace.config("windows", {"windows_version": "windows-11-arm", "remote_access": "both"}, runner_arch="X64")
        url = "http://100.64.0.42:6082/vnc.html#resize=scale&autoconnect=1&path=websockify"
        rows = [("Windows RDP", "failed", "See remote setup"), ("Windows noVNC", "ready", url + "; console session")]
        card = report.access_summary(cfg, rows, {"WFS_REMOTE": "success"})
        self.assertIn("Windows 11 ARM64 → Windows Server 2025 x64", card)
        self.assertIn("One access path is ready", card)
        self.assertIn(f"[Open private desktop]({url})", card)
        self.assertEqual(report.browser_link(url.replace("100.64.0.42", "192.0.2.42")), "")
        self.assertEqual(report.browser_link("https://example.com/vnc.html#resize=scale&autoconnect=1&path=websockify"), "")

    def test_application_counts_do_not_treat_timeout_as_installed(self):
        card = report.apps_summary([("Chrome", "installed", "Verified"), ("Tool | X", "timed out", "Elapsed"),
                                    ("CapCut", "pending interactive", "Shortcut"), ("Windows RDP", "ready", "Remote")], "failure")
        self.assertIn("1 installed/configured", card)
        self.assertIn("1 pending", card)
        self.assertIn("1 with issues", card)
        self.assertIn("Tool &#124; X", card)
        self.assertNotIn("Windows RDP", card)


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
