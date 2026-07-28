# BoxBrain target link for Windows.
# Review this file before running it. It creates a non-administrator local user,
# enables Microsoft's OpenSSH server, and authorizes one BoxBrain public key.

[CmdletBinding()]
param(
    [switch]$Authorized,
    [string[]]$BoxBrainAddress = @('10.12.194.1')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Test-BoxBrainPrivateIPv4 {
    param([string]$Address)

    $parsed = $null
    if (-not [Net.IPAddress]::TryParse($Address, [ref]$parsed)) {
        return $false
    }
    if ($parsed.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) {
        return $false
    }
    $octets = $parsed.GetAddressBytes()
    return (
        $octets[0] -eq 10 -or
        ($octets[0] -eq 172 -and $octets[1] -ge 16 -and $octets[1] -le 31) -or
        ($octets[0] -eq 192 -and $octets[1] -eq 168) -or
        ($octets[0] -eq 169 -and $octets[1] -eq 254)
    )
}

$principal = New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent()
)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an Administrator PowerShell window.'
}

Write-Host ''
Write-Host 'BOXBRAIN AUTHORIZATION' -ForegroundColor Cyan
Write-Host 'This will enable an SSH service and create a non-administrator'
Write-Host 'account named boxbrain-link for this authorized BoxBrain agent.'
Write-Host 'Only use this on a computer you own or are authorized to assess.'
if (-not $Authorized) {
    $approval = Read-Host 'Type AUTHORIZE to continue'
    if ($approval -cne 'AUTHORIZE') {
        throw 'Authorization was not confirmed. No changes were made.'
    }
} else {
    Write-Host 'Authorization was explicitly supplied by the local operator.'
}

$remoteAddresses = @(
    foreach ($address in $BoxBrainAddress) {
        $candidate = $address.Trim()
        if (-not (Test-BoxBrainPrivateIPv4 $candidate)) {
            throw "BoxBrainAddress must contain only RFC1918 or link-local IPv4 addresses: $candidate"
        }
        $candidate
    }
) | Sort-Object -Unique
if ($remoteAddresses.Count -eq 0) {
    throw 'At least one BoxBrain Pi address is required.'
}

$userName = 'boxbrain-link'
$publicKey = '__BOXBRAIN_PUBLIC_KEY__'
$capabilityName = 'OpenSSH.Server~~~~0.0.1.0'
$capability = Get-WindowsCapability -Online -Name $capabilityName
$installedNow = $false
if ($capability.State -ne 'Installed') {
    Write-Host 'Installing Microsoft OpenSSH Server...'
    Add-WindowsCapability -Online -Name $capabilityName | Out-Null
    $installedNow = $true
}

$user = Get-LocalUser -Name $userName -ErrorAction SilentlyContinue
if ($null -eq $user) {
    $randomBytes = New-Object byte[] 48
    $randomGenerator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $randomGenerator.GetBytes($randomBytes)
    } finally {
        $randomGenerator.Dispose()
    }
    $randomPassword = [Convert]::ToBase64String($randomBytes)
    $securePassword = ConvertTo-SecureString $randomPassword -AsPlainText -Force
    $user = New-LocalUser `
        -Name $userName `
        -Password $securePassword `
        -AccountNeverExpires `
        -UserMayNotChangePassword `
        -Description 'BoxBrain authorized target SSH link'
}
Enable-LocalUser -Name $userName
$usersGroup = Get-LocalGroup -SID 'S-1-5-32-545'
$isUsersMember = Get-LocalGroupMember -Group $usersGroup -ErrorAction SilentlyContinue |
    Where-Object { $_.SID -eq $user.SID }
if ($null -eq $isUsersMember) {
    Add-LocalGroupMember -Group $usersGroup -Member $userName
}

$profileDirectory = Join-Path $env:SystemDrive "Users\$userName"
$sshDirectory = Join-Path $profileDirectory '.ssh'
$authorizedKeys = Join-Path $sshDirectory 'authorized_keys'
New-Item -ItemType Directory -Force -Path $sshDirectory | Out-Null
[IO.File]::WriteAllText($authorizedKeys, "$publicKey`n", [Text.UTF8Encoding]::new($false))

$userAccount = New-Object Security.Principal.NTAccount(
    "$env:COMPUTERNAME\$userName"
)
$userSid = $userAccount.Translate([Security.Principal.SecurityIdentifier])
$systemSid = New-Object Security.Principal.SecurityIdentifier('S-1-5-18')
$adminsSid = New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')

$directoryAcl = New-Object Security.AccessControl.DirectorySecurity
$directoryAcl.SetAccessRuleProtection($true, $false)
foreach ($sid in @($userSid, $systemSid, $adminsSid)) {
    $rule = New-Object Security.AccessControl.FileSystemAccessRule(
        $sid,
        'FullControl',
        'ContainerInherit,ObjectInherit',
        'None',
        'Allow'
    )
    $directoryAcl.AddAccessRule($rule)
}
Set-Acl -Path $sshDirectory -AclObject $directoryAcl

$fileAcl = New-Object Security.AccessControl.FileSecurity
$fileAcl.SetAccessRuleProtection($true, $false)
foreach ($sid in @($userSid, $systemSid, $adminsSid)) {
    $rule = New-Object Security.AccessControl.FileSystemAccessRule(
        $sid,
        'FullControl',
        'Allow'
    )
    $fileAcl.AddAccessRule($rule)
}
Set-Acl -Path $authorizedKeys -AclObject $fileAcl
$programAuthorizedKeys = Join-Path $env:ProgramData 'ssh\boxbrain_authorized_keys'
New-Item -ItemType Directory -Force -Path (Split-Path $programAuthorizedKeys) | Out-Null
[IO.File]::WriteAllText(
    $programAuthorizedKeys,
    "$publicKey`n",
    [Text.UTF8Encoding]::new($false)
)
Set-Acl -Path $programAuthorizedKeys -AclObject $fileAcl

$configPath = Join-Path $env:ProgramData 'ssh\sshd_config'
if (-not (Test-Path $configPath)) {
    Set-Service -Name sshd -StartupType Automatic
    Start-Service -Name sshd
    Start-Sleep -Seconds 1
    Stop-Service -Name sshd
}
if (-not (Test-Path $configPath)) {
    $defaultConfig = Join-Path $env:SystemRoot 'System32\OpenSSH\sshd_config_default'
    New-Item -ItemType Directory -Force -Path (Split-Path $configPath) | Out-Null
    Copy-Item $defaultConfig $configPath
}
$config = Get-Content -Raw $configPath
$marker = '# BEGIN BOXBRAIN LINK'
if (-not $config.Contains($marker)) {
    Copy-Item $configPath "$configPath.boxbrain-backup-$(Get-Date -Format yyyyMMdd-HHmmss)"
}
$block = @'

# BEGIN BOXBRAIN LINK
Match User boxbrain-link
    AuthorizedKeysFile __PROGRAMDATA__/ssh/boxbrain_authorized_keys
    AuthenticationMethods publickey
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    PermitTTY no
    AllowTcpForwarding no
    X11Forwarding no
    PermitTunnel no
# END BOXBRAIN LINK
'@
if ($config.Contains($marker)) {
    $pattern = '(?s)\r?\n?# BEGIN BOXBRAIN LINK.*?# END BOXBRAIN LINK'
    $config = [Text.RegularExpressions.Regex]::Replace($config, $pattern, $block)
    [IO.File]::WriteAllText($configPath, $config, [Text.UTF8Encoding]::new($false))
} else {
    Add-Content -Path $configPath -Value $block -Encoding utf8
}

$sshd = Join-Path $env:SystemRoot 'System32\OpenSSH\sshd.exe'
& $sshd -t -f $configPath
if ($LASTEXITCODE -ne 0) {
    throw 'OpenSSH rejected its configuration. Restore the newest .boxbrain-backup file.'
}

# Keep the legacy display name so upgrades narrow the existing rule in place.
$ruleName = 'BoxBrain USB SSH'
if (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue) {
    Set-NetFirewallRule -DisplayName $ruleName -Enabled True -Action Allow
    Get-NetFirewallRule -DisplayName $ruleName |
        Get-NetFirewallAddressFilter |
        Set-NetFirewallAddressFilter -RemoteAddress $remoteAddresses
} else {
    New-NetFirewallRule `
        -DisplayName $ruleName `
        -Direction Inbound `
        -Action Allow `
        -Protocol TCP `
        -LocalPort 22 `
        -RemoteAddress $remoteAddresses `
        -Profile Any | Out-Null
}

if ($installedNow) {
    Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue |
        Disable-NetFirewallRule
}
Set-Service -Name sshd -StartupType Automatic
Restart-Service -Name sshd

Write-Host ''
Write-Host 'BoxBrain link authorized.' -ForegroundColor Green
Write-Host 'The boxbrain-link account is not an administrator.'
Write-Host ('Allowed Pi address(es): {0}' -f ($remoteAddresses -join ', '))
Write-Host 'USB-C targets are detected automatically after this authorization.'
Write-Host 'For Wi-Fi/Ethernet, run this on the Pi:'
Write-Host '  boxbrainctl add-target <this-computer-private-ip> --authorized'
