#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$PiAddress = "10.12.194.1",
    [ValidatePattern("^[a-z_][a-z0-9_-]{0,31}$")]
    [string]$PiUser = "kali",
    [string]$KeyPath = (Join-Path $HOME ".ssh\boxbrain_pi_ed25519"),
    [ValidateRange(1024, 65525)]
    [int]$PreferredLocalPort = 6081,
    [ValidateRange(1024, 65535)]
    [int]$RemoteWebSocketPort = 6081,
    [ValidatePattern("^10\.12\.194\.[0-9]{1,3}$")]
    [string]$TargetAddress = "10.12.194.4",
    [string]$CredentialPath = (
        Join-Path $env:LOCALAPPDATA "BoxBrain\credentials\morris-vnc.clixml"
    ),
    [switch]$NoOpen,
    [switch]$NoClipboard
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-PinnedSshCommand {
    param(
        [Parameter(Mandatory)][string]$SshPath,
        [Parameter(Mandatory)][string]$IdentityPath,
        [Parameter(Mandatory)][string]$Target,
        [Parameter(Mandatory)][string]$Command
    )

    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $SshPath
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $escapedIdentity = $IdentityPath.Replace('"', '\"')
    $escapedCommand = $Command.Replace('"', '\"')
    $startInfo.Arguments = (
        '-i "{0}" -o BatchMode=yes -o IdentitiesOnly=yes ' +
        '-o StrictHostKeyChecking=yes -o ConnectTimeout=8 {1} "{2}"'
    ) -f $escapedIdentity, $Target, $escapedCommand

    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    try {
        if (-not $process.Start()) {
            throw "ssh.exe did not start."
        }
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        return [pscustomobject]@{
            ExitCode = $process.ExitCode
            Output = (($stdout, $stderr) -join [Environment]::NewLine).Trim()
        }
    }
    finally {
        $process.Dispose()
    }
}

if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
    throw "The BoxBrain SSH key was not found at $KeyPath."
}
$ssh = Get-Command ssh.exe -ErrorAction Stop
$target = "$PiUser@$PiAddress"

# Ensure the existing noVNC viewer and both WebSocket proxies are running.
$piViewerUrl = & (Join-Path $PSScriptRoot "open-pi-console.ps1") `
    -PiAddress $PiAddress `
    -PiUser $PiUser `
    -KeyPath $KeyPath `
    -NoOpen
$viewerUri = [Uri]$piViewerUrl
$viewerLocalPort = $viewerUri.Port

$reachability = Invoke-PinnedSshCommand `
    -SshPath $ssh.Source `
    -IdentityPath $KeyPath `
    -Target $target `
    -Command "nc -zw2 $TargetAddress 5900"
if ($reachability.ExitCode -ne 0) {
    throw "Morris VNC is not reachable from the Pi on $TargetAddress`:5900."
}

$localPort = $null
$startTunnel = $false
foreach ($offset in 0..9) {
    $candidate = $PreferredLocalPort + $offset
    $listener = Get-NetTCPConnection -LocalAddress "127.0.0.1" `
        -LocalPort $candidate -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $listener) {
        $localPort = $candidate
        $startTunnel = $true
        break
    }
    $process = Get-CimInstance Win32_Process `
        -Filter "ProcessId = $($listener.OwningProcess)" `
        -ErrorAction SilentlyContinue
    $expected = "127.0.0.1:${candidate}:127.0.0.1:${RemoteWebSocketPort}"
    if (
        $null -ne $process -and
        $process.Name -eq "ssh.exe" -and
        $process.CommandLine -like "*$expected*" -and
        $process.CommandLine -like "*$target*"
    ) {
        $localPort = $candidate
        break
    }
}
if ($null -eq $localPort) {
    throw "No private local port is available for the Morris console tunnel."
}

if ($startTunnel) {
    $arguments = @(
        "-N",
        "-L", "127.0.0.1:${localPort}:127.0.0.1:${RemoteWebSocketPort}",
        "-i", $KeyPath,
        "-o", "BatchMode=yes",
        "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        $target
    )
    $tunnel = Start-Process -FilePath $ssh.Source -ArgumentList $arguments `
        -WindowStyle Hidden -PassThru
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 200
        if ($tunnel.HasExited) { break }
        $client = [Net.Sockets.TcpClient]::new()
        try {
            $ready = $client.ConnectAsync("127.0.0.1", $localPort).Wait(250)
        }
        catch { $ready = $false }
        finally { $client.Dispose() }
        if ($ready) { break }
    }
    if (-not $ready) {
        if (-not $tunnel.HasExited) { Stop-Process -Id $tunnel.Id }
        throw "The private Morris console SSH tunnel could not be opened."
    }
}

if (-not $NoClipboard -and (Test-Path -LiteralPath $CredentialPath)) {
    $credential = Import-Clixml -LiteralPath $CredentialPath
    $clipboardReady = $false
    foreach ($attempt in 1..5) {
        try {
            $credential.GetNetworkCredential().Password | Set-Clipboard
            $clipboardReady = $true
            break
        }
        catch [Runtime.InteropServices.ExternalException] {
            Start-Sleep -Milliseconds 250
        }
    }
    if (-not $clipboardReady) {
        Write-Warning (
            "The console tunnel is ready, but the VNC password could not " +
            "be copied because the clipboard is busy."
        )
    }
}

$url = (
    "http://127.0.0.1:${viewerLocalPort}/current/vnc.html" +
    "?host=127.0.0.1&port=${localPort}" +
    "&autoconnect=1&resize=scale&reconnect=1"
)
if (-not $NoOpen) { Start-Process $url }
Write-Output $url
