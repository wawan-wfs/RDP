# Read-only local Windows RDP status.
$ErrorActionPreference = 'Stop'
$base = 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server'
$rdp = Join-Path $base 'WinStations\RDP-Tcp'
try {
    $terminal = Get-ItemProperty -LiteralPath $base -Name 'fDenyTSConnections'
    $listener = Get-ItemProperty -LiteralPath $rdp -Name 'PortNumber','UserAuthentication'
    $termService = Get-Service -Name 'TermService'
    $tailscale = Get-Service -Name 'Tailscale' -ErrorAction SilentlyContinue
    $tcp = @(Get-NetTCPConnection -State Listen -LocalPort $listener.PortNumber -ErrorAction SilentlyContinue)
    [pscustomobject]@{
        RdpEnabled       = ($terminal.fDenyTSConnections -eq 0)
        NlaRequired      = ($listener.UserAuthentication -eq 1)
        Port             = $listener.PortNumber
        TermService      = $termService.Status
        LocalTcpListener = ($tcp.Count -gt 0)
        TailscaleService = if ($tailscale) { $tailscale.Status } else { 'Not found' }
    } | Format-List
    Write-Output 'Local status only. Network reachability and interactive login are not tested.'
} catch {
    Write-Error "Unable to inspect local Windows RDP settings: $_"
    exit 1
}
