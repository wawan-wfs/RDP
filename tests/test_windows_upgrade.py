"""Static validation for the Windows legacy-source upgrade: no remote session needed."""
import unittest,sys
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
class Regression(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.source=(ROOT/'.github/workflows/windows-remote-workspace.yml').read_text(encoding='utf8')
  cls.wf=yaml.safe_load(cls.source)
  cls.steps=cls.wf['jobs']['secure-rdp']['steps']
 def test_name_manual_trigger_three_workflows(self):
  self.assertEqual(self.wf['name'],'WFS Windows Remote Workspace')
  self.assertEqual(set(self.wf['on']),{'workflow_dispatch'})
  self.assertEqual(len(list((ROOT/'.github/workflows').glob('*.yml'))),3)
 def test_x64_fallback_for_gui(self):
  self.assertIn("inputs.ide_choice != 'none'",self.wf['jobs']['secure-rdp']['runs-on'])
  self.assertIn("inputs.editor_choice != 'none'",self.wf['jobs']['secure-rdp']['runs-on'])
  self.assertIn("inputs.metatrader_choice != 'none'",self.wf['jobs']['secure-rdp']['runs-on'])
 def test_no_pinned_legacy_installer_versions(self):
  self.assertNotIn('CapCut_9_4_0_4015',self.source)
  self.assertNotIn('releases/download/v0.3.2',self.source)
  self.assertIn('releases/latest',self.source)
  self.assertIn('SHA256SUMS',self.source)
 def test_app_installer_and_audit_before_dashboard(self):
  names=[s.get('name','') for s in self.steps]
  i=lambda x:next(k for k,n in enumerate(names) if x in n)
  self.assertLess(i('Install verified OmniRoute'),i('Publish real app shortcuts'))
  self.assertLess(i('Audit installed apps'),i('Publish app status'))
  self.assertIn('python -m windows.app_audit',self.source)
 def test_shortcuts_single_desktop(self):
  self.assertNotIn('$shortcutDirectories += Join-Path $rdpProfile "Desktop"',self.source)
  self.assertIn('$duplicate = Join-Path $rdpProfile "Desktop',self.source)
 def test_cli_fallback_and_mt5_verification(self):
  self.assertIn("'@anthropic-ai/claude-code' { 'claude' }",self.source)
  self.assertIn('MetaTrader $Version verified',self.source)
  self.assertIn('ByteDance.CapCut',self.source)
  self.assertIn("ProgramFiles 'ArtCraft\\ArtCraft Launcher\\artcraft-launcher.exe'",self.source)
  self.assertIn('HKCU:\\Software\\Learning Machines LLC\\ArtCraft Launcher',self.source)

 def test_all_selected_apps_not_starved_by_optional_failures(self):
  src=self.source
  self.assertNotIn("if ($Name -in @('CapCut', 'Codex CLI', 'Claude Code')) { throw }",src)
  self.assertNotIn("Install-NpmGlobalPackage -PackageName 'omniroute'",src)
  self.assertIn("Invoke-BoundedInstaller -FilePath $env:ComSpec",src)
  self.assertIn("Write-Warning \"⚠️ Some installation groups failed:",src)
  a=src.index("Add-InstallTask -Name 'gui'")
  g=src[a:src.index("Add-InstallTask -Name 'cli'",a)]
  self.assertLess(g.index("Install-MetaTrader -Version 'mt4'"),g.index("if ($wantedAntigravity)"))
  self.assertLess(g.index("Install-MetaTrader -Version 'mt5'"),g.index("Install-CapCutForRdp"))
  self.assertIn("& $ctx.Winget install --id ByteDance.CapCut",src)
  self.assertNotIn(" $args += @('--id','ByteDance.CapCut'",src)

 def test_artcraft_and_cli_recovery_paths(self):
  src=self.source
  self.assertIn('windows/artcraft_portable.ps1',src)
  self.assertIn('windows/repair_cli.ps1',src)
  self.assertLess(src.index('13c ·'),src.index('14 ·'))
  self.assertLess(src.index('13d ·'),src.index('14 ·'))
  art=(ROOT/'windows/artcraft_portable.ps1').read_text(encoding='utf8')
  self.assertIn('SHA256SUMS.txt',art)
  self.assertIn('Get-FileHash',art)
  self.assertIn('ARTCRAFT_EXE=',art)
  cli=(ROOT/'windows/repair_cli.ps1').read_text(encoding='utf8')
  self.assertIn('Invoke-BoundedInstaller',cli)
  self.assertIn('opencode-ai',cli)
  self.assertIn('@openai/codex',cli)

 def test_capcut_interactive_repair_is_not_claimed_installed(self):
  self.assertIn('windows/capcut_logon.ps1',self.source)
  s=(ROOT/'windows/capcut_logon.ps1').read_text(encoding='utf8')
  self.assertIn('Install-CapCut-For-RDP.ps1',s)
  self.assertIn('Startup',s)
  self.assertIn('CapCut-Install.log',s)
  audit=(ROOT/'windows/app_audit.py').read_text(encoding='utf8')
  self.assertIn("'pending interactive'",audit)
  self.assertIn('capcut-pending.txt',audit)

 def test_no_secret_in_summary_or_logs(self):
  s=(ROOT/'windows/legacy_dashboard.py').read_text(encoding='utf8')
  self.assertNotIn('RDP_PASSWORD=',s)
  self.assertNotIn('VNC_PASSWORD=',s)
  self.assertIn('tailnet_ipv4',s)
if __name__=='__main__':unittest.main(verbosity=2)