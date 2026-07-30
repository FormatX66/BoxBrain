[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [ValidatePattern('^[A-Za-z0-9._-]{1,80}$')]
    [string]$VmName = 'BoxBrain-Windows-Lab',

    [ValidatePattern('^[A-Za-z0-9._-]{1,80}$')]
    [string]$GuestUser = 'boxbrain-lab',

    [ValidatePattern('^[A-Za-z0-9-]{1,63}$')]
    [string]$GuestComputerName = 'BB-WIN-LAB',

    [string]$CredentialPath =
        'C:\VMs\BoxBrain-Windows-Lab\secrets\lab-credential.clixml',

    [string]$StatusPath =
        'C:\VMs\BoxBrain-Windows-Lab\credential-rotation-status.json',

    [string]$ErrorPath =
        'C:\VMs\BoxBrain-Windows-Lab\logs\credential-rotation-error.json'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$pendingCredentialPath = $null
$guestPasswordChanged = $false
$oldSession = $null
$verificationSession = $null
$randomBytes = $null
$newPassword = $null

trap {
    $errorDirectory = Split-Path -Parent $ErrorPath
    if (Test-Path -LiteralPath $errorDirectory -PathType Container) {
        [ordered]@{
            recorded_at = (Get-Date).ToUniversalTime().ToString('o')
            vm_name = $VmName
            guest_user = $GuestUser
            password_changed = $guestPasswordChanged
            pending_credential_path = $pendingCredentialPath
            error = $_.Exception.Message
            category = $_.CategoryInfo.Category.ToString()
            script_line = $_.InvocationInfo.ScriptLineNumber
        } | ConvertTo-Json |
            Set-Content -LiteralPath $ErrorPath -Encoding UTF8
    }
    throw
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )) {
    throw 'Run this script from an elevated Windows PowerShell session.'
}

Import-Module Hyper-V -ErrorAction Stop
$vm = Get-VM -Name $VmName -ErrorAction Stop
if ($vm.State -ne 'Running') {
    throw "VM must be running to rotate its credential; current state is $($vm.State)."
}
if (-not (Test-Path -LiteralPath $CredentialPath -PathType Leaf)) {
    throw "Encrypted lab credential not found: $CredentialPath"
}

$oldCredential = Import-Clixml -LiteralPath $CredentialPath
if ($oldCredential -isnot [Management.Automation.PSCredential]) {
    throw 'Encrypted lab credential file did not contain a PSCredential.'
}
$expectedSuffix = "\$GuestUser"
if (
    $oldCredential.UserName -ne $GuestUser -and
    -not $oldCredential.UserName.EndsWith(
        $expectedSuffix,
        [StringComparison]::OrdinalIgnoreCase
    )
) {
    throw 'Encrypted credential does not belong to the expected lab account.'
}

$credentialDirectory = Split-Path -Parent $CredentialPath
$statusDirectory = Split-Path -Parent $StatusPath
foreach ($directory in @($credentialDirectory, $statusDirectory)) {
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
        throw "Required directory does not exist: $directory"
    }
}

$action = (
    "Rotate the dedicated '$GuestUser' password inside '$VmName' and " +
    'replace its current-user DPAPI credential'
)
if (-not $PSCmdlet.ShouldProcess($VmName, $action)) {
    return
}

try {
    $randomBytes = New-Object byte[] 48
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($randomBytes)
    }
    finally {
        $generator.Dispose()
    }
    $newPassword = [Convert]::ToBase64String($randomBytes)
    $newSecurePassword = ConvertTo-SecureString `
        -String $newPassword `
        -AsPlainText `
        -Force
    $newCredential = [Management.Automation.PSCredential]::new(
        $oldCredential.UserName,
        $newSecurePassword
    )

    $pendingCredentialPath = Join-Path $credentialDirectory (
        '.lab-credential.pending-' + [Guid]::NewGuid().ToString('N') +
        '.clixml'
    )
    $newCredential | Export-Clixml -LiteralPath $pendingCredentialPath

    $oldSession = New-PSSession `
        -VMName $VmName `
        -Credential $oldCredential `
        -ErrorAction Stop
    $changedIdentity = Invoke-Command -Session $oldSession -ScriptBlock {
        param(
            [string]$ExpectedComputerName,
            [string]$ExpectedGuestUser,
            [Security.SecureString]$ReplacementPassword
        )
        if ($env:COMPUTERNAME -ne $ExpectedComputerName) {
            throw 'PowerShell Direct reached an unexpected guest.'
        }
        $account = Get-LocalUser `
            -Name $ExpectedGuestUser `
            -ErrorAction Stop
        if (-not $account.Enabled) {
            throw 'The dedicated lab account is disabled.'
        }
        Set-LocalUser `
            -Name $ExpectedGuestUser `
            -Password $ReplacementPassword `
            -ErrorAction Stop
        [ordered]@{
            computer_name = $env:COMPUTERNAME
            guest_user = $ExpectedGuestUser
        }
    } -ArgumentList @(
        $GuestComputerName,
        $GuestUser,
        $newSecurePassword
    )
    $guestPasswordChanged = $true
    Remove-PSSession -Session $oldSession -ErrorAction SilentlyContinue
    $oldSession = $null

    $verificationSession = New-PSSession `
        -VMName $VmName `
        -Credential $newCredential `
        -ErrorAction Stop
    $verifiedIdentity = Invoke-Command `
        -Session $verificationSession `
        -ScriptBlock {
            [ordered]@{
                computer_name = $env:COMPUTERNAME
                user_name = [Security.Principal.WindowsIdentity]::GetCurrent().Name
            }
        }
    if (
        $verifiedIdentity.computer_name -ne $GuestComputerName -or
        -not $verifiedIdentity.user_name.EndsWith(
            "\$GuestUser",
            [StringComparison]::OrdinalIgnoreCase
        )
    ) {
        throw 'The rotated credential opened an unexpected guest identity.'
    }

    Move-Item `
        -LiteralPath $pendingCredentialPath `
        -Destination $CredentialPath `
        -Force
    $pendingCredentialPath = $null

    $status = [ordered]@{
        recorded_at = (Get-Date).ToUniversalTime().ToString('o')
        vm_name = $vm.Name
        vm_id = $vm.Id.ToString()
        guest_user = $GuestUser
        credential_user = $newCredential.UserName
        password_changed = $true
        new_credential_verified = $true
        credential_storage = 'current-user DPAPI CLIXML'
    }
    $status | ConvertTo-Json |
        Set-Content -LiteralPath $StatusPath -Encoding UTF8
    $status | ConvertTo-Json
}
finally {
    if ($oldSession) {
        Remove-PSSession -Session $oldSession -ErrorAction SilentlyContinue
    }
    if ($verificationSession) {
        Remove-PSSession `
            -Session $verificationSession `
            -ErrorAction SilentlyContinue
    }
    if ($randomBytes) {
        [Array]::Clear($randomBytes, 0, $randomBytes.Length)
    }
    $newPassword = $null
    $newSecurePassword = $null
    $newCredential = $null
    $oldCredential = $null
}
