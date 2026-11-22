import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from windows.app_audit import requested,inspect,roots

class AppAudit(unittest.TestCase):
 def test_selection(self):
  c={'ide_choice':'both','editor_choice':'both','metatrader_choice':'both','router_choice':'omniroute','coding_agent_choice':'both','ai_agent_choice':'none','install_artcraft':True,'rdp_username':'RDP'}
  w=requested(c)
  self.assertTrue(all(w[x] for x in ('VS Code','Antigravity IDE','CapCut','Shotcut','MetaTrader 4','MetaTrader 5','OmniRoute','Codex CLI','Claude Code','ArtCraft Launcher')))
  self.assertFalse(w['9Router'])
 def test_known_paths_and_missing_status(self):
  c={'ide_choice':'vscode','editor_choice':'none','metatrader_choice':'none','router_choice':'none','coding_agent_choice':'none','ai_agent_choice':'none','install_artcraft':False,'rdp_username':'RDP'}
  env={'ProgramFiles':'C:/Program Files','ProgramFiles(x86)':'C:/x86','LOCALAPPDATA':'C:/Users/runneradmin/AppData/Local','ProgramData':'C:/ProgramData'}
  rows=inspect(c,exists=lambda p: str(p).endswith('Microsoft VS Code/Code.exe'),env=env)
  self.assertEqual([x[1] for x in rows if x[0]=='VS Code'],['installed'])
  self.assertEqual([x[1] for x in rows if x[0]=='Chrome'],['failed'])
 def test_no_password_logged(self):
  from windows.app_audit import candidates
  c={'rdp_username':'RDP'}
  s=str(candidates(c))
  self.assertNotIn('RDP_PASSWORD',s)
  self.assertNotIn('VNC_PASSWORD',s)

if __name__=='__main__':unittest.main(verbosity=2)