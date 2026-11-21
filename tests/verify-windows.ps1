$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
foreach ($script in Get-ChildItem (Join-Path $root 'windows') -Filter *.ps1) {
  $tokens=$null; $errors=$null
  [Management.Automation.Language.Parser]::ParseFile($script.FullName,[ref]$tokens,[ref]$errors) | Out-Null
  if ($errors.Count) { throw "$($script.Name): $($errors | Out-String)" }
}
& (Join-Path $root 'windows/Test-Workspace-InstallStatus.ps1')

. (Join-Path $root 'windows/Workspace-Privileges.ps1')
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
$expected = $principal.IsInRole([Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'))
if ((Test-WorkspaceAdministrator) -ne $expected) { throw 'Administrator check differs from built-in SID' }
Write-Host "WFS/SECURITY SID-based elevation probe passed (elevated=$expected)"
