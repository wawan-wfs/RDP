"""Regression fixtures for the private noVNC Tailscale Serve configuration."""
import unittest
from unittest.mock import patch

import serve_verify as sv


class ServeVerifyTests(unittest.TestCase):
    TCP = {'TCP': {'6082': {'TCPForward': '127.0.0.1:6081'}}, 'AllowFunnel': {}}
    HTTPS = {
        'TCP': {'443': {'HTTPS': True}},
        'Web': {'rdp-runner.example.ts.net:443': {
            'Handlers': {'/': {'Proxy': 'http://127.0.0.1:6081'}}}},
        'AllowFunnel': {},
    }

    def test_valid_tcp(self):
        self.assertIn('confirmed', sv.verify_serve(self.TCP, 'tcp', 6082, 'tcp://127.0.0.1:6081'))

    def test_valid_tcp_scheme_present(self):
        self.assertIn('confirmed', sv.verify_serve({'TCP': {'6082': {
            'TCPForward': 'tcp://localhost:6081'}}}, 'tcp', 6082, 'tcp://127.0.0.1:6081'))

    def test_valid_https(self):
        self.assertIn('confirmed', sv.verify_serve(self.HTTPS, 'https', 443, 'http://127.0.0.1:6081',
                                                   'rdp-runner.example.ts.net'))

    def test_reject_wrong_tcp_target(self):
        with self.assertRaisesRegex(sv.ServeVerifyError, 'does not target'):
            sv.verify_serve({'TCP': {'6082': {'TCPForward': '0.0.0.0:6081'}}},
                            'tcp', 6082, 'tcp://127.0.0.1:6081')

    def test_reject_public_funnel(self):
        config = dict(self.TCP, AllowFunnel={'rdp-runner.example.ts.net:6082': True})
        with self.assertRaisesRegex(sv.ServeVerifyError, 'Public'):
            sv.verify_serve(config, 'tcp', 6082, 'tcp://127.0.0.1:6081')

    def test_reject_wrong_https_proxy(self):
        config = dict(self.HTTPS, Web={'rdp-runner.example.ts.net:443': {
            'Handlers': {'/': {'Proxy': 'http://127.0.0.1:6060'}}}})
        with self.assertRaisesRegex(sv.ServeVerifyError, 'does not target'):
            sv.verify_serve(config, 'https', 443, 'http://127.0.0.1:6081', 'rdp-runner.example.ts.net')

    def test_reject_wrong_https_hostname(self):
        with self.assertRaisesRegex(sv.ServeVerifyError, 'not present'):
            sv.verify_serve(self.HTTPS, 'https', 443, 'http://127.0.0.1:6081',
                            'wrong.example.ts.net')

    def test_missing_route(self):
        with self.assertRaisesRegex(sv.ServeVerifyError, 'no TCP listener'):
            sv.verify_serve({}, 'tcp', 6082, 'tcp://127.0.0.1:6081')

    def test_no_fallback_to_invalid_mode(self):
        with self.assertRaisesRegex(sv.ServeVerifyError, 'Mode and port'):
            sv.verify_serve(self.TCP, 'tcp', 443, 'tcp://127.0.0.1:6081')

    def test_reject_unexpected_requested_proxy(self):
        with self.assertRaisesRegex(sv.ServeVerifyError, "Requested proxy target"):
            sv.verify_serve(self.TCP, "tcp", 6082, "tcp://127.0.0.1:7000")

    def test_reject_unknown_target_path(self):
        with self.assertRaisesRegex(sv.ServeVerifyError, 'does not target'):
            sv.verify_serve({'TCP': {'6082': {'TCPForward': '127.0.0.1:6081/private'}}},
                            'tcp', 6082, 'tcp://127.0.0.1:6081')


if __name__ == '__main__':
    unittest.main(verbosity=2)