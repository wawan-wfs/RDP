$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
foreach ($script in Get-ChildItem (Join-Path $root 'windows') -Filter *.ps1) {
  $tokens=$null; $errors=$null
  [Management.Automation.Language.Parser]::ParseFile($script.FullName,[ref]$tokens,[ref]$errors) | Out-Null
  if ($errors.Count) { throw "$($script.Name): $($errors | Out-String)" }
}
& (Join-Path $root 'windows/Test-Workspace-InstallStatus.ps1')
