[CmdletBinding()]
param(
    [string]$VmName = 'BoxBrain-Windows-Lab',
    [string]$CredentialPath = 'C:\VMs\BoxBrain-Windows-Lab\secrets\lab-credential.clixml',
    [string]$StatusPath = 'C:\VMs\BoxBrain-Windows-Lab\guest-provisioning.json',
    [string]$OnboardingUrl = 'http://10.12.194.1:8788/windows-link.ps1',
    [Parameter(Mandatory)]
    [string]$ExpectedScriptSha256
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-ProvisioningStatus {
    param(
        [Parameter(Mandatory)][string]$Stage,
        [ValidateSet('running', 'complete', 'failed')][string]$State = 'running',
        [string]$Message = '',
        [hashtable]$Checks
    )

    $status = [ordered]@{
        recorded_at = (Get-Date).ToUniversalTime().ToString('o')
        vm_name = $VmName
        state = $State
        stage = $Stage
        message = $Message
    }
    if ($Checks) {
        $status.checks = $Checks
    }
    $status | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $StatusPath -Encoding UTF8
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an elevated Windows PowerShell session.'
}

$expectedUri = [Uri]'http://10.12.194.1:8788/windows-link.ps1'
$actualUri = [Uri]$OnboardingUrl
if (
    $actualUri.Scheme -cne $expectedUri.Scheme -or
    $actualUri.Host -cne $expectedUri.Host -or
    $actualUri.Port -ne $expectedUri.Port -or
    $actualUri.AbsolutePath -cne $expectedUri.AbsolutePath
) {
    throw 'OnboardingUrl must be the fixed reviewed BoxBrain Pi endpoint.'
}
if ($ExpectedScriptSha256 -notmatch '^[A-Fa-f0-9]{64}$') {
    throw 'ExpectedScriptSha256 must be a 64-character SHA-256 value.'
}

Import-Module Hyper-V -ErrorAction Stop
$vm = Get-VM -Name $VmName -ErrorAction Stop
if ($vm.State -ne 'Running') {
    throw "VM must be running for guest provisioning; current state is $($vm.State)."
}
if (-not (Test-Path -LiteralPath $CredentialPath -PathType Leaf)) {
    throw "Encrypted lab credential not found: $CredentialPath"
}

$credential = Import-Clixml -LiteralPath $CredentialPath
if ($credential -isnot [Management.Automation.PSCredential]) {
    throw 'Encrypted lab credential file did not contain a PSCredential.'
}

$session = $null
try {
    Write-ProvisioningStatus -Stage 'connect' -Message 'Connecting through Hyper-V PowerShell Direct.'
    $session = New-PSSession -VMName $VmName -Credential $credential -ErrorAction Stop

    Write-ProvisioningStatus -Stage 'verify-script' `
        -Message 'Downloading and hash-checking the reviewed Pi onboarding script inside the VM.'
    $guestPreparation = Invoke-Command -Session $session -ScriptBlock {
        param($Url, $ExpectedHash)

        Set-ItemProperty `
            -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server' `
            -Name fDenyTSConnections `
            -Value 0
        Enable-NetFirewallRule -DisplayGroup 'Remote Desktop'
        New-Item -ItemType Directory -Path 'C:\ProgramData\BoxBrain' -Force | Out-Null

        $link = 'C:\Windows\Temp\boxbrain-link.ps1'
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $link
        $actualHash = (Get-FileHash -LiteralPath $link -Algorithm SHA256).Hash
        if ($actualHash -cne $ExpectedHash.ToUpperInvariant()) {
            throw "Downloaded onboarding script hash did not match the reviewed value: $actualHash"
        }

        [pscustomobject]@{
            script_path = $link
            script_sha256 = $actualHash
            pi_reachable = Test-NetConnection 10.12.194.1 -Port 8788 `
                -InformationLevel Quiet -WarningAction SilentlyContinue
        }
    } -ArgumentList $OnboardingUrl, $ExpectedScriptSha256

    if (-not $guestPreparation.pi_reachable) {
        throw 'The guest could download the script but did not confirm the Pi onboarding port.'
    }

    Write-ProvisioningStatus -Stage 'authorize-link' `
        -Message 'Creating the restricted BoxBrain link account and SSH service inside the VM.'
    Invoke-Command -Session $session -ScriptBlock {
        $link = 'C:\Windows\Temp\boxbrain-link.ps1'
        & powershell.exe `
            -NoProfile `
            -ExecutionPolicy Bypass `
            -File $link `
            -Authorized `
            -BoxBrainAddress '10.12.194.1'
        if ($LASTEXITCODE -ne 0) {
            throw "BoxBrain onboarding script failed with exit code $LASTEXITCODE."
        }
        'complete' | Set-Content `
            -LiteralPath 'C:\ProgramData\BoxBrain\provisioned.ok' `
            -Encoding ASCII
    }

    Write-ProvisioningStatus -Stage 'verify' `
        -Message 'Verifying the guest service, account, firewall, and authorization boundary.'
    $checks = Invoke-Command -Session $session -ScriptBlock {
        $administratorGroup = Get-LocalGroup -SID 'S-1-5-32-544'
        $administratorMembers = @(
            Get-LocalGroupMember -Group $administratorGroup -ErrorAction SilentlyContinue |
                ForEach-Object Name
        )
        $linkUser = Get-LocalUser -Name 'boxbrain-link' -ErrorAction SilentlyContinue
        $sshRule = Get-NetFirewallRule -DisplayName 'BoxBrain USB SSH' -ErrorAction SilentlyContinue
        $sshAddresses = @(
            $sshRule |
                Get-NetFirewallAddressFilter -ErrorAction SilentlyContinue |
                ForEach-Object RemoteAddress
        )

        [pscustomobject]@{
            provisioned_marker = Test-Path -LiteralPath 'C:\ProgramData\BoxBrain\provisioned.ok'
            rdp_running = (Get-Service -Name TermService).Status -eq 'Running'
            ssh_running = (Get-Service -Name sshd).Status -eq 'Running'
            link_user_exists = [bool]$linkUser
            link_user_enabled = [bool]($linkUser -and $linkUser.Enabled)
            link_user_not_admin = [bool](
                $linkUser -and -not (
                    $administratorMembers |
                        Where-Object { $_ -match '\\boxbrain-link$' }
                )
            )
            ssh_firewall_enabled = [bool]($sshRule -and $sshRule.Enabled -eq 'True')
            ssh_firewall_pi_only = (
                $sshAddresses.Count -eq 1 -and
                $sshAddresses[0] -eq '10.12.194.1'
            )
        }
    }

    $checkTable = @{}
    foreach ($property in $checks.PSObject.Properties) {
        if ($property.Name -notin @('PSComputerName', 'RunspaceId', 'PSShowComputerName')) {
            $checkTable[$property.Name] = [bool]$property.Value
        }
    }
    if ($checkTable.Values -contains $false) {
        throw 'One or more guest provisioning checks did not pass.'
    }

    Write-ProvisioningStatus -Stage 'complete' -State complete `
        -Message 'The VM is linked to BoxBrain through the restricted Pi-only SSH boundary.' `
        -Checks $checkTable
    Get-Content -LiteralPath $StatusPath -Raw
} catch {
    Write-ProvisioningStatus -Stage 'failed' -State failed -Message $_.Exception.Message
    throw
} finally {
    if ($session) {
        Remove-PSSession -Session $session -ErrorAction SilentlyContinue
    }
}
