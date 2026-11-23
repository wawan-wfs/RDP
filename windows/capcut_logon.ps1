# CapCut can require a real RDP profile. Schedule a one-time install attempt
# in the selected user's desktop, with a log and manual Start Menu retry shortcut.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$cfg = Get-Content "$env:WFS_STATE/config.json" -Raw | ConvertFrom-Json
if ($cfg.editor_choice -notin @('capcut','both')) { return }
$rdp = [string]$cfg.rdp_username
$profile = Join-Path $env:SystemDrive ("Users\" + $rdp)
$existing = @(
  "$profile\AppData\Local\Programs\CapCut\CapCut.exe",
  "$profile\AppData\Local\CapCut\CapCut.exe"
) | Where-Object { Test-Path $_ -PathType Leaf } | Select-Object -First 1
if ($existing) { Write-Host '[WFS/CAPCUT] Executable already present; no logon retry required'; return }
$directory = Join-Path $env:ProgramData 'WFS-Apps\CapCut'
New-Item $directory -ItemType Directory -Force | Out-Null
$scriptFile = Join-Path $directory 'Install-CapCut-For-RDP.ps1'
$body = @'
$ErrorActionPreference = 'Continue'
$expected = '__WFS_RDP_USERNAME__'
if ($env:USERNAME -ine $expected) { exit 0 }
$logDir = Join-Path $env:LOCALAPPDATA 'WFS'
New-Item $logDir -ItemType Directory -Force | Out-Null
$log = Join-Path $logDir 'CapCut-Install.log'
Start-Transcript -Path $log -Append -ErrorAction SilentlyContinue | Out-Null
try {
  $roots = @("$env:LOCALAPPDATA\Programs\CapCut", "$env:LOCALAPPDATA\CapCut")
  $findExe = { @($roots | ForEach-Object { Get-ChildItem $_ -Recurse -Filter CapCut.exe -File -ErrorAction SilentlyContinue } | Select-Object -First 1)[0] }
  $exe = & $findExe
  if (-not $exe) {
    $winget = (Get-Command winget.exe -ErrorAction SilentlyContinue).Source
    if (-not $winget) { throw 'WinGet unavailable in RDP user profile' }
    Write-Host '[WFS/CAPCUT] Installing latest catalog package in the interactive RDP user context'
    & $winget install --id ByteDance.CapCut --exact --source winget --scope user --silent --accept-package-agreements --accept-source-agreements --disable-interactivity | Out-Host
    $exitCode = $LASTEXITCODE
    $exe = & $findExe
    if (-not $exe) { throw "CapCut executable not detected after WinGet exit $exitCode" }
  }
  $shell = New-Object -ComObject WScript.Shell
  $shortcut = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'CapCut.lnk'))
  $shortcut.TargetPath = $exe.FullName
  $shortcut.WorkingDirectory = Split-Path $exe.FullName -Parent
  $shortcut.Save()
  Write-Host "[WFS/CAPCUT] Executable verified in RDP profile: $($exe.FullName)"
} catch {
  Write-Warning ('[WFS/CAPCUT] ' + $_.Exception.Message)
} finally {
  Stop-Transcript -ErrorAction SilentlyContinue | Out-Null
}
'@
$body = $body.Replace('__WFS_RDP_USERNAME__',$rdp.Replace("'","''"))
[IO.File]::WriteAllText($scriptFile,$body,[Text.UTF8Encoding]::new($true))
$shell = New-Object -ComObject WScript.Shell
$startupDir = Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\Startup'
$programsDir = Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs'
$target = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $scriptFile
$startup = $shell.CreateShortcut((Join-Path $startupDir 'WFS CapCut RDP Setup.lnk'))
$startup.TargetPath = $target
$startup.Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f $scriptFile
$startup.Save()
$manual = $shell.CreateShortcut((Join-Path $programsDir 'Install or Repair CapCut for RDP.lnk'))
$manual.TargetPath = $target
$manual.Arguments = $arguments
$manual.Save()
New-Item (Join-Path $env:ProgramData 'WFS-Apps\capcut-pending.txt') -ItemType File -Force | Out-Null
Write-Host '::notice title=WFS CapCut::CapCut is missing after silent setup; a retry is prepared for RDP user logon, with a Start Menu repair shortcut and a per-user log.'
