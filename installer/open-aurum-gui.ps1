#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$PiAddress = "10.12.194.1",
    [ValidatePattern("^[a-z_][a-z0-9_-]{0,31}$")]
    [string]$PiUser = "kali",
    [string]$KeyPath = (Join-Path $HOME ".ssh\boxbrain_pi_ed25519"),
    [ValidateRange(1024, 65525)]
    [int]$PreferredLocalPort = 8765,
    [switch]$NoOpen
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-LocalTcpPort {
    param([Parameter(Mandatory)][int]$Port)
    $client = [Net.Sockets.TcpClient]::new()
    try {
        return $client.ConnectAsync("127.0.0.1", $Port).Wait(250)
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

if ($PiAddress -ne "10.12.194.1") {
    throw "The first Aurum GUI launch is bound to the approved USB route 10.12.194.1."
}
if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
    throw "The dedicated BBPI4 SSH key was not found at $KeyPath."
}

$ssh = (Get-Command ssh.exe -CommandType Application -ErrorAction Stop).Source
$target = "$PiUser@$PiAddress"
$options = @(
    "-i", $KeyPath,
    "-o", "BatchMode=yes",
    "-o", "IdentitiesOnly=yes",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "ConnectTimeout=8"
)

$ready = (& $ssh @options $target "sudo -n /usr/local/bin/aurum-gui-start").Trim()
if ($LASTEXITCODE -ne 0 -or $ready -notmatch "(?m)^AURUM_GUI_READY address=127\.0\.0\.1 port=8765 transient=true$") {
    throw "The Pi-local Aurum GUI did not start with its expected safety boundary.`n$ready"
}

$localPort = $null
$startTunnel = $false
foreach ($offset in 0..9) {
    $candidate = $PreferredLocalPort + $offset
    $listener = Get-NetTCPConnection `
        -LocalAddress "127.0.0.1" `
        -LocalPort $candidate `
        -State Listen `
        -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $listener) {
        $localPort = $candidate
        $startTunnel = $true
        break
    }
    $process = Get-CimInstance Win32_Process `
        -Filter "ProcessId = $($listener.OwningProcess)" `
        -ErrorAction SilentlyContinue
    $expectedForward = "127.0.0.1:${candidate}:127.0.0.1:8765"
    if (
        $null -ne $process -and
        $process.Name -eq "ssh.exe" -and
        $process.CommandLine -like "*$expectedForward*" -and
        $process.CommandLine -like "*$target*"
    ) {
        $localPort = $candidate
        break
    }
}
if ($null -eq $localPort) {
    throw "No private local port is available for the Aurum GUI tunnel."
}

if ($startTunnel) {
    $escapedKeyPath = $KeyPath.Replace('"', '\"')
    $arguments = (
        '-N -L 127.0.0.1:{0}:127.0.0.1:8765 ' +
        '-i "{1}" -o BatchMode=yes -o IdentitiesOnly=yes ' +
        '-o StrictHostKeyChecking=yes -o ExitOnForwardFailure=yes ' +
        '-o ServerAliveInterval=30 -o ServerAliveCountMax=3 {2}'
    ) -f $localPort, $escapedKeyPath, $target
    $tunnel = Start-Process `
        -FilePath $ssh `
        -ArgumentList $arguments `
        -WindowStyle Hidden `
        -PassThru

    $tunnelReady = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 200
        if ($tunnel.HasExited) {
            break
        }
        if (Test-LocalTcpPort -Port $localPort) {
            $tunnelReady = $true
            break
        }
    }
    if (-not $tunnelReady) {
        if (-not $tunnel.HasExited) {
            Stop-Process -Id $tunnel.Id
        }
        throw "The private Aurum GUI SSH tunnel could not be opened."
    }
}

$url = "http://127.0.0.1:$localPort/"
$status = Invoke-RestMethod -Uri "${url}api/status" -TimeoutSec 5
if (
    $status.schema -ne "aurum.gui.v1" -or
    $status.console.identity -ne "BBPI4/Aurum" -or
    $status.transport.loopback_only -ne $true -or
    $status.authority.host_actuation -ne $false
) {
    throw "The Aurum GUI status proof was not valid."
}

if (-not $NoOpen) {
    Start-Process $url
}
Write-Output "AURUM_GUI_OPEN_OK url=$url mind_version=$($status.console.mind_version) host_actuation=false"
