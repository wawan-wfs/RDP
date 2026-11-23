# Second-pass CLI recovery. Selected applications get independent bounded attempts.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$cfg = Get-Content "$env:WFS_STATE/config.json" -Raw | ConvertFrom-Json
. (Join-Path $env:RUNNER_TEMP 'rdp-install-helpers.ps1')
$prefix = Join-Path $env:ProgramData 'RDP-Tools\npm'
New-Item -ItemType Directory -Path $prefix -Force | Out-Null
$node = @("$env:ProgramFiles\nodejs\node.exe", (Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) 'nodejs\node.exe')) |
  Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $node) { throw 'Node.js missing; cannot repair CLI tools' }
$npmCli = Join-Path (Split-Path $node -Parent) 'node_modules\npm\bin\npm-cli.js'
if (-not (Test-Path $npmCli)) { throw 'npm-cli.js missing from installed Node.js' }
$packages = [ordered]@{}
if ($cfg.router_choice -in @('9router','both')) { $packages['9Router'] = @('9router','9router') }
if ($cfg.coding_agent_choice -in @('codex','both')) { $packages['Codex CLI'] = @('@openai/codex','codex') }
if ($cfg.ai_agent_choice -in @('opencode','all')) { $packages['OpenCode'] = @('opencode-ai','opencode') }
if ($cfg.ai_agent_choice -in @('openclaw','both','all')) { $packages['OpenClaw'] = @('openclaw','openclaw') }
$nodeDir = Split-Path $node -Parent
$machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
$parts = @($machinePath -split ';' | Where-Object { $_ })
foreach ($part in @($prefix,$nodeDir)) {
  if ($part -notin $parts) { $parts += $part }
}
[Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'Machine')
$env:PATH = "$prefix;$nodeDir;" + $env:PATH
if ($env:GITHUB_PATH) { $prefix | Add-Content $env:GITHUB_PATH -Encoding UTF8 }
$installed = 0
$missing = 0
foreach ($entry in $packages.GetEnumerator()) {
  $name = [string]$entry.Key
  $package = [string]$entry.Value[0]
  $command = [string]$entry.Value[1]
  $target = Join-Path $prefix "$command.cmd"
  if (Test-Path $target -PathType Leaf) {
    Write-Host "[WFS/REPAIR] $name: detected at $target; no download"
    $installed++
    continue
  }
  Write-Host "::group::WFS Recovery / $name"
  try {
    Write-Host "[WFS/REPAIR] Installing official npm package $package"
    # Invoke node.exe directly. Native arguments remain separate even when
    # its Program Files installation path contains spaces.
    $nativeArgs = @(
      ('"{0}"' -f $npmCli), 'install', '--global', '--prefix',
      ('"{0}"' -f $prefix), '--no-audit', '--no-fund', '--no-progress',
      '--fetch-retries=1', '--fetch-timeout=60000', ('"{0}@latest"' -f $package)
    )
    $exitCode = Invoke-BoundedInstaller -FilePath $node -Arguments $nativeArgs -TimeoutSeconds 145
    if ($exitCode -notin @(0,3010) -or -not (Test-Path $target -PathType Leaf)) {
      throw "npm exited $exitCode or executable missing"
    }
    Write-Host "[WFS/REPAIR] $name: executable verified at $target"
    $installed++
  } catch {
    $missing++
    Write-Warning "[WFS/REPAIR] $name: $($_.Exception.Message)"
  } finally {
    Write-Host '::endgroup::'
  }
}
Write-Host "::notice title=WFS CLI recovery::$installed CLI executables verified; $missing missing after retry"
