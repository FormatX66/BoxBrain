[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$HopperAddress,

    [ValidateRange(1024, 65535)]
    [int]$LocalPort = 6080,

    [string]$IdentityFile = (Join-Path $env:USERPROFILE '.ssh\aurum_hopper_ed25519'),

    [string]$KnownHostsFile = (Join-Path $env:USERPROFILE '.ssh\aurum_hopper_known_hosts')
)

$ErrorActionPreference = 'Stop'
foreach ($path in @($IdentityFile, $KnownHostsFile)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required Hopper trust file is missing: $path" }
}
$ssh = (Get-Command ssh.exe -ErrorAction Stop).Source
$arguments = @(
    '-T',
    '-i', $IdentityFile,
    '-o', 'BatchMode=yes',
    '-o', 'IdentitiesOnly=yes',
    '-o', 'StrictHostKeyChecking=yes',
    '-o', "UserKnownHostsFile=$KnownHostsFile",
    '-o', 'ExitOnForwardFailure=yes',
    '-L', "127.0.0.1:${LocalPort}:127.0.0.1:6080",
    "aurum-remote@$HopperAddress",
    'desktop-tunnel'
)
$tunnel = Start-Process -FilePath $ssh -ArgumentList $arguments -PassThru -WindowStyle Hidden
$viewer = "http://127.0.0.1:$LocalPort/vnc.html?host=127.0.0.1&port=$LocalPort&autoconnect=1&resize=scale"
$probe = "http://127.0.0.1:$LocalPort/vnc.html"
$deadline = [DateTime]::UtcNow.AddSeconds(45)
$ready = $false
while ([DateTime]::UtcNow -lt $deadline) {
    if ($tunnel.HasExited) { throw 'The guarded Hopper desktop tunnel did not start.' }
    try {
        $response = Invoke-WebRequest -Uri $probe -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) { $ready = $true; break }
    }
    catch {
        Start-Sleep -Seconds 1
    }
}
if (-not $ready) {
    Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue
    throw 'Hopper did not prove the browser Remote Desktop listener within 45 seconds.'
}
Start-Process $viewer | Out-Null
Write-Output "AURUM_HOPPER_REMOTE_DESKTOP status=ready tunnel_pid=$($tunnel.Id) viewer=$viewer"
Write-Output "Stop with: Stop-Process -Id $($tunnel.Id)"
Write-Output 'Stopping the tunnel also stops Hopper Remote Desktop.'
