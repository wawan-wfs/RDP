param([Parameter(Mandatory)][ValidateSet('start','cleanup')][string] $Phase)
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
    }
  }
  if (Test-Path "$state/rdp-backup.json") {
    $previous = Get-Content "$state/rdp-backup.json" -Raw | ConvertFrom-Json
    Set-ItemProperty $terminal fDenyTSConnections $previous.deny
    Set-ItemProperty $listener UserAuthentication $previous.nla
    if ($null -ne $previous.security_layer) { Set-ItemProperty $listener SecurityLayer $previous.security_layer }
    Remove-NetFirewallRule -Name "$rule-*" -ErrorAction SilentlyContinue
    foreach ($old in $previous.enabled) { Enable-NetFirewallRule -Name $old -ErrorAction SilentlyContinue }
    if (-not $previous.service -and (Get-Service TermService).Status -eq 'Running') { Stop-Service TermService -Force -ErrorAction SilentlyContinue }
    Remove-Item "$state/rdp-backup.json" -Force
  }
  Get-ScheduledTask -TaskName "WFS-UserApps-$env:GITHUB_RUN_ID-$env:GITHUB_RUN_ATTEMPT-*" -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-ScheduledTask -InputObject $_ -ErrorAction SilentlyContinue; Unregister-ScheduledTask -InputObject $_ -Confirm:$false -ErrorAction SilentlyContinue }
  if (Test-Path "$state/user-owned") { Remove-LocalUser -Name $user -ErrorAction SilentlyContinue; Remove-Item "$state/user-owned" -Force }
  return
}

if (-not (Test-WorkspaceAdministrator)) {
  throw 'Windows RDP/noVNC requires an elevated Administrator token (SID S-1-5-32-544); choose an elevated dedicated Windows runner'
}
# The action can report a connected backend before the CLI serves the node IP.
# Resolve a verified 100.64.0.0/10 address, with bounded retries and a JSON fallback.
$rawIp = & python -m windows.tailnet_ip
if ($LASTEXITCODE -ne 0 -or -not $rawIp) { throw 'Tailscale IPv4 readiness check failed; review WFS/TAILNET diagnostics above' }
$ip = & python shared/workspace.py ip $rawIp
if ($LASTEXITCODE -ne 0 -or -not $ip) { throw 'No valid tailnet IPv4' }
Status 'Tailnet' 'ready' "IPv4 $ip"
if ($c.remote_access -in @('rdp','both')) {
  Write-Host '::group::WFS / Native RDP - NLA and private listener'
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
      # Legacy workflow offered RDP Administrator access. Keep UAC enabled.
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
    # Block explicitly on other connected interfaces, including cases with pre-existing broad allow rules.
    foreach ($alias in @(Get-NetAdapter | Where-Object Name -ne $tsIf.InterfaceAlias | ForEach-Object Name)) {
      foreach ($proto in @('TCP','UDP')) {
        New-NetFirewallRule -Name "$rule-block-$proto-$([guid]::NewGuid().ToString('N'))" -DisplayName 'WFS private RDP block' -Direction Inbound -Action Block -InterfaceAlias $alias -Protocol $proto -LocalPort 3389 | Out-Null
      }
    }
    # Deny addresses outside Tailscale's IPv4 range on the tailnet adapter as well.
    New-NetFirewallRule -Name "$rule-block-outside" -DisplayName 'WFS block non-tailnet RDP' -Direction Inbound -Action Block -RemoteAddress @('0.0.0.0-100.63.255.255','100.128.0.0-255.255.255.255','::/0') -Protocol TCP -LocalPort 3389 | Out-Null
    New-NetFirewallRule -Name "$rule-allow" -DisplayName 'WFS tailnet-only RDP' -Direction Inbound -Action Allow -InterfaceAlias $tsIf.InterfaceAlias -LocalAddress $ip -RemoteAddress '100.64.0.0/10' -Protocol TCP -LocalPort 3389 | Out-Null
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
  } finally {
    Write-Host '::endgroup::'
  }
}
if ($c.remote_access -in @('novnc','both')) {
  Write-Host '::group::WFS / Browser desktop - TightVNC, WebSocket and tailnet'
  try {
    if ($env:RUNNER_ARCH -and $env:RUNNER_ARCH -ne 'X64') { throw 'TightVNC browser mode is x64 only' }
    if (Get-Service tvnserver -ErrorAction SilentlyContinue) { throw 'Existing TightVNC service will not be modified' }
    $pwd = Secret web
    $msi = "$state/tightvnc.msi"
    $msiUrl = 'https://www.tightvnc.com/download/2.8.90/tightvnc-2.8.90-gpl-setup-64bit.msi'
    Invoke-WebRequest $msiUrl -OutFile $msi -TimeoutSec 60
    $signature = Get-AuthenticodeSignature -FilePath $msi
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'GlavSoft|TightVNC') { throw 'TightVNC signature/publisher verification failed' }
    New-NetFirewallRule -Name "$rule-VNC-Block" -DisplayName 'WFS block direct VNC' -Protocol TCP -LocalPort 5900 -Direction Inbound -Action Block | Out-Null
    New-Item "$state/vnc-owned" -ItemType File -Force | Out-Null
    $arguments = @('/i', ('"{0}"' -f $msi), '/quiet', '/norestart', 'ADDLOCAL=Server', 'SERVER_REGISTER_AS_SERVICE=1',
      'SERVER_ADD_FIREWALL_EXCEPTION=0', 'SET_USEVNCAUTHENTICATION=1','VALUE_OF_USEVNCAUTHENTICATION=1',
      'SET_ALLOWLOOPBACK=1','VALUE_OF_ALLOWLOOPBACK=1','SET_LOOPBACKONLY=1','VALUE_OF_LOOPBACKONLY=1',
      'SET_REMOVEWALLPAPER=1','VALUE_OF_REMOVEWALLPAPER=0',
      'MsiHiddenProperties=VALUE_OF_PASSWORD','SET_PASSWORD=1',"VALUE_OF_PASSWORD=$pwd")
    try {
      $code = Invoke-BoundedInstaller msiexec.exe $arguments 120
      if ($code -notin 0,3010) { throw "TightVNC MSI returned $code" }
    } finally { Remove-Variable pwd,arguments -ErrorAction SilentlyContinue }
    Start-Service tvnserver
    Wait-ServicePort '127.0.0.1' 5900
    & python shared/rfb_probe.py 127.0.0.1 5900 | Out-Null
    if ($LASTEXITCODE -ne 0 -or (Get-NetTCPConnection -State Listen -LocalPort 5900 | Where-Object LocalAddress -notin @('127.0.0.1','::1'))) { throw 'VNC loopback/auth gate failed' }
    $bundle = "$state/novnc.zip"
    Invoke-WebRequest 'https://codeload.github.com/novnc/noVNC/zip/refs/tags/v1.7.0' -OutFile $bundle -TimeoutSec 60
    Expand-Archive -LiteralPath $bundle -DestinationPath "$state/web"
    $web = "$state/web/noVNC-1.7.0"
    if (-not (Test-Path "$web/vnc.html")) { throw 'noVNC distribution missing' }
    $g = Invoke-BoundedInstaller (Get-Command python).Source @('-m','venv',('"{0}"' -f "$state/venv")) 90
    if ($g -ne 0) { throw 'noVNC bridge venv failed' }
    $exe = "$state/venv/Scripts/python.exe"
    $g = Invoke-BoundedInstaller $exe @('-m','pip','install','--disable-pip-version-check','--retries','1','--timeout','20','aiohttp>=3.13.3,<4') 120
    if ($g -ne 0) { throw 'noVNC bridge dependency install failed' }
    $action = New-ScheduledTaskAction -Execute $exe -Argument ('"{0}" "{1}"' -f "$PSScriptRoot/novnc_bridge.py",$web)
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([timespan]::FromHours(6)) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $task -Action $action -Settings $settings -User SYSTEM -RunLevel Highest -Force | Out-Null
    Start-ScheduledTask -TaskName $task
    Wait-ServicePort '127.0.0.1' 6081
    & $exe "$PSScriptRoot/test_novnc.py" --live
    if ($LASTEXITCODE -ne 0) { throw 'HTTP/WebSocket RFB smoke failed' }
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
      Ts-Serve tcp 6082 'tcp://127.0.0.1:6081'
      $url = "http://${ip}:6082/vnc.html$fragment"
    }
    Status 'Windows noVNC' 'ready' "$url; console session; VNC password required"
    Set-Content "$state/novnc-ready" 'yes'
  } catch { Status 'Windows noVNC' 'failed' 'See the remote setup step'; Write-Warning ("noVNC setup: " + $_.Exception.Message) }
  finally { Write-Host '::endgroup::' }
}
if (-not ((Test-Path "$state/rdp-ready") -or (Test-Path "$state/novnc-ready"))) { throw 'No requested remote endpoint passed its readiness checks' }
$global:LASTEXITCODE = 0
