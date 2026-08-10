#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$PiAddress = "10.12.194.1",
    [ValidatePattern("^[a-z_][a-z0-9_-]{0,31}$")]
    [string]$PiUser = "kali",
    [string]$KeyPath = (Join-Path $HOME ".ssh\boxbrain_pi_ed25519"),
    [ValidateRange(1024, 65525)]
    [int]$PreferredLocalPort = 6080,
    [ValidateRange(1024, 65525)]
    [int]$PreferredViewerLocalPort = 8790,
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

if (-not (Test-PrivateOrLinkLocalAddress -Address $PiAddress)) {
    throw "PiAddress must be a private or link-local IPv4 address."
}
if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
    throw "The BoxBrain SSH key was not found at $KeyPath."
}
$ssh = Get-Command ssh.exe -ErrorAction Stop

$target = "$PiUser@$PiAddress"
$remoteResult = Invoke-PinnedSshCommand `
    -SshPath $ssh.Source `
    -IdentityPath $KeyPath `
    -Target $target `
    -Command "sudo -n /usr/local/bin/boxbrain-console-start"
if (
    $remoteResult.ExitCode -ne 0 -or
    $remoteResult.Output -notmatch (
        "(?m)^BOXBRAIN_CONSOLE_READY address=" +
        "(?<ViewerAddress>[0-9.]+) port=(?<ViewerPort>[0-9]+)\s*$"
    )
) {
    throw (
        "The Pi console could not be started." +
        [Environment]::NewLine + $remoteResult.Output
    )
}
$viewerAddress = $Matches["ViewerAddress"]
$viewerRemotePort = [int]$Matches["ViewerPort"]
if (-not (Test-PrivateOrLinkLocalAddress -Address $viewerAddress)) {
    throw "The Pi console reported a non-private viewer address."
}
if ($viewerRemotePort -ne $ViewerPort) {
    throw "The Pi console reported unexpected viewer port $viewerRemotePort."
}

$localPort = $null
$viewerLocalPort = $null
$startTunnel = $false
foreach ($offset in 0..9) {
    $candidate = $PreferredLocalPort + $offset
    $viewerCandidate = $PreferredViewerLocalPort + $offset
    $listener = Get-NetTCPConnection `
        -LocalAddress "127.0.0.1" `
        -LocalPort $candidate `
        -State Listen `
        -ErrorAction SilentlyContinue |
        Select-Object -First 1
    $viewerListener = Get-NetTCPConnection `
        -LocalAddress "127.0.0.1" `
        -LocalPort $viewerCandidate `
        -State Listen `
        -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $listener -and $null -eq $viewerListener) {
        $localPort = $candidate
        $viewerLocalPort = $viewerCandidate
        $startTunnel = $true
        break
    }

    if (
        $null -eq $listener -or
        $null -eq $viewerListener -or
        $listener.OwningProcess -ne $viewerListener.OwningProcess
    ) {
        continue
    }
    $process = Get-CimInstance Win32_Process `
        -Filter "ProcessId = $($listener.OwningProcess)" `
        -ErrorAction SilentlyContinue
    $expectedForward = "127.0.0.1:${candidate}:127.0.0.1:6080"
    $expectedViewerForward = (
        "127.0.0.1:${viewerCandidate}:${viewerAddress}:${viewerRemotePort}"
    )
    if (
        $null -ne $process -and
        $process.Name -eq "ssh.exe" -and
        $process.CommandLine -like "*$expectedForward*" -and
        $process.CommandLine -like "*$expectedViewerForward*" -and
        $process.CommandLine -like "*$target*"
    ) {
        $localPort = $candidate
        $viewerLocalPort = $viewerCandidate
        break
    }
}
if ($null -eq $localPort -or $null -eq $viewerLocalPort) {
    throw "No private local port pair is available for the Pi console tunnel."
}

if ($startTunnel) {
    $escapedKeyPath = $KeyPath.Replace('"', '\"')
    $tunnelArguments = (
        '-N -L 127.0.0.1:{0}:127.0.0.1:6080 ' +
        '-L 127.0.0.1:{1}:{2}:{3} ' +
        '-i "{4}" -o BatchMode=yes -o IdentitiesOnly=yes ' +
        '-o StrictHostKeyChecking=yes -o ExitOnForwardFailure=yes ' +
        '-o ServerAliveInterval=30 -o ServerAliveCountMax=3 {5}'
    ) -f (
        $localPort,
        $viewerLocalPort,
        $viewerAddress,
        $viewerRemotePort,
        $escapedKeyPath,
        $target
    )
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
        if (
            (Test-LocalTcpPort -Port $localPort) -and
            (Test-LocalTcpPort -Port $viewerLocalPort)
        ) {
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
    "http://127.0.0.1:${viewerLocalPort}/current/vnc.html" +
    "?host=127.0.0.1&port=${localPort}" +
    "&autoconnect=1&resize=scale&reconnect=1"
)
if (-not $NoOpen) {
    Start-Process $url
}
Write-Output $url
