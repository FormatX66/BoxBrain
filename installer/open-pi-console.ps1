#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$PiAddress = "10.12.194.1",
    [ValidatePattern("^[a-z_][a-z0-9_-]{0,31}$")]
    [string]$PiUser = "kali",
    [string]$KeyPath = (Join-Path $HOME ".ssh\boxbrain_pi_ed25519"),
    [ValidateRange(1024, 65525)]
    [int]$PreferredLocalPort = 6080,
    [ValidateRange(1024, 65535)]
    [int]$ViewerPort = 8790,
    [switch]$NoOpen
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-PrivateOrLinkLocalAddress {
    param([Parameter(Mandatory)][string]$Address)

    $parsed = $null
    if (-not [Net.IPAddress]::TryParse($Address, [ref]$parsed)) {
        return $false
    }
    $bytes = $parsed.GetAddressBytes()
    if ($bytes.Length -ne 4) {
        return $false
    }
    return (
        $bytes[0] -eq 10 -or
        ($bytes[0] -eq 172 -and $bytes[1] -ge 16 -and $bytes[1] -le 31) -or
        ($bytes[0] -eq 192 -and $bytes[1] -eq 168) -or
        ($bytes[0] -eq 169 -and $bytes[1] -eq 254)
    )
}

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

if (-not (Test-PrivateOrLinkLocalAddress -Address $PiAddress)) {
    throw "PiAddress must be a private or link-local IPv4 address."
}
if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
    throw "The BoxBrain SSH key was not found at $KeyPath."
}
$ssh = Get-Command ssh.exe -ErrorAction Stop

$sshOptions = @(
    "-i", $KeyPath,
    "-o", "BatchMode=yes",
    "-o", "IdentitiesOnly=yes",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "ConnectTimeout=8"
)
$target = "$PiUser@$PiAddress"
$remoteOutput = & $ssh.Source @sshOptions $target `
    "sudo -n /usr/local/bin/boxbrain-console-start" 2>&1
if (
    $LASTEXITCODE -ne 0 -or
    -not ($remoteOutput -match "^BOXBRAIN_CONSOLE_READY ")
) {
    $detail = ($remoteOutput | ForEach-Object { "$_" }) -join [Environment]::NewLine
    throw "The Pi console could not be started.$([Environment]::NewLine)$detail"
}

$localPort = $null
$startTunnel = $false
foreach ($candidate in $PreferredLocalPort..($PreferredLocalPort + 9)) {
    $listener = Get-NetTCPConnection `
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
    $expectedForward = "127.0.0.1:${candidate}:127.0.0.1:6080"
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
    throw "No private local port is available for the Pi console tunnel."
}

if ($startTunnel) {
    $escapedKeyPath = $KeyPath.Replace('"', '\"')
    $tunnelArguments = (
        '-N -L 127.0.0.1:{0}:127.0.0.1:6080 ' +
        '-i "{1}" -o BatchMode=yes -o IdentitiesOnly=yes ' +
        '-o StrictHostKeyChecking=yes -o ExitOnForwardFailure=yes ' +
        '-o ServerAliveInterval=30 -o ServerAliveCountMax=3 {2}'
    ) -f $localPort, $escapedKeyPath, $target
    $tunnel = Start-Process `
        -FilePath $ssh.Source `
        -ArgumentList $tunnelArguments `
        -WindowStyle Hidden `
        -PassThru

    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 200
        if ($tunnel.HasExited) {
            break
        }
        if (Test-LocalTcpPort -Port $localPort) {
            $ready = $true
            break
        }
    }
    if (-not $ready) {
        if (-not $tunnel.HasExited) {
            Stop-Process -Id $tunnel.Id
        }
        throw "The private Pi console SSH tunnel could not be opened."
    }
}

$url = (
    "http://${PiAddress}:${ViewerPort}/current/vnc.html" +
    "?host=127.0.0.1&port=${localPort}" +
    "&autoconnect=1&resize=scale&reconnect=1"
)
if (-not $NoOpen) {
    Start-Process $url
}
Write-Output $url
