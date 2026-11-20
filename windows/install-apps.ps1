param([ValidateSet('base','gui','cli','all')][string] $Group = 'all')
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
Set-Location (Split-Path $PSScriptRoot -Parent)
. "$PSScriptRoot/Workspace-InstallStatus.ps1"
$c = Get-Content "$env:WFS_STATE/config.json" -Raw | ConvertFrom-Json
$env:WFS_INSTALL_STATUS_DIR = "$env:WFS_STATE/app-status"
New-Item -ItemType Directory -Path $env:WFS_INSTALL_STATUS_DIR -Force | Out-Null
$programs = Join-Path $env:ProgramData 'WFS Workspace'
New-Item -ItemType Directory -Path $programs -Force | Out-Null
$menu = Join-Path $env:ProgramData 'Microsoft/Windows/Start Menu/Programs/WFS Workspace'
New-Item -ItemType Directory -Path $menu -Force | Out-Null
$pf = @($env:ProgramFiles,${env:ProgramFiles(x86)}) | Where-Object { $_ }
$winget = (Get-Command winget.exe -ErrorAction SilentlyContinue).Source
if (-not $winget) { $winget = (Get-ChildItem "$env:ProgramFiles/WindowsApps/Microsoft.DesktopAppInstaller_*/winget.exe" -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1).FullName }
$choco = (Get-Command choco.exe -ErrorAction SilentlyContinue).Source

function Status($n,$s,$d) { & python shared/workspace.py status $n $s $d }
function Candidates([string] $sub) { $pf | ForEach-Object { Join-Path $_ $sub } }
function Locate([string[]] $paths) { $paths | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1 }
function Shortcut([string] $name,[string] $exe,[string] $args = '') {
  if (-not $exe) { return }
  $shell = New-Object -ComObject WScript.Shell
  $link = $shell.CreateShortcut((Join-Path $menu "$name.lnk"))
  $link.TargetPath = $exe
  $link.Arguments = $args
  $link.Save()
  if ($name -notmatch '^Configure ') {
    $public = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) "WFS $name.lnk"))
    $public.TargetPath = $exe
    $public.Arguments = $args
    $public.Save()
  }
}
function Queue-AtLogon([string]$key,[string]$file,[string]$commandArgs) {
  if (-not (Test-Path "$env:WFS_STATE/user-owned")) { return }
  $account = "$env:COMPUTERNAME\$($c.rdp_username)"
  $taskName = "WFS-UserApps-$env:GITHUB_RUN_ID-$env:GITHUB_RUN_ATTEMPT-$key"
  try {
    $once = Join-Path $programs "$key-once.ps1"
    # All script names and options below are fixed by this repository.
    $oncePath = "'" + $file.Replace("'","''") + "'"
    $marker = "'" + $key + ".v1.success'"
    $script = @(
      '$ErrorActionPreference = "Stop"'
      '$parent = Join-Path $env:LOCALAPPDATA "WFS-Workspace"'
      'New-Item -Path $parent -ItemType Directory -Force | Out-Null'
      ('$stamp = Join-Path $parent '+$marker)
      'if (Test-Path -LiteralPath $stamp) { exit 0 }'
      ('& '+$oncePath+' '+$commandArgs)
      'if ($LASTEXITCODE -in @($null,0)) { Set-Content -LiteralPath $stamp -Value complete }'
    )
    Set-Content -LiteralPath $once -Value $script -Encoding utf8BOM
    $action = New-ScheduledTaskAction -Execute (Join-Path $PSHOME 'pwsh.exe') -Argument ('-NoLogo -NoProfile -NonInteractive -File "{0}"' -f $once)
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([timespan]::FromMinutes(7)) -MultipleInstances IgnoreNew
    $principal = New-ScheduledTaskPrincipal -UserId $account -LogonType Interactive -RunLevel Limited
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $account
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
  } catch { Write-Warning "Could not queue per-user setup $key; Start Menu fallback is available." }
}
function Choice($choice,$one) { $choice -in @($one,'both','all') }
function Report-App($name,[scriptblock]$action) {
  $result = 'installed'
  $detail = 'Verified executable, package or configured policy'
  try {
    $output = & $action
    if ('pending interactive' -in $output) { $result='pending interactive'; $detail='Use the WFS shortcut in the remote session' }
    if ('unsupported' -in $output) { $result='unsupported'; $detail='No validated native package for this image' }
  } catch [TimeoutException] { $result='timed out'; $detail='Installer process stopped at its timeout' }
    catch { $result='failed'; $detail='Installer or post-install verification failed'; Write-Warning ("$name failed: " + $_.Exception.Message) }
  Status $name $result $detail
}
function Package($id,$chocoId,[string[]]$paths,[int]$timeout = 240,[switch]$allowUser) {
  $target = Locate $paths
  if ($target) { return $target }
  if ($winget) {
    $args = @('install','--id',$id,'--exact','--source','winget','--silent','--accept-package-agreements','--accept-source-agreements','--disable-interactivity')
    if (-not $allowUser) { $args += @('--scope','machine') }
    $code = Invoke-BoundedInstaller $winget $args $timeout
    if ($code -notin 0,3010,1641 -and -not (Locate $paths)) { throw "Winget returned $code for $id" }
  } elseif ($choco -and $chocoId) {
    $code = Invoke-BoundedInstaller $choco @('install',$chocoId,'-y','--no-progress') $timeout
    if ($code -notin 0,3010,1641) { throw "Chocolatey returned $code for $id" }
  } else { throw "No approved package installer found for $id" }
  $target = Locate $paths
  if (-not $target) { throw "Executable for $id was not found in known locations" }
  return $target
}
function Verify-Signer($file,$issuer) {
  $s = Get-AuthenticodeSignature -FilePath $file
  if ($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch $issuer) { throw 'Unexpected or invalid installer signature' }
}
function Download($url,$path) { Invoke-WebRequest -Uri $url -OutFile $path -TimeoutSec 60 }
function Chrome-Policy {
  $key = 'HKLM:\SOFTWARE\Policies\Google\Chrome\ExtensionInstallForcelist'
  New-Item -Path $key -Force | Out-Null
  $existing = Get-ItemProperty -Path $key
  $ids = @('hlkenndednhfkekhgcdicdfddnkalmdm','fdpohaocaechififmbbbbbknoalclacl')
  foreach ($id in $ids) {
    if ($existing.PSObject.Properties.Value -match "^$id(?:;|$)") { continue }
    $number = 1
    while ($null -ne (Get-ItemPropertyValue -Path $key -Name ([string]$number) -ErrorAction SilentlyContinue)) { $number++ }
    New-ItemProperty -Path $key -Name ([string]$number) -Value "$id;https://clients2.google.com/service/update2/crx" -PropertyType String -Force | Out-Null
  }
}
function User-Winget-Setup([string]$id,[string]$app) {
  if (-not $winget) { throw 'Winget is unavailable for interactive fallback' }
  $key = $app -replace '[^A-Za-z0-9-]',''
  $installer = Join-Path $programs "$key-user-install.ps1"
  $script = @(
    '$ErrorActionPreference = "Stop"'
    '$exit = 1'
    ("winget install --id '"+$id+"' --exact --source winget --scope user --silent --accept-package-agreements --accept-source-agreements --disable-interactivity")
    '$exit = $LASTEXITCODE'
    'if ($exit -notin 0,3010,1641) { throw "WinGet exit $exit" }'
    '$global:LASTEXITCODE = 0'
  )
  Set-Content -LiteralPath $installer -Value $script -Encoding utf8BOM
  Queue-AtLogon $key $installer ''
  Shortcut "Install $app" (Join-Path $PSHOME 'pwsh.exe') ('-NoLogo -NoExit -NoProfile -File "{0}"' -f $installer)
  'pending interactive'
}
function Set-DefaultChrome {
  if ($env:RUNNER_ENVIRONMENT -ne 'github-hosted') { return }
  $assoc = Join-Path $programs 'DefaultAppAssociations.xml'
  @'
<?xml version="1.0" encoding="UTF-8"?>
<DefaultAssociations>
  <Association Identifier="http" ProgId="ChromeHTML" ApplicationName="Google Chrome" />
  <Association Identifier="https" ProgId="ChromeHTML" ApplicationName="Google Chrome" />
  <Association Identifier=".htm" ProgId="ChromeHTML" ApplicationName="Google Chrome" />
  <Association Identifier=".html" ProgId="ChromeHTML" ApplicationName="Google Chrome" />
</DefaultAssociations>
'@ | Set-Content -LiteralPath $assoc -Encoding utf8
  $policy = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\System'
  New-Item -Path $policy -Force | Out-Null
  New-ItemProperty -Path $policy -Name DefaultAssociationsConfiguration -Value $assoc -PropertyType String -Force | Out-Null
}
function Mt($v) {
  $file = Join-Path $programs "MetaTrader-$v-Setup.exe"
  $exes = if ($v -eq 'mt4') { @(Candidates 'MetaTrader 4 EXNESS/terminal.exe'; Candidates 'Exness MetaTrader 4/terminal.exe'; Candidates 'MetaTrader 4/terminal.exe') }
          else { @(Candidates 'MetaTrader 5/terminal64.exe') }
  $terminal = Locate $exes
  if (-not $terminal) {
    $url = if ($v -eq 'mt4') { 'https://download.terminal.free/cdn/web/exness.technologies.ltd/mt4/exness4setup.exe' }
           else { 'https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe' }
    Download $url $file
    Verify-Signer $file 'MetaQuotes|Exness'
    try { $null = Invoke-BoundedInstaller $file @('/auto') 200 } catch [TimeoutException] { Write-Warning 'Unattended installer timed out; using interactive fallback' }
    $terminal = Locate $exes
  }
  if ($terminal) {
    $terminalVersion = (Get-Item -LiteralPath $terminal).VersionInfo
    if ($terminalVersion.ProductName -notmatch 'MetaTrader') { throw 'Unexpected terminal product metadata' }
    Shortcut "MetaTrader $($v.Substring(2))" $terminal
  } else {
    Shortcut "Install MetaTrader $($v.Substring(2))" $file
    'pending interactive'
  }
}
function ArtCraft {
  $release = Invoke-RestMethod 'https://api.github.com/repos/craft-launcher/craft-launcher/releases/latest' -TimeoutSec 45
  $assets = @($release.assets | Where-Object { $_.name -match 'x86_64.*\.msi$|x64.*\.msi$' -and $_.digest -match '^sha256:[a-f0-9]{64}$' })
  if ($assets.Count -ne 1) { throw 'No unique x64 MSI with a release digest' }
  $asset = $assets[0]
  if ($asset.browser_download_url -notmatch '^https://github\.com/(craft-launcher|storytold)/craft-launcher/releases/download/') { throw 'Unexpected ArtCraft release location' }
  $target = Join-Path $programs 'ArtCraft-Setup.msi'
  Download $asset.browser_download_url $target
  if ((Get-FileHash $target -Algorithm SHA256).Hash.ToLower() -ne $asset.digest.Substring(7)) { throw 'ArtCraft installer checksum mismatch' }
  $code = Invoke-BoundedInstaller msiexec.exe @('/i',('"{0}"' -f $target),'/qn','/norestart','ALLUSERS=1') 180
  $binary = Locate @(Candidates 'ArtCraft/Launcher/artcraft-launcher.exe'; Candidates 'ArtCraft Launcher/artcraft-launcher.exe')
  if ($code -in 0,3010 -and $binary) { Shortcut 'ArtCraft Launcher' $binary }
  else { Shortcut 'Install ArtCraft Launcher' "$env:SystemRoot/System32/msiexec.exe" ('/i "{0}"' -f $target); 'pending interactive' }
}
function NpmApp($package,$bin,[int]$seconds = 300) {
  $node = Locate @(Candidates 'nodejs/node.exe')
  if (-not $node) { throw 'Node.js dependency missing' }
  $npm = Join-Path (Split-Path $node) 'node_modules/npm/bin/npm-cli.js'
  if (-not (Test-Path -LiteralPath $npm)) { throw 'npm-cli.js missing' }
  $prefix = Join-Path $programs $bin
  New-Item -ItemType Directory $prefix -Force | Out-Null
  $shim = Join-Path $prefix "$bin.cmd"
  $exe = "$env:SystemRoot/System32/cmd.exe"
  $stamp = Join-Path $prefix '.wfs-completed'
  if (-not (Test-Path -LiteralPath $shim) -or -not (Test-Path -LiteralPath $stamp)) {
    Remove-Item -LiteralPath $shim,$stamp -Force -ErrorAction SilentlyContinue
    $code = Invoke-BoundedInstaller $node @(('"{0}"' -f $npm),'install','--global','--prefix',('"{0}"' -f $prefix),'--include=optional','--no-audit','--no-fund','--fetch-retries=1','--fetch-timeout=60000',"$package@latest") $seconds
    if ($code -ne 0) { Remove-Item -LiteralPath $shim -Force -ErrorAction SilentlyContinue; throw "npm exited $code" }
  }
  if (-not (Test-Path -LiteralPath $shim)) { throw 'Installed CLI shim was not found' }
  if ($bin -in @('codex','opencode')) {
    $test = Invoke-BoundedInstaller $exe @('/D','/C',('""{0}" --version"' -f $shim)) 30
    if ($test -ne 0) { throw 'Installer verification via --version failed' }
  }
  Set-Content -LiteralPath $stamp -Value 'npm verified'
  Shortcut $bin $exe ('/D /K ""{0}""' -f $shim)
  $machinePath = [Environment]::GetEnvironmentVariable('Path','Machine')
  if ($prefix -notin ($machinePath -split ';')) { [Environment]::SetEnvironmentVariable('Path', "$machinePath;$prefix", 'Machine') }
}
function VendorNative($app) {
  $url = switch ($app) {
    'Claude Code' {'https://claude.ai/install.ps1'}
    'Hermes Agent' {'https://hermes-agent.nousresearch.com/install.ps1'}
    'OpenClaw' {'https://openclaw.ai/install.ps1'}
  }
  $opts = switch ($app) {
    'Hermes Agent' {@('-NonInteractive','-Branch','main')}
    'OpenClaw' {@('-NoOnboard')}
    default {@()}
  }
  # Install via desktop user instead of under the Actions runner's profile.
  # A fixed publisher URL is staged, without credentials or onboarding.
  $file = Join-Path $programs ($app.Replace(' ','-') + '-install.ps1')
  Download $url $file
  $info = Get-Item $file
  if ($info.Length -lt 100 -or $info.Length -gt 5MB) { throw 'Unexpected vendor script size' }
  $tokens=$null; $parse=$null
  [Management.Automation.Language.Parser]::ParseFile($file,[ref]$tokens,[ref]$parse) | Out-Null
  if ($parse.Count) { throw 'Vendor script invalid' }
  Queue-AtLogon ($app.Replace(' ','-')) $file ($opts -join ' ')
  Shortcut "Install $app" (Join-Path $PSHOME 'pwsh.exe') ('-NoLogo -NoExit -NoProfile -File "{0}" {1}' -f $file,($opts -join ' '))
  'pending interactive'
}

if ($Group -in 'base','all') {
  Report-App 'Chrome' {
    try { $chrome = Package 'Google.Chrome' 'googlechrome' @(Candidates 'Google/Chrome/Application/chrome.exe') }
    catch {
      $msi = "$env:WFS_STATE/chrome.msi"
      Download 'https://dl.google.com/dl/chrome/install/googlechromestandaloneenterprise64.msi' $msi
      Verify-Signer $msi 'Google'
      $null = Invoke-BoundedInstaller msiexec.exe @('/i',('"{0}"' -f $msi),'/qn','/norestart') 180
      $chrome = Locate @(Candidates 'Google/Chrome/Application/chrome.exe')
      if (-not $chrome) { throw 'Chrome binary unavailable' }
    }
    Shortcut 'Google Chrome' $chrome
    try { Set-DefaultChrome } catch { Write-Warning 'Chrome is installed but default browser policy could not be set' }
  }
  try { Chrome-Policy; Status 'Chrome extensions' 'configured' 'Cookie-Editor and GoFullPage policy; verify activation at chrome://extensions' }
  catch { Status 'Chrome extensions' 'failed' 'Managed policy could not be configured' }
  Report-App 'WinRAR' { Shortcut 'WinRAR' (Package 'RARLab.WinRAR' 'winrar' @(Candidates 'WinRAR/WinRAR.exe')) }
  Report-App 'Node.js LTS' { $null = Package 'OpenJS.NodeJS.LTS' 'nodejs-lts' @(Candidates 'nodejs/node.exe') }
}
if ($Group -in 'gui','all') {
  if (Choice $c.ide_choice 'vscode') { Report-App 'VS Code' {
    $exe = Package 'Microsoft.VisualStudioCode' 'vscode' @(Candidates 'Microsoft VS Code/Code.exe')
    Shortcut 'Visual Studio Code' $exe
    $codeCli = Join-Path (Split-Path $exe) 'bin/code.cmd'
    if (Test-Path $codeCli) {
      $cmd = "$env:SystemRoot/System32/cmd.exe"
      Shortcut 'Configure VS Code extensions' $cmd ('/D /K ""{0}" --install-extension OpenAI.chatgpt --force & "{0}" --install-extension cweijan.vscode-office --force"' -f $codeCli)
    }
  } }
  if (Choice $c.ide_choice 'antigravity') { Report-App 'Antigravity IDE' {
    try { Shortcut 'Antigravity IDE' (Package 'Google.AntigravityIDE' '' @(Candidates 'Antigravity IDE/Antigravity IDE.exe'; Candidates 'Antigravity/Antigravity.exe')) }
    catch { User-Winget-Setup 'Google.AntigravityIDE' 'Antigravity IDE' }
  } }
  if (Choice $c.editor_choice 'shotcut') { Report-App 'Shotcut' { Shortcut 'Shotcut' (Package 'Meltytech.Shotcut' 'shotcut' @(Candidates 'Shotcut/shotcut.exe')) } }
  if (Choice $c.editor_choice 'capcut') { Report-App 'CapCut' {
    try { Shortcut 'CapCut' (Package 'ByteDance.CapCut' '' @(Candidates 'CapCut/CapCut.exe')) }
    catch { User-Winget-Setup 'ByteDance.CapCut' 'CapCut' }
  } }
  if (Choice $c.metatrader_choice 'mt4') { Report-App 'MetaTrader 4 (Exness)' { Mt mt4 } }
  if (Choice $c.metatrader_choice 'mt5') { Report-App 'MetaTrader 5' { Mt mt5 } }
  if ($c.install_artcraft) { Report-App 'ArtCraft Launcher' { ArtCraft } }
}
if ($Group -in 'cli','all') {
  if (Choice $c.router_choice '9router') { Report-App '9Router' { NpmApp '9router' '9router' } }
  if (Choice $c.router_choice 'omniroute') { Report-App 'OmniRoute' { NpmApp 'omniroute' 'omniroute' 360 } }
  if (Choice $c.coding_agent_choice 'codex') { Report-App 'Codex CLI' { NpmApp '@openai/codex' 'codex' } }
  if (Choice $c.coding_agent_choice 'claude') { Report-App 'Claude Code' { VendorNative 'Claude Code' } }
  if (Choice $c.ai_agent_choice 'hermes') { Report-App 'Hermes Agent' { VendorNative 'Hermes Agent' } }
  if (Choice $c.ai_agent_choice 'openclaw') { Report-App 'OpenClaw' { VendorNative 'OpenClaw' } }
  if ($c.ai_agent_choice -in @('opencode','all')) { Report-App 'OpenCode' { NpmApp 'opencode-ai' 'opencode' } }
}
$global:LASTEXITCODE = 0
