import contextlib
import io
import json
import subprocess
import unittest
from unittest import mock
import tailnet_ip as ip


class PrivateTailnetTests(unittest.TestCase):
    def test_private_ip_accepts_only_tailnet_v4(self):
        self.assertEqual(ip.private_ip("100.64.0.42"), "100.64.0.42")
        self.assertEqual(ip.private_ip("100.127.255.254"), "100.127.255.254")
        for bad in ("100.63.255.255", "100.128.0.1", "10.1.0.2", "fd7a:115c:a1e0::1", "bad", ""):
            with self.subTest(bad=bad):
                self.assertIsNone(ip.private_ip(bad))

    def test_cli_accepts_tailscale_only(self):
        self.assertEqual(ip.from_cli("10.0.1.2\n100.108.0.3\n"), "100.108.0.3")
        self.assertIsNone(ip.from_cli("10.2.3.4\n"))

    def test_status_requires_running(self):
        self.assertEqual(ip.from_status(json.dumps({"BackendState": "Running", "Self": {
            "TailscaleIPs": ["fd7a::a", "100.109.10.11"]}})), "100.109.10.11")
        self.assertIsNone(ip.from_status(json.dumps({"BackendState": "NeedsLogin", "Self": {
            "TailscaleIPs": ["100.109.10.11"]}})))
        self.assertIsNone(ip.from_status("{broken"))

    def test_query_status_fallback_when_cli_fails(self):
        with mock.patch.object(ip, "invoke", side_effect=[None, json.dumps({
            "BackendState": "Running", "Self": {"TailscaleIPs": ["100.72.0.5"]}})]) as cli:
            address, source = ip.query("tailscale")
        self.assertEqual((address, source), ("100.72.0.5", "tailscale status --json"))
        self.assertEqual(cli.call_count, 2)

    def test_query_rejects_non_tailnet(self):
        with mock.patch.object(ip, "invoke", side_effect=["192.168.1.2", json.dumps({
            "BackendState": "Running", "Self": {"TailscaleIPs": ["fd7a::a"]}})]):
            self.assertEqual(ip.query("tailscale"), (None, None))

    def test_resolve_waits_for_daemon(self):
        calls = []
        with mock.patch.object(ip, "query", side_effect=[
            (None, None), (None, None), ("100.64.0.51", "tailscale ip -4")]):
            with contextlib.redirect_stderr(io.StringIO()):
                address = ip.resolve("tailscale", attempts=5, interval=3,
                                     sleeper=lambda n: calls.append(n))
        self.assertEqual(address, "100.64.0.51")
        self.assertEqual(calls, [3, 3])

    def test_resolve_fails_without_verified_endpoint(self):
        with mock.patch.object(ip, "query", return_value=(None, None)):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertIsNone(ip.resolve("tailscale", attempts=2, interval=0,
                                              sleeper=lambda _: None))

    def test_invoke_nonzero_output_not_used(self):
        with mock.patch.object(ip.subprocess, "run",
                               return_value=subprocess.CompletedProcess([], 1, "100.90.0.1", "error")):
            self.assertIsNone(ip.invoke("tailscale", "ip", "-4"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
