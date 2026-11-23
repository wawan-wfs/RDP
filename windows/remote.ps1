param([Parameter(Mandatory)][ValidateSet('start','browser','cleanup')][string] $Phase)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
Set-Location (Split-Path $PSScriptRoot -Parent)
. "$PSScriptRoot/Workspace-InstallStatus.ps1"
. "$PSScriptRoot/Workspace-Privileges.ps1"
if (-not $env:WFS_STATE -or -not (Test-Path -LiteralPath $env:WFS_STATE)) { if ($Phase -eq 'cleanup') { return } else { throw 'Missing preflight state' } }
$state = $env:WFS_STATE
$c = Get-Content "$state/config.json" -Raw | ConvertFrom-Json
function Status($name,$value,$detail) { & python shared/workspace.py status $name $value $detail }
function Secret($role) {
  $value = & python shared/workspace.py password $role
  if ($LASTEXITCODE -ne 0 -or -not $value) { throw "Missing or invalid password for $role" }
  Write-Host "::add-mask::$value"
  return $value
}
function Tcp($target,$p) {
  & python shared/workspace.py tcp $target $p *> $null
  return $LASTEXITCODE -eq 0
}
function Wait-ServicePort($target,$p) {
  for ($i=0; $i -lt 30; $i++) { if (Tcp $target $p) { return }; Start-Sleep 2 }
  throw "Port $p not reachable on configured listener"
}
function Ts-Serve($kind,$port,$target) {
  $json = & tailscale serve status --json
  if ($LASTEXITCODE -ne 0) { throw 'Could not inspect existing Tailscale Serve' }
  $s = $json | ConvertFrom-Json -AsHashtable
  if ($s -and (($s.TCP -and $s.TCP.Contains([string]$port)) -or ($s.Web -and @($s.Web.Keys | Where-Object { $_ -like "*:$port" }).Count) -or ($s.AllowFunnel -and $true -in $s.AllowFunnel.Values))) {
    throw 'Refusing to overwrite existing Serve or use a public node'
  }
  & tailscale serve --bg "--${kind}=$port" $target | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Tailscale Serve $kind $port failed" }
  Add-Content "$state/serve.txt" "$kind $port"
}
$terminal = 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server'
$listener = "$terminal\WinStations\RDP-Tcp"
$user = $c.rdp_username
$rule = "WFS-RDP-$env:GITHUB_RUN_ID-$env:GITHUB_RUN_ATTEMPT"
$task = "WFS-noVNC-$env:GITHUB_RUN_ID-$env:GITHUB_RUN_ATTEMPT"

if ($Phase -eq 'cleanup') {
  $ErrorActionPreference = 'Continue'
  if (Test-Path "$state/serve.txt") {
    Get-Content "$state/serve.txt" | ForEach-Object {
      if ($_ -match '^(tcp|https) ([0-9]+)$') { & tailscale serve "--$($Matches[1])=$($Matches[2])" off | Out-Null }
    }
    Remove-Item "$state/serve.txt" -Force
  }
  if (Test-Path "$state/vnc-owned") {
    Stop-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue
    Stop-Service tvnserver -ErrorAction SilentlyContinue
    if (Get-Service tvnserver -ErrorAction SilentlyContinue) {
      Set-Service tvnserver -StartupType Disabled -ErrorAction SilentlyContinue
      if (Test-Path "$state/tightvnc.msi") {
        try { $null = Invoke-BoundedInstaller msiexec.exe @('/x',('"{0}"' -f "$state/tightvnc.msi"),'/quiet','/norestart') 45 } catch { Write-Warning 'The stopped, loopback-only TightVNC service could not be removed' }
      }
    }
    if (-not (Get-Service tvnserver -ErrorAction SilentlyContinue)) {
      Remove-NetFirewallRule -Name "$rule-VNC-Block" -ErrorAction SilentlyContinue
      Remove-Item "$state/vnc-owned" -Force
    } else {
      Write-Warning 'TightVNC service remains installed; direct VNC firewall deny rule retained for safety.'
    }
  }
  if (Test-Path "$state/rdp-backup.json") {
    $previous = Get-Content "$state/rdp-backup.json" -Raw | ConvertFrom-Json
    Set-ItemProperty $terminal fDenyTSConnections $previous.deny
    Set-ItemProperty $listener UserAuthentication $previous.nla
    if ($null -ne $previous.security_layer) { Set-ItemProperty $listener SecurityLayer $previous.security_layer }
    Remove-NetFirewallRule -Name "$rule-allow" -ErrorAction SilentlyContinue
    foreach ($old in $previous.enabled) { Enable-NetFirewallRule -Name $old -ErrorAction SilentlyContinue }
    if (-not $previous.service -and (Get-Service TermService).Status -eq 'Running') { Stop-Service TermService -Force -ErrorAction SilentlyContinue }
    # Restore modified firewall profiles only on the same disposable GitHub-hosted runner.
    if (Test-Path "$state/firewall-before.json") {
      try {
        $savedProfiles = @(Get-Content "$state/firewall-before.json" -Raw | ConvertFrom-Json)
        foreach ($saved in $savedProfiles) {
          $enabledFlag = if ($saved.enabled) { 'True' } else { 'False' }
          if ($saved.default_inbound -in @('Allow', 'Block')) {
            Set-NetFirewallProfile -Profile $saved.name -Enabled $enabledFlag -DefaultInboundAction $saved.default_inbound -ErrorAction Stop
          } else {
            # NotConfigured is only legal for GPO settings; never write it to a local store.
            Set-NetFirewallProfile -Profile $saved.name -Enabled $enabledFlag -ErrorAction Stop
            Write-Warning "Original default inbound for $($saved.name) was not a restorable local value; retaining Block on disposable runner."
          }
        }
        Remove-Item "$state/firewall-before.json" -Force
      } catch { Write-Warning ("Windows Firewall profile restore: " + $_.Exception.Message) }
    }
    Remove-Item "$state/rdp-backup.json" -Force
  }
  Get-ScheduledTask -TaskName "WFS-UserApps-$env:GITHUB_RUN_ID-$env:GITHUB_RUN_ATTEMPT-*" -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-ScheduledTask -InputObject $_ -ErrorAction SilentlyContinue; Unregister-ScheduledTask -InputObject $_ -Confirm:$false -ErrorAction SilentlyContinue }
  # The CapCut logon fallback must not persist on a reused/self-hosted runner
  # after the temporary RDP session has ended.
  if ($c.editor_choice -in @('capcut','both')) {
    $capcutStartup = Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\Startup\WFS CapCut RDP Setup.lnk'
    $capcutRepair = Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\Install or Repair CapCut for RDP.lnk'
    foreach ($path in @($capcutStartup,$capcutRepair)) {
      Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath (Join-Path $env:ProgramData 'WFS-Apps\capcut-pending.txt') -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $env:ProgramData 'WFS-Apps\CapCut') -Recurse -Force -ErrorAction SilentlyContinue
  }
  if (Test-Path "$state/user-owned") { Remove-LocalUser -Name $user -ErrorAction SilentlyContinue; Remove-Item "$state/user-owned" -Force }
  return
}

if (-not (Test-WorkspaceAdministrator)) {
  throw 'Windows RDP/noVNC requires an elevated Administrator token (SID S-1-5-32-544); choose an elevated dedicated Windows runner'
}
# Avoid race between action backend Ready and Tailscale CLI IPv4 assignment.
$rawIp = & python -m windows.tailnet_ip
if ($LASTEXITCODE -ne 0 -or -not $rawIp) { throw 'Tailscale node has no verified private IPv4 after bounded retries' }
$ip = & python shared/workspace.py ip $rawIp
if ($LASTEXITCODE -ne 0 -or -not $ip) { throw 'No valid tailnet IPv4' }
Status 'Tailnet' 'ready' "IPv4 $ip"
if ($Phase -eq 'start' -and $c.remote_access -in @('rdp','both')) {
  Write-Host '::group::🛡️ WFS / RDP · secure private listener + NLA'
  try {
    if ((Get-NetFirewallProfile | Where-Object { -not $_.Enabled }).Count) { throw 'Windows Firewall must be enabled for each profile' }
    if ((Get-ItemProperty $listener).PortNumber -ne 3389) { throw 'Expected native RDP listener at 3389' }
    if (Get-LocalUser -Name $user -ErrorAction SilentlyContinue) { throw 'Remote username already exists; choose a different dedicated account' }
    $remoteGroup = Get-LocalGroup -SID 'S-1-5-32-555'
    $pwd = Secret rdp
    New-LocalUser -Name $user -Password (ConvertTo-SecureString $pwd -AsPlainText -Force) -Description 'WFS temporary workspace' | Out-Null
    New-Item "$state/user-owned" -ItemType File -Force | Out-Null
    Remove-Variable pwd
    Add-LocalGroupMember -Group $remoteGroup.Name -Member $user
    if ($c.rdp_user_role -eq 'administrator') {
      # Legacy Windows workflow used the administrators group. This is opt-in now,
      # resolved by SID for localized Windows images and checked after assignment.
      $adminGroup = Get-LocalGroup -SID 'S-1-5-32-544' -ErrorAction Stop
      Add-LocalGroupMember -Group $adminGroup.Name -Member $user -ErrorAction Stop
      $createdSid = (Get-LocalUser -Name $user -ErrorAction Stop).SID.Value
      if (@(Get-LocalGroupMember -Group $adminGroup.Name -ErrorAction Stop | Where-Object { $_.SID.Value -eq $createdSid }).Count -lt 1) {
        throw 'RDP user Administrator membership could not be verified'
      }
      Status 'RDP account role' 'configured' 'Administrator (opt-in); UAC remains enabled'
    } else {
      Status 'RDP account role' 'configured' 'Standard user (recommended)'
    }
    $tsIf = Get-NetIPAddress -IPAddress $ip -AddressFamily IPv4 -ErrorAction Stop | Select-Object -First 1
    $rdpRules = @(Get-NetFirewallRule -Name 'RemoteDesktop*' -ErrorAction SilentlyContinue | Where-Object Enabled -eq 'True')
    @{
      deny = (Get-ItemProperty $terminal).fDenyTSConnections
      nla = (Get-ItemProperty $listener).UserAuthentication
      security_layer = (Get-ItemProperty $listener).SecurityLayer
      enabled = @($rdpRules | ForEach-Object Name)
      service = ((Get-Service TermService).Status -eq 'Running')
    } | ConvertTo-Json | Set-Content "$state/rdp-backup.json"
    $rdpRules | Disable-NetFirewallRule
    # Fail closed: prevent default-allow profiles from exposing port 3389.
    # GitHub ARM64 images can have non-Block profile defaults. For disposable hosted
    # runners only, save those defaults and temporarily enforce inbound Block.
    # Self-hosted runners are never modified automatically for this requirement.
    $profiles = @(Get-NetFirewallProfile -ErrorAction Stop)
    if ($profiles.Count -lt 1) { throw 'No Windows Firewall profiles were found' }
    $unprotected = @($profiles | Where-Object { -not $_.Enabled -or [string]$_.DefaultInboundAction -ne 'Block' })
    if ($unprotected.Count -gt 0) {
      $details = ($unprotected | ForEach-Object { "{0}: enabled={1}, inbound={2}" -f $_.Name,$_.Enabled,$_.DefaultInboundAction }) -join '; '
      Write-Warning "WFS/RDP: Firewall profiles require temporary hardening: $details"
      if ($env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or $c.runner_type -ne 'github') {
        throw 'Self-hosted firewall settings are not modified automatically. Enable all profiles with DefaultInboundAction Block before RDP.'
      }
      $snapshot = @($profiles | ForEach-Object {
        [pscustomobject]@{ name = [string]$_.Name; enabled = [bool]$_.Enabled; default_inbound = [string]$_.DefaultInboundAction }
      })
      ConvertTo-Json -InputObject $snapshot -Depth 5 | Set-Content "$state/firewall-before.json" -Encoding utf8
      foreach ($profile in $unprotected) {
        Set-NetFirewallProfile -Profile $profile.Name -Enabled True -DefaultInboundAction Block -ErrorAction Stop
      }
    }
    # Verify *effective* policy after applying temporary hardening.
    $effectiveProfiles = @(Get-NetFirewallProfile -PolicyStore ActiveStore -ErrorAction Stop)
    if ($effectiveProfiles.Count -lt 1 -or @($effectiveProfiles | Where-Object { -not $_.Enabled -or [string]$_.DefaultInboundAction -ne 'Block' }).Count -gt 0) {
      throw 'Firewall policy still permits unsolicited inbound traffic. Refusing to expose RDP.'
    }
    Write-Host '::notice title=WFS RDP firewall::Effective inbound Block verified on all Windows Firewall profiles'
    Write-Host '::notice title=WFS RDP firewall::Using single scoped allow rule, inbound-default-deny; no invalid address ranges or interface aliases'
    New-NetFirewallRule -Name "$rule-allow" -DisplayName 'WFS scoped RDP over Tailscale' -Direction Inbound -Action Allow -LocalAddress $ip -RemoteAddress '100.64.0.0/10' -Protocol TCP -LocalPort 3389 -ErrorAction Stop | Out-Null
    Set-ItemProperty $listener UserAuthentication 1
    Set-ItemProperty $listener SecurityLayer 2
    Set-ItemProperty $terminal fDenyTSConnections 0
    Start-Service TermService
    Wait-ServicePort $ip 3389
    & python shared/rdp_probe.py $ip 3389 --nla
    if ($LASTEXITCODE -ne 0) { throw 'RDP NLA protocol probe failed' }
    Status 'Windows RDP' 'ready' "mstsc /v:${ip}:3389; user $user; NLA enabled"
    Set-Content "$state/rdp-ready" 'yes'
  } catch {
    Status 'Windows RDP' 'failed' 'See the remote setup step'
    Write-Warning ("RDP setup: " + $_.Exception.Message)
  } finally { Write-Host '::endgroup::' }
}
if (($Phase -eq 'start' -and $c.remote_access -eq 'novnc') -or ($Phase -eq 'browser' -and $c.remote_access -eq 'both')) {
  Write-Host '::group::🖥️ WFS / noVNC · loopback and tailnet bridge'
  $novncStage = 'preflight'
  try {
    if ($env:RUNNER_ARCH -eq 'ARM64') { throw 'TightVNC browser mode is x64 only' }
    if (Get-Service tvnserver -ErrorAction SilentlyContinue) { throw 'Existing TightVNC service will not be modified' }
    $pwd = Secret web
    $novncStage = 'download / signature verification'
    $msi = "$state/tightvnc.msi"
    $msiUrl = 'https://www.tightvnc.com/download/2.8.90/tightvnc-2.8.90-gpl-setup-64bit.msi'
    $msiProperties = @('ADDLOCAL=Server', 'SERVER_REGISTER_AS_SERVICE=1',
      'SERVER_ADD_FIREWALL_EXCEPTION=0', 'SET_USEVNCAUTHENTICATION=1','VALUE_OF_USEVNCAUTHENTICATION=1',
      'SET_ALLOWLOOPBACK=1','VALUE_OF_ALLOWLOOPBACK=1','SET_LOOPBACKONLY=1','VALUE_OF_LOOPBACKONLY=1',
      'SET_REMOVEWALLPAPER=1','VALUE_OF_REMOVEWALLPAPER=0',
      'MsiHiddenProperties=VALUE_OF_PASSWORD','SET_PASSWORD=1',"VALUE_OF_PASSWORD=$pwd")
    # Reject HTML/corrupted downloads before invoking msiexec (avoids opaque MSI 1619).
    $validMsi = $false
    try {
      Invoke-WebRequest $msiUrl -OutFile $msi -TimeoutSec 75 -ErrorAction Stop
      $f = [IO.File]::OpenRead($msi)
      try {
        $signatureBytes = [byte[]]::new(8)
        [void]$f.Read($signatureBytes, 0, 8)
        $validMsi = ($f.Length -ge 1000000 -and [Convert]::ToHexString($signatureBytes) -eq 'D0CF11E0A1B11AE1')
      } finally { $f.Dispose() }
      if (-not $validMsi) { Write-Warning 'TightVNC URL did not return a valid MSI binary. Trying the signed winget package instead.' }
    } catch { Write-Warning 'TightVNC direct download unavailable; trying the winget package.' }
    if ($validMsi) {
      Write-Host '[WFS/noVNC] Verifying TightVNC installer signature'
      $signature = Get-AuthenticodeSignature -FilePath $msi
      if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'GlavSoft|TightVNC') { throw 'TightVNC MSI Authenticode signature or publisher verification failed' }
    }
    $novncStage = 'TightVNC installation'
    # The VNC listener MUST remain local-only. Block direct remote 5900 before install.
    New-NetFirewallRule -Name "$rule-VNC-Block" -DisplayName 'WFS deny direct VNC (use Tailscale bridge)' -Protocol TCP -LocalPort 5900 -Direction Inbound -Action Block -ErrorAction Stop | Out-Null
    New-Item "$state/vnc-owned" -ItemType File -Force | Out-Null
    try {
      $installed = $false
      if ($validMsi) {
        $arguments = @('/i', ('"{0}"' -f $msi), '/quiet', '/norestart') + $msiProperties
        $code = Invoke-BoundedInstaller msiexec.exe $arguments 120
        if ($code -in 0,3010) { $installed = $true }
        else { Write-Warning "TightVNC MSI returned $code; attempting winget signed fallback" }
      }
      if (-not $installed) {
        $winget = (Get-Command winget.exe -ErrorAction SilentlyContinue).Source
        if (-not $winget) { throw 'TightVNC MSI unavailable or invalid and winget.exe is missing' }
        $override = $msiProperties -join ' '
        $code = Invoke-BoundedInstaller $winget @('install','--id','GlavSoft.TightVNC','--exact','--source','winget',
          '--silent','--accept-source-agreements','--accept-package-agreements','--disable-interactivity',
          '--override',('"{0}"' -f $override)) 240
        if ($code -notin 0,3010) { throw "TightVNC winget fallback returned $code" }
      }
    } finally { Remove-Variable pwd,msiProperties,arguments -ErrorAction SilentlyContinue }
    $novncStage = 'TightVNC service and loopback listener'
    Write-Host '[WFS/noVNC] Installer finished; checking local VNC service'
    if (-not (Get-Service tvnserver -ErrorAction SilentlyContinue)) { throw 'TightVNC installation did not create the server service' }
    Write-Host '[WFS/noVNC] Starting VNC service and checking loopback port 5900'
    Start-Service tvnserver -ErrorAction Stop
    Wait-ServicePort '127.0.0.1' 5900
    & python shared/rfb_probe.py 127.0.0.1 5900 | Out-Null
    if ($LASTEXITCODE -ne 0 -or (Get-NetTCPConnection -State Listen -LocalPort 5900 | Where-Object LocalAddress -notin @('127.0.0.1','::1'))) { throw 'VNC loopback/auth gate failed' }
    $novncStage = 'download noVNC frontend'
    Write-Host '[WFS/noVNC] VNC loopback verified; downloading noVNC frontend'
    $bundle = "$state/novnc.zip"
    Invoke-WebRequest 'https://codeload.github.com/novnc/noVNC/zip/refs/tags/v1.7.0' -OutFile $bundle -TimeoutSec 60
    Expand-Archive -LiteralPath $bundle -DestinationPath "$state/web"
    $web = "$state/web/noVNC-1.7.0"
    if (-not (Test-Path "$web/vnc.html")) { throw 'noVNC distribution missing' }
    # The setup-python Python runtime is already isolated per hosted runner.
    # Do not waste minutes on a second venv and duplicate pip installation.
    $novncStage = 'aiohttp dependency'
    $exe = (Get-Command python -ErrorAction Stop).Source
    & $exe -c 'import aiohttp; print(aiohttp.__version__)' 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
      Write-Host '[WFS/noVNC] Installing only missing aiohttp dependency into setup-python runtime'
      $g = Invoke-BoundedInstaller $exe @('-m','pip','install','--disable-pip-version-check','--retries','1','--timeout','20','aiohttp>=3.13.3,<4') 110
      if ($g -ne 0) { throw 'noVNC aiohttp dependency install failed' }
    } else {
      Write-Host '[WFS/noVNC] aiohttp already available; skipping duplicate install'
    }
    $novncStage = 'background bridge task'
    Write-Host '[WFS/noVNC] Python bridge ready; registering background scheduled task'
    $action = New-ScheduledTaskAction -Execute $exe -Argument ('"{0}" "{1}"' -f "$PSScriptRoot/novnc_bridge.py",$web)
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([timespan]::FromHours(6)) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $task -Action $action -Settings $settings -User SYSTEM -RunLevel Highest -Force | Out-Null
    Write-Host '[WFS/noVNC] Starting background bridge task'
    Start-ScheduledTask -TaskName $task
    Write-Host '[WFS/noVNC] Waiting for loopback HTTP/WebSocket port 6081'
    Wait-ServicePort '127.0.0.1' 6081
    $novncStage = 'HTTP/WebSocket handshake'
    Write-Host '[WFS/noVNC] Running live HTTP/WebSocket handshake probe'
    & $exe "$PSScriptRoot/test_novnc.py" --live
    if ($LASTEXITCODE -ne 0) { throw 'HTTP/WebSocket RFB smoke failed' }
    $novncStage = 'Tailscale Serve mapping'
    $fragment = '#resize=scale&autoconnect=1&path=websockify'
    $url = $null
    if ($c.novnc_transport -eq 'tailscale_https') {
      try {
        $dns = ((& tailscale status --json | ConvertFrom-Json).Self.DNSName).TrimEnd('.')
        if ($dns -notmatch '^[a-z0-9.-]+\.ts\.net$') { throw 'MagicDNS is unavailable' }
        Ts-Serve https 443 'http://127.0.0.1:6081'
        $url = "https://$dns/vnc.html$fragment"
      } catch { Status 'Windows HTTPS' 'warning' 'HTTPS is unavailable; trying private TCP 6082' }
    }
    if (-not $url) {
      Write-Host '[WFS/noVNC] Configuring private Tailscale TCP relay 6082'
      Ts-Serve tcp 6082 'tcp://127.0.0.1:6081'
      $url = "http://${ip}:6082/vnc.html$fragment"
    }
    Status 'Windows noVNC' 'ready' "$url; console session; VNC password required"
    Set-Content "$state/novnc-ready" 'yes'
  } catch {
    Status 'Windows noVNC' 'failed' "Failed at $novncStage; see noVNC step logs"
    Write-Warning ("[WFS/noVNC] FAILED stage=" + $novncStage + "; reason=" + $_.Exception.Message)
    Write-Host "::warning title=WFS noVNC setup::Failure during $novncStage; RDP may still be available."
  }
  finally { Write-Host '::endgroup::' }
}
if ($Phase -eq 'start' -and -not ((Test-Path "$state/rdp-ready") -or (Test-Path "$state/novnc-ready"))) { throw 'No requested remote endpoint passed its readiness checks' }
if ($Phase -eq 'browser' -and -not (Test-Path "$state/novnc-ready")) { throw 'Optional browser endpoint did not pass readiness checks; native RDP may remain available' }
$global:LASTEXITCODE = 0