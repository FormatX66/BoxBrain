#Requires -Version 5.1
[CmdletBinding()]
param(
    [string[]]$PiAddresses = @("10.12.194.1", "10.42.194.1", "192.168.0.194"),
    [ValidatePattern("^[a-z_][a-z0-9_-]{0,31}$")]
    [string]$PiUser = "kali",
    [string]$KeyPath = (Join-Path $HOME ".ssh\boxbrain_pi_ed25519"),
    [string]$KnownHostsPath = (Join-Path $HOME ".ssh\known_hosts"),
    [switch]$NoLaunch
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$approvedAddresses = @("10.12.194.1", "10.42.194.1", "192.168.0.194")
foreach ($address in $PiAddresses) {
    if ($address -notin $approvedAddresses) {
        throw "PiAddress is not an approved BBPI4 route: $address"
    }
}
if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
    throw "The dedicated BoxBrain SSH identity was not found at $KeyPath."
}
if (-not (Test-Path -LiteralPath $KnownHostsPath -PathType Leaf)) {
    throw "The strict SSH known-hosts file was not found at $KnownHostsPath."
}

$ssh = Get-Command ssh.exe -CommandType Application -ErrorAction Stop
$baseOptions = @(
    "-i", $KeyPath,
    "-o", "BatchMode=yes",
    "-o", "IdentitiesOnly=yes",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "UserKnownHostsFile=$KnownHostsPath",
    "-o", "ConnectTimeout=8"
)

$selected = $null
foreach ($address in $PiAddresses) {
    $status = @(& $ssh.Source @baseOptions "$PiUser@$address" "/usr/local/bin/aurum --status" 2>$null)
    if ($LASTEXITCODE -eq 0 -and ($status -join "`n").Contains("AURUM_CONSOLE_READY")) {
        $selected = $address
        break
    }
}
if ($null -eq $selected) {
    throw "The verified Aurum console was not reachable over an approved BBPI4 route."
}

Write-Output "AURUM_CONSOLE_ROUTE_VERIFIED address=$selected command=/usr/local/bin/aurum"
if ($NoLaunch) {
    return
}

$launchArguments = @("-tt") + $baseOptions + @("$PiUser@$selected", "aurum")
$process = Start-Process `
    -FilePath $ssh.Source `
    -ArgumentList $launchArguments `
    -WindowStyle Normal `
    -PassThru
Write-Output "AURUM_CONSOLE_WINDOW_STARTED pid=$($process.Id) address=$selected"
