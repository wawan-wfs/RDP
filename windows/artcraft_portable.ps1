# Verified official portable fallback for ArtCraft MSI.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$cfg = Get-Content "$env:WFS_STATE/config.json" -Raw | ConvertFrom-Json
if (-not $cfg.install_artcraft) { Write-Host '[WFS/ARTCRAFT] Not requested'; return }
$candidates = @(
  "$env:ProgramFiles\ArtCraft\ArtCraft Launcher\artcraft-launcher.exe",
  "$env:ProgramFiles\ArtCraft Launcher\artcraft-launcher.exe",
  "$env:SystemDrive\Users\$($cfg.rdp_username)\AppData\Local\Programs\ArtCraft\ArtCraft Launcher\artcraft-launcher.exe"
)
$found = @($candidates | Where-Object { Test-Path $_ -PathType Leaf } | Select-Object -First 1)[0]
$root = Join-Path $env:ProgramData 'WFS-Apps\ArtCraft'
if (-not $found -and (Test-Path $root)) {
  $found = @(Get-ChildItem -Path $root -Filter 'artcraft-launcher.exe' -File -Recurse -Depth 4 -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName)[0]
}
if (-not $found) {
  $headers = @{ 'User-Agent' = 'WFS-RDP-Installer'; Accept = 'application/vnd.github+json' }
  $release = Invoke-RestMethod 'https://api.github.com/repos/storytold/craft-launcher/releases/latest' -Headers $headers -TimeoutSec 30 -ErrorAction Stop
  if ([string]$release.tag_name -notmatch '^v[0-9]+\.[0-9]+\.[0-9]+$') { throw 'Invalid latest ArtCraft release tag' }
  $asset = @($release.assets | Where-Object { $_.name -match '^artcraft-launcher-[0-9.]+-windows-x64-portable\.zip$' } | Select-Object -First 1)[0]
  $sumAsset = @($release.assets | Where-Object { $_.name -eq 'SHA256SUMS.txt' } | Select-Object -First 1)[0]
  if (-not $asset -or -not $sumAsset) { throw 'Latest release missing portable ZIP or SHA256SUMS.txt' }
  foreach ($item in @($asset,$sumAsset)) {
    if (([uri]$item.browser_download_url).Host -ne 'github.com') { throw 'Portable asset host not trusted' }
  }
  $downloadDir = Join-Path $env:RUNNER_TEMP 'wfs-artcraft-portable'
  New-Item $downloadDir -ItemType Directory -Force | Out-Null
  $archive = Join-Path $downloadDir $asset.name
  $sums = Join-Path $downloadDir 'SHA256SUMS.txt'
  Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $archive -TimeoutSec 100 -ErrorAction Stop
  Invoke-WebRequest -Uri $sumAsset.browser_download_url -OutFile $sums -TimeoutSec 35 -ErrorAction Stop
  $line = @(Get-Content $sums | Where-Object { $_ -match [regex]::Escape($asset.name) } | Select-Object -First 1)[0]
  if (-not $line -or $line -notmatch '^([0-9a-fA-F]{64})\s+') { throw 'Matching portable SHA256 checksum missing' }
  if ((Get-FileHash $archive -Algorithm SHA256).Hash -ne $Matches[1]) { throw 'Portable checksum mismatch' }
  New-Item $root -ItemType Directory -Force | Out-Null
  Write-Host "[WFS/ARTCRAFT] Extracting verified official portable version $($release.tag_name)"
  Expand-Archive -LiteralPath $archive -DestinationPath $root -Force
  $found = @(Get-ChildItem -Path $root -Filter 'artcraft-launcher.exe' -File -Recurse -Depth 4 -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName)[0]
  if (-not $found) { throw 'Verified portable archive did not contain launcher executable' }
}
Write-Host "[WFS/ARTCRAFT] Verified executable available: $found"
"ARTCRAFT_EXE=$found" | Add-Content $env:GITHUB_ENV -Encoding UTF8
