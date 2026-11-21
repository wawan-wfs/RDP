# Restore only settings modified by the uploaded legacy MSI policy step.
$ErrorActionPreference = 'Stop'
if ($env:RUNNER_ENVIRONMENT -ne 'github-hosted') { return }
$backup = Join-Path $env:ProgramData 'RDP-Setup\msi-policy-before.json'
if (-not (Test-Path -LiteralPath $backup)) { return }
$values = Get-Content -LiteralPath $backup -Raw | ConvertFrom-Json
$policy = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\Installer'
foreach ($name in @('DisableMSI','DisableUserInstalls')) {
  $old = $values.$name
  if ($null -eq $old) {
    Remove-ItemProperty -Path $policy -Name $name -ErrorAction SilentlyContinue
  } else {
    Set-ItemProperty -Path $policy -Name $name -Value ([int]$old) -ErrorAction Stop
  }
}
Remove-Item -LiteralPath $backup -Force
Write-Host '✅ WFS / MSI policy restored to original per-run state'