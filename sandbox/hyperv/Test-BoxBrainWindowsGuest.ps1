[CmdletBinding()]
param(
    [string]$VmName = 'BoxBrain-Windows-Lab',
    [string]$CredentialPath = 'C:\VMs\BoxBrain-Windows-Lab\secrets\lab-credential.clixml',
    [string]$StatusPath = 'C:\VMs\BoxBrain-Windows-Lab\guest-verification.json'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an elevated Windows PowerShell session.'
}

Import-Module Hyper-V -ErrorAction Stop
$vm = Get-VM -Name $VmName -ErrorAction Stop
if ($vm.State -ne 'Running') {
    throw "VM must be running for guest verification; current state is $($vm.State)."
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
    $session = New-PSSession -VMName $VmName -Credential $credential -ErrorAction Stop

    $guest = Invoke-Command -Session $session -ScriptBlock {
        $administratorGroup = Get-LocalGroup -SID 'S-1-5-32-544'
        $administratorMembers = @(
            Get-LocalGroupMember -Group $administratorGroup -ErrorAction SilentlyContinue |
                ForEach-Object Name
        )
        $linkUser = Get-LocalUser -Name 'boxbrain-link' -ErrorAction SilentlyContinue
        $rdpRule = Get-NetFirewallRule -DisplayGroup 'Remote Desktop' -ErrorAction SilentlyContinue |
            Where-Object Enabled -eq 'True' |
            Select-Object -First 1
        $sshRule = Get-NetFirewallRule -DisplayName 'BoxBrain USB SSH' -ErrorAction SilentlyContinue
        $sshd = Get-Service -Name sshd -ErrorAction SilentlyContinue
        $sshCapability = Get-WindowsCapability `
            -Online `
            -Name 'OpenSSH.Server~~~~0.0.1.0' `
            -ErrorAction SilentlyContinue
        $servicingProcesses = @(
            Get-Process -Name dism,TiWorker,TrustedInstaller,MoUsoCoreWorker `
                -ErrorAction SilentlyContinue |
                Select-Object ProcessName, CPU, StartTime |
                Sort-Object ProcessName
        )
        $ipv4 = @(
            Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
                Where-Object {
                    $_.IPAddress -notlike '127.*' -and
                    $_.AddressState -eq 'Preferred'
                } |
                ForEach-Object IPAddress
        )
        $internetHttps = $false
        $internetClient = [Net.Sockets.TcpClient]::new()
        try {
            $internetTask = $internetClient.ConnectAsync('www.microsoft.com', 443)
            $internetHttps = $internetTask.Wait(3000) -and $internetClient.Connected
        } catch {
            $internetHttps = $false
        } finally {
            $internetClient.Dispose()
        }

        [ordered]@{
            computer_name = $env:COMPUTERNAME
            os_caption = (Get-CimInstance Win32_OperatingSystem).Caption
            os_version = (Get-CimInstance Win32_OperatingSystem).Version
            provisioned_marker = Test-Path -LiteralPath 'C:\ProgramData\BoxBrain\provisioned.ok'
            rdp_service_status = (Get-Service -Name TermService).Status.ToString()
            rdp_firewall_enabled = [bool]$rdpRule
            ssh_service_exists = [bool]$sshd
            ssh_service_status = if ($sshd) { $sshd.Status.ToString() } else { $null }
            ssh_capability_state = if ($sshCapability) { $sshCapability.State.ToString() } else { $null }
            servicing_processes = $servicingProcesses
            ssh_firewall_enabled = [bool]($sshRule -and $sshRule.Enabled -eq 'True')
            link_user_exists = [bool]$linkUser
            link_user_enabled = if ($linkUser) { [bool]$linkUser.Enabled } else { $null }
            link_user_is_administrator = [bool](
                $administratorMembers |
                    Where-Object { $_ -match '\\boxbrain-link$' }
            )
            ipv4_addresses = $ipv4
            microsoft_https_reachable = $internetHttps
        }
    }

    $checks = [ordered]@{
        expected_computer_name = $guest.computer_name -eq 'BB-WIN-LAB'
        pi_network_address = [bool]($guest.ipv4_addresses | Where-Object { $_ -like '10.12.194.*' })
        rdp_running = $guest.rdp_service_status -eq 'Running'
        rdp_firewall_enabled = [bool]$guest.rdp_firewall_enabled
        provisioning_complete = [bool]$guest.provisioned_marker
        restricted_link_user_exists = [bool]$guest.link_user_exists
        restricted_link_user_not_admin = $guest.link_user_exists -and -not $guest.link_user_is_administrator
        ssh_running = $guest.ssh_service_status -eq 'Running'
        ssh_firewall_enabled = [bool]$guest.ssh_firewall_enabled
    }
    $allChecksPassed = -not ($checks.Values -contains $false)

    $result = [ordered]@{
        recorded_at = (Get-Date).ToUniversalTime().ToString('o')
        vm_name = $VmName
        state = if ($allChecksPassed) { 'complete' } else { 'pending' }
        guest = $guest
        checks = $checks
    }
    $result | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $StatusPath -Encoding UTF8
    $result | ConvertTo-Json -Depth 7
} catch {
    $result = [ordered]@{
        recorded_at = (Get-Date).ToUniversalTime().ToString('o')
        vm_name = $VmName
        state = 'unavailable'
        error = $_.Exception.Message
    }
    $result | ConvertTo-Json | Set-Content -LiteralPath $StatusPath -Encoding UTF8
    $result | ConvertTo-Json
} finally {
    if ($session) {
        Remove-PSSession -Session $session -ErrorAction SilentlyContinue
    }
}
