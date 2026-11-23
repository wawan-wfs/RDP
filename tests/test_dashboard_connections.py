import os,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from windows import legacy_dashboard as ld
class Conn(unittest.TestCase):
 def test_rdp_command_and_ip_shown_no_password(self):
  cfg={'windows_version':'windows-2025','remote_access':'rdp','rdp_username':'RDP','hostname':'rdp-runner','duration_hours':'6'}
  rows=[('Tailnet','ready','IPv4 100.77.8.9'),('Windows RDP','ready','mstsc /v:100.77.8.9:3389; user RDP; NLA enabled')]
  md,html=ld.content('access',cfg,rows,{},'99','1')
  self.assertIn('mstsc /v:100.77.8.9:3389 /f',md)
  self.assertIn('Tailscale IPv4',html)
  self.assertIn('rdp-runner',html)
  self.assertIn('Mode password RDP',md)
  self.assertNotIn('RDP_PASSWORD=',md)
 def test_both_mode_partial_when_novnc_missing(self):
  cfg={'remote_access':'both','rdp_username':'RDP','hostname':'rdp-runner'}
  rows=[('Tailnet','ready','IPv4 100.111.1.2'),('Windows RDP','ready','mstsc /v:100.111.1.2:3389'),('Windows noVNC','failed','Probe timed out')]
  md,html=ld.content('access',cfg,rows,{},'99','1')
  self.assertIn('PARTIAL ACCESS',md)
  self.assertNotIn('Workspace · READY',md)
  console='\n'.join(ld.console_access_lines(cfg,rows))
  self.assertIn('FAILED',console)
  self.assertNotIn('noVNC URL        : http',console)

 def test_public_ip_not_shown(self):
  cfg={'hostname':'rdp-runner','remote_access':'rdp','rdp_username':'RDP'}
  rows=[('Tailnet','ready','IPv4 8.8.8.8'),('Windows RDP','ready','mstsc /v:8.8.8.8:3389')]
  md,html=ld.content('access',cfg,rows,{},'99','1')
  self.assertIn('| Windows RDP | `Belum siap` |',md)
  self.assertIn('Belum siap',md)
if __name__=='__main__':unittest.main(verbosity=2)