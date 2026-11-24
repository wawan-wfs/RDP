"""Unit/safety regression suite for the user-supplied Windows YAML as base."""
import sys,unittest,json,re,tempfile,os
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from windows import legacy_dashboard
from shared import workspace

class Legacy(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.text=(ROOT/'.github/workflows/windows-remote-workspace.yml').read_text(encoding='utf8')
  cls.data=yaml.load(cls.text,Loader=yaml.BaseLoader)
  cls.steps=cls.data['jobs']['secure-rdp']['steps']
 def test_only_three_launch_workflows(self):
  self.assertEqual({x.name for x in (ROOT/'.github/workflows').glob('*.yml')},{'windows-remote-workspace.yml','linux-remote-workspace.yml','macos-remote-workspace.yml'})
  self.assertEqual(set(self.data['on']),{'workflow_dispatch'})
 def test_legacy_choice_parity(self):
  options=self.data['on']['workflow_dispatch']['inputs']
  for name in ('ide_choice','editor_choice','metatrader_choice','router_choice','coding_agent_choice','ai_agent_choice','install_artcraft','windows_version','duration_hours','hostname_mode','rdp_password_mode'):
   self.assertIn(name,options)
  for name in ('remote_access','novnc_transport','vnc_password_mode','rdp_user_role','desktop_profile','rdp_username','validation_only'):
   self.assertIn(name,options)
  self.assertEqual(options['remote_access']['default'],'rdp')
  self.assertEqual(options['rdp_username']['default'],'RDP')
 def test_access_credentials_are_opt_in(self):
  options=self.data['on']['workflow_dispatch']['inputs']
  self.assertIn('reveal_random_password',options)
  self.assertEqual(options['reveal_random_password']['default'],'false')
  reveal=next(x for x in self.steps if 'windows.access_credentials' in x.get('run',''))
  self.assertIn('inputs.reveal_random_password',reveal['if'])
  self.assertIn('secrets.RDP_PASSWORD',reveal['env']['RDP_PASSWORD'])
  self.assertIn('secrets.VNC_PASSWORD',reveal['env']['VNC_PASSWORD'])
  normal=next(x for x in self.steps if 'windows.legacy_dashboard access' in x.get('run',''))
  self.assertNotIn('RDP_PASSWORD',normal.get('env',{}))
  self.assertNotIn('VNC_PASSWORD',normal.get('env',{}))

 def test_original_app_functions_preserved(self):
  for marker in ('function Install-CapCutForRdp','function Install-ClaudeForRdp','function Install-MetaTrader','function Install-ArtCraft','function Invoke-RdpUserTask','function Add-InstallTask','Google.AntigravityIDE','Google.Chrome','OpenAI.chatgpt','cweijan.vscode-office','hlkenndednhfkekhgcdicdfddnkalmdm','fdpohaocaechififmbbbbbknoalclacl','MetaTrader 5','New-AppShortcut','RDP-Setup'):
   with self.subTest(marker=marker): self.assertIn(marker,self.text)
 def test_secrets_not_printed(self):
  self.assertNotIn('Password: $password',self.text)
  self.assertNotIn('"``$env:RDP_PASSWORD``"',self.text)
  self.assertIn('::add-mask::',self.text)
 def test_preflight_and_remote_before_apps(self):
  titles=[x['name'] for x in self.steps]
  remote=next(i for i,s in enumerate(self.steps) if s.get('id')=='remote')
  install=next(i for i,s in enumerate(self.steps) if s.get('id')=='legacy_apps')
  self.assertLess(remote,install)
  self.assertTrue(all(x.get('id') not in ('remote','legacy_apps') or x.get('if') for x in self.steps))
  self.assertEqual(len(titles),len(set(titles)))
  self.assertIn('tailscale/github-action',self.text)
 def test_firewall_safe_fail_closed(self):
  s=(ROOT/'windows/remote.ps1').read_text(encoding='utf8')
  self.assertNotIn('-InterfaceAlias',s)
  self.assertNotIn('0.0.0.0-100.63.255.255',s)
  self.assertIn('DefaultInboundAction',s)
  self.assertIn('Set-NetFirewallProfile -Profile $profile.Name -Enabled True -DefaultInboundAction Block',s)
  self.assertIn("$env:RUNNER_ENVIRONMENT -ne 'github-hosted'",s)
  self.assertIn('Get-NetFirewallProfile -PolicyStore ActiveStore',s)
  self.assertIn('firewall-before.json',s)
  self.assertIn('Set-NetFirewallProfile -Profile $saved.name',s)
  self.assertIn("if ($saved.enabled) { 'True' } else { 'False' }",s)
  self.assertNotIn("-Enabled ([bool]$saved.enabled)",s)
  self.assertIn("[ValidateSet('start','browser','cleanup')]",s)
  self.assertIn("if ($Phase -eq 'browser'",s)
  self.assertIn('-RemoteAddress \'100.64.0.0/10\'',s)
  self.assertIn('SecurityLayer 2',s)
  self.assertIn('UserAuthentication 1',s)
 def test_novnc_independent_timeout_and_continued_apps(self):
  steps=self.steps
  remote=next(x for x in steps if x.get('id')=='remote')
  browser=next(x for x in steps if x.get('id')=='browser')
  apps=next(x for x in steps if x.get('id')=='legacy_apps')
  self.assertLessEqual(int(remote['timeout-minutes']),12)
  self.assertLessEqual(int(browser['timeout-minutes']),12)
  self.assertEqual(browser['continue-on-error'],'true')
  self.assertIn('steps.remote.outcome',browser['if'])
  self.assertIn('steps.remote.outcome',apps['if'])
  self.assertNotIn('steps.browser.outcome',apps['if'])
  self.assertTrue(any(x.get('name','').startswith('06a2') for x in steps))
  self.assertIn('windows.record_novnc_failure',self.text)
  self.assertIn('windows.legacy_dashboard console',self.text)
  titles=[s['name'] for s in steps]
  early=next(i for i,title in enumerate(titles) if title.startswith('06-primary'))
  self.assertLess(titles.index(remote['name']),early)
  self.assertLess(early,titles.index(browser['name']))

 def test_novnc_failfast_probe_is_bounded(self):
  remote=(ROOT/'windows/remote.ps1').read_text(encoding='utf8')
  self.assertIn('novnc_probe.py',remote)
  self.assertIn('-TimeoutSeconds 25',remote)
  self.assertNotIn('test_novnc.py" --live',remote)
  self.assertIn('python windows/test_novnc_probe.py',self.text)
  self.assertIn('WFS/APP/SELECT',(ROOT/'windows/legacy_dashboard.py').read_text(encoding='utf8'))

 def test_serve_route_verified_before_browser_ready(self):
  remote=(ROOT/'windows/remote.ps1').read_text(encoding='utf8')
  self.assertIn('python -m windows.serve_verify $kind $port $target $dns',remote)
  self.assertIn("Ts-Serve https 443 'http://127.0.0.1:6081' $dns",remote)
  self.assertIn('Serve mapping verified',remote)
  self.assertIn('python windows/test_serve_verify.py',self.text)
  self.assertLess(remote.index('windows.serve_verify'),remote.index("Status 'Windows noVNC' 'ready'"))

 def test_novnc_msi_magic_and_fallback(self):
  s=(ROOT/'windows/remote.ps1').read_text(encoding='utf8')
  for part in ('D0CF11E0A1B11AE1','Get-AuthenticodeSignature','GlavSoft.TightVNC','SERVER_ADD_FIREWALL_EXCEPTION=0','SET_LOOPBACKONLY=1','VNC loopback/auth gate failed'):
   self.assertIn(part,s)
 def test_dashboards_escape_content(self):
  cfg=workspace.config('windows',{})
  summary,html=legacy_dashboard.content('access',cfg,[('Demo<script>','failed','Bad <h1>'),('Windows noVNC','ready','http://8.8.8.8:6082/vnc.html')],{},'10','1')
  self.assertIn('Demo&lt;script&gt;',html)
  self.assertNotIn('Bad <h1>',html)
  self.assertNotIn('href="http://8.8.8.8',html)
  self.assertIn('SETUP FAILED' if 'SETUP FAILED' in html else 'READY',html)
 def test_msi_restore_protects_self_hosted(self):
  s=(ROOT/'windows/restore-msi-policy.ps1').read_text(encoding='utf8')
  self.assertIn("$env:RUNNER_ENVIRONMENT -ne 'github-hosted'",s)
  self.assertIn('DisableUserInstalls',s)
 def test_duration_preserves_cleanup(self):
  self.assertLessEqual(int(self.data['jobs']['secure-rdp']['timeout-minutes']),360)
  final=self.steps[-1]
  self.assertIn('always()',final['if'])
  self.assertIn('Phase cleanup',final['run'])

if __name__=='__main__':unittest.main(verbosity=2)