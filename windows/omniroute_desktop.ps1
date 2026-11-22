# Install only the verified latest official portable OmniRoute desktop binary.
# This is independent of the npm CLI used by the legacy workflow.
$ErrorActionPreference = 'Stop'
$cfg = Get-Content "$env:WFS_STATE/config.json" -Raw | ConvertFrom-Json
if ($cfg.router_choice -notin @('omniroute','both')) { Write-Host '[WFS/APP] OmniRoute desktop: not requested'; return }
$targetDir = Join-Path $env:ProgramData 'WFS-Apps\OmniRoute'
$targetExe = Join-Path $targetDir 'OmniRoute.exe'
try {
  $headers = @{ 'User-Agent'='WFS-RDP-Installer'; Accept='application/vnd.github+json' }
  $release = Invoke-RestMethod 'https://api.github.com/repos/cheaper-inference/OmniRoute/releases/latest' -Headers $headers -TimeoutSec 30
  $asset = @($release.assets | Where-Object { $_.name -eq 'OmniRoute.exe' } | Select-Object -First 1)[0]
  if (-not $asset) { throw 'Current OmniRoute release has no Windows portable OmniRoute.exe asset; CLI remains independent.' }
  if (([uri]$asset.browser_download_url).Host -ne 'github.com') { throw 'Unexpected OmniRoute download host' }
  $digest = [string]$asset.digest
  if ($digest -notmatch '^sha256:([a-fA-F0-9]{64})$') { throw 'Release asset has no verifiable SHA256 digest; refusing unverified executable' }
  $expected = $Matches[1].ToLowerInvariant()
  New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
  $tmp = Join-Path $targetDir 'OmniRoute.download.exe'
  try {
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $tmp -TimeoutSec 150 -ErrorAction Stop
    $item = Get-Item $tmp
    if ($item.Length -lt 1000000) { throw 'OmniRoute file too small to be a desktop executable' }
    $stream = [IO.File]::OpenRead($tmp)
    try { if ($stream.ReadByte() -ne 77 -or $stream.ReadByte() -ne 90) { throw 'OmniRoute PE header missing' } }
    finally { $stream.Dispose() }
    if ((Get-FileHash $tmp -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'OmniRoute asset SHA256 mismatch' }
    Move-Item $tmp $targetExe -Force
  } finally { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
  "OMNIROUTE_EXE=$targetExe" | Out-File -FilePath $env:GITHUB_ENV -Append -Encoding utf8
  & python shared/workspace.py status 'OmniRoute Desktop' installed "Official portable executable available; release $($release.tag_name)"
  Write-Host "::notice title=WFS OmniRoute::Verified official desktop executable, $($release.tag_name). Run from desktop after RDP login."
} catch {
  & python shared/workspace.py status 'OmniRoute Desktop' warning 'Official portable executable unavailable; npm CLI is separately verified'
  Write-Warning ("OmniRoute portable setup: " + $_.Exception.Message)
}