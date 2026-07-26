# BoxBrain current Wi-Fi provisioning helper for Windows.
# The saved passphrase is sent only through SSH standard input to the Pi's fixed
# USB-C address. It is not printed, logged, placed in argv, or written to disk.

[CmdletBinding()]
param(
    [switch]$Authorized,
    [string]$PiAddress = '10.12.194.1',
    [string]$PiUser = 'kali',
    [string]$IdentityFile = "$env:USERPROFILE\.ssh\boxbrain_pi_ed25519",
    [string]$WifiInterface = 'wlan0'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$principal = New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent()
)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an Administrator PowerShell window.'
}
if ($PiAddress -cne '10.12.194.1') {
    throw 'Wi-Fi provisioning is restricted to the BoxBrain USB-C address 10.12.194.1.'
}
if ($PiUser -notmatch '^[A-Za-z_][A-Za-z0-9_-]{0,31}$') {
    throw 'The Pi user name is invalid.'
}
if ($WifiInterface -notmatch '^[A-Za-z0-9_.:-]{1,32}$') {
    throw 'The Pi Wi-Fi interface name is invalid.'
}
if (-not (Test-Path -LiteralPath $IdentityFile -PathType Leaf)) {
    throw "The Pi SSH identity was not found: $IdentityFile"
}
if ($IdentityFile.Contains('"')) {
    throw 'The Pi SSH identity path contains an unsupported quote character.'
}

Write-Host ''
Write-Host 'BOXBRAIN WI-FI PROVISIONING' -ForegroundColor Cyan
Write-Host 'This reads only the currently connected Windows Wi-Fi profile and'
Write-Host 'streams it to the Pi through the dedicated USB-C SSH connection.'
Write-Host 'The passphrase will not be displayed or saved by this helper.'
if (-not $Authorized) {
    $approval = Read-Host 'Type PROVISION WIFI to continue'
    if ($approval -cne 'PROVISION WIFI') {
        throw 'Wi-Fi provisioning was not authorized. No credential was read.'
    }
} else {
    Write-Host 'Authorization was explicitly supplied by the local operator.'
}

$interfaceOutput = @(& netsh.exe wlan show interfaces)
$ssidMatch = $interfaceOutput |
    Select-String -Pattern '^\s*SSID\s*:\s*(.+?)\s*$' |
    Select-Object -First 1
$profileMatch = $interfaceOutput |
    Select-String -Pattern '^\s*Profile\s*:\s*(.+?)\s*$' |
    Select-Object -First 1
if ($null -eq $ssidMatch -or $null -eq $profileMatch) {
    throw 'Windows is not currently connected to a Wi-Fi profile.'
}
$ssid = $ssidMatch.Matches[0].Groups[1].Value
$profileName = $profileMatch.Matches[0].Groups[1].Value

$profileOutput = @(& netsh.exe wlan show profile name="$profileName" key=clear)
$keyMatch = $profileOutput |
    Select-String -Pattern '^\s*Key Content\s*:\s*(.+?)\s*$' |
    Select-Object -First 1
if ($null -eq $keyMatch) {
    throw 'The current profile has no readable WPA/WPA2 personal passphrase.'
}
$passphrase = $keyMatch.Matches[0].Groups[1].Value
$profileOutput = $null
$keyMatch = $null

$payload = [ordered]@{
    schema_version = 1
    source = 'windows-current-profile'
    transport = 'usb-c-ssh'
    ssid = $ssid
    passphrase = $passphrase
} | ConvertTo-Json -Compress

$ssh = (Get-Command ssh.exe -ErrorAction Stop).Source
$start = New-Object Diagnostics.ProcessStartInfo
$start.FileName = $ssh
$start.Arguments = (
    '-i "{0}" -o BatchMode=yes -o ConnectTimeout=10 -o IdentitiesOnly=yes ' +
    '-o StrictHostKeyChecking=yes {1}@{2} ' +
    '"sudo -n /usr/local/bin/boxbrainctl wifi-provision --stdin --authorized --interface {3}"'
) -f $IdentityFile, $PiUser, $PiAddress, $WifiInterface
$start.UseShellExecute = $false
$start.CreateNoWindow = $true
$start.RedirectStandardInput = $true
$start.RedirectStandardOutput = $true
$start.RedirectStandardError = $true

$process = New-Object Diagnostics.Process
$process.StartInfo = $start
try {
    if (-not $process.Start()) {
        throw 'Could not start the secure Pi connection.'
    }
    $process.StandardInput.Write($payload)
    $process.StandardInput.Close()
    $payload = $null
    $passphrase = $null
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) {
        if ($stderr -match 'Host key verification failed') {
            throw 'The Pi host key is not trusted. Verify it over USB-C before provisioning.'
        }
        throw 'The Pi rejected the Wi-Fi profile. No credential was logged.'
    }
    $result = $stdout | ConvertFrom-Json
    Write-Host ''
    Write-Host ('Pi connected to Wi-Fi: {0}' -f $result.ssid) -ForegroundColor Green
    Write-Host ('Interface: {0}; profile: {1}' -f $result.interface, $result.profile)
    Write-Host 'Credential transport: USB-C SSH standard input; logging disabled.'
} finally {
    $payload = $null
    $passphrase = $null
    if ($null -ne $process) {
        $process.Dispose()
    }
}
