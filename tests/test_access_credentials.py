"""Unit checks for opt-in credential disclosure and safe copyable access logs."""
import unittest

from shared import workspace
from windows import access_credentials, legacy_dashboard


class AccessCredentialsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = workspace.config('windows', {
            'remote_access': 'both',
            'rdp_password_mode': 'random_each_run',
            'vnc_password_mode': 'random_each_run'
        }, run_id='42', attempt='1', runner_arch='X64')
        cls.rows = [
            ('Tailnet', 'ready', 'IPv4 100.75.20.9'),
            ('Windows RDP', 'ready', 'mstsc /v:100.75.20.9:3389; user RDP; NLA enabled'),
            ('Windows noVNC', 'ready', 'http://100.75.20.9:6082/vnc.html#resize=scale&autoconnect=1&path=websockify'),
        ]
        cls.env = {
            'WFS_REVEAL_RANDOM_PASSWORD': 'true',
            'RDP_PASSWORD': 'Example_LongPassword!42',
            'VNC_PASSWORD': 'VNC_TestSecret!42',
        }

    def test_only_explicit_opt_in_can_reveal(self):
        with self.assertRaisesRegex(ValueError, 'opt-in'):
            access_credentials.summary_fragment(self.cfg, self.rows, {
                **self.env, 'WFS_REVEAL_RANDOM_PASSWORD': 'false'
            })

    def test_values_match_actual_session_derivation(self):
        values = access_credentials.ready_random_passwords(self.cfg, self.rows, self.env)
        self.assertEqual(values, [
            ('Windows RDP', workspace.derive(self.cfg, 'rdp', self.env['RDP_PASSWORD'])),
            ('Windows noVNC', workspace.derive(self.cfg, 'web', self.env['VNC_PASSWORD'])),
        ])
        fragment = access_credentials.summary_fragment(self.cfg, self.rows, self.env)
        self.assertIn(values[0][1], fragment)
        self.assertIn(values[1][1], fragment)
        self.assertNotIn(self.env['RDP_PASSWORD'], fragment)
        self.assertNotIn(self.env['VNC_PASSWORD'], fragment)

    def test_never_reveal_failed_or_fixed_credentials(self):
        rows = self.rows[:-1] + [('Windows noVNC', 'failed', 'Optional browser failed')]
        output = access_credentials.summary_fragment(self.cfg, rows, self.env)
        self.assertIn('Windows RDP', output)
        self.assertNotIn('| Windows noVNC |', output)
        fixed = dict(self.cfg, rdp_password_mode='same_from_secret')
        self.assertIn('Tidak ada endpoint', access_credentials.summary_fragment(fixed, rows, self.env))

    def test_missing_seed_does_not_echo(self):
        with self.assertRaisesRegex(ValueError, 'Missing RDP_PASSWORD'):
            access_credentials.ready_random_passwords(self.cfg, self.rows, {'VNC_PASSWORD': 'AnotherValidSeed'})

    def test_access_log_contains_all_paths_without_secrets(self):
        rows = self.rows + [('Tailnet DNS', 'ready', 'rdp-runner.example.ts.net')]
        lines = '\n'.join(legacy_dashboard.console_access_lines(self.cfg, rows))
        self.assertIn('100.75.20.9', lines)
        self.assertIn('rdp-runner', lines)
        self.assertIn('rdp-runner.example.ts.net', lines)
        self.assertIn('mstsc /v:100.75.20.9:3389 /f', lines)
        self.assertIn('http://100.75.20.9:6082/vnc.html', lines)
        self.assertNotIn(self.env['RDP_PASSWORD'], lines)
        self.assertNotIn(self.env['VNC_PASSWORD'], lines)

    def test_html_dashboard_omits_password(self):
        summary, html = legacy_dashboard.content('access', self.cfg, self.rows, {}, '42', '1')
        self.assertIn('Mode password RDP', summary)
        self.assertIn('mstsc /v:100.75.20.9:3389 /f', summary)
        self.assertNotIn(self.env['RDP_PASSWORD'], summary + html)


if __name__ == '__main__':
    unittest.main(verbosity=2)
