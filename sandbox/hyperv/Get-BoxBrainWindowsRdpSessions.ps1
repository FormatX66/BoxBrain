[CmdletBinding()]
param(
    [ValidatePattern('^[A-Za-z0-9._-]{1,80}$')]
    [string]$VmName = 'BoxBrain-Windows-Lab',

    [string]$CredentialPath = 'C:\VMs\BoxBrain-Windows-Lab\secrets\lab-credential.clixml',

    [string]$OutputPath = 'C:\VMs\BoxBrain-Windows-Lab\rdp-session-diagnostic.json'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

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
    throw "VM must be running for RDP session diagnosis; current state is $($vm.State)."
}
if (-not (Test-Path -LiteralPath $CredentialPath -PathType Leaf)) {
    throw "Encrypted lab credential not found: $CredentialPath"
}

$credential = Import-Clixml -LiteralPath $CredentialPath
if ($credential -isnot [Management.Automation.PSCredential]) {
    throw 'Encrypted lab credential file did not contain a PSCredential.'
}

$outputDirectory = Split-Path -Parent $OutputPath
if (-not (Test-Path -LiteralPath $outputDirectory -PathType Container)) {
    throw "Output directory does not exist: $outputDirectory"
}

$session = $null
try {
    $session = New-PSSession `
        -VMName $VmName `
        -Credential $credential `
        -ErrorAction Stop

    $guest = Invoke-Command -Session $session -ScriptBlock {
        $terminalServerPath = (
            'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server'
        )
        $terminalServer = Get-ItemProperty `
            -LiteralPath $terminalServerPath `
            -ErrorAction Stop

        $sessionLines = @(
            (& "$env:SystemRoot\System32\qwinsta.exe" 2>&1) |
                ForEach-Object { $_.ToString() }
        )

        $processes = @()
        foreach ($process in @(
            Get-CimInstance Win32_Process -ErrorAction Stop |
                Where-Object Name -in @(
                    'explorer.exe',
                    'LogonUI.exe',
                    'rdpclip.exe',
                    'userinit.exe'
                )
        )) {
            $owner = Invoke-CimMethod `
                -InputObject $process `
                -MethodName GetOwner `
                -ErrorAction SilentlyContinue
            $processes += [ordered]@{
                name = $process.Name
                process_id = [int]$process.ProcessId
                session_id = [int]$process.SessionId
                owner = if ($owner -and $owner.ReturnValue -eq 0) {
                    if ($owner.Domain) {
                        "$($owner.Domain)\$($owner.User)"
                    } else {
                        $owner.User
                    }
                } else {
                    $null
                }
            }
        }

        $eventChannels = @(
            'Microsoft-Windows-TerminalServices-' +
                'LocalSessionManager/Operational',
            'Microsoft-Windows-TerminalServices-' +
                'RemoteConnectionManager/Operational'
        )
        $events = @()
        foreach ($channel in $eventChannels) {
            foreach ($event in @(
                Get-WinEvent `
                    -LogName $channel `
                    -MaxEvents 50 `
                    -ErrorAction SilentlyContinue |
                    Where-Object {
                        $_.Id -in @(21, 22, 23, 24, 25, 39, 40, 1149)
                    }
            )) {
                $message = [string]$event.Message
                if ($message.Length -gt 2000) {
                    $message = $message.Substring(0, 2000)
                }
                $events += [ordered]@{
                    channel = $channel
                    time_utc = $event.TimeCreated.ToUniversalTime().ToString('o')
                    id = [int]$event.Id
                    level = $event.LevelDisplayName
                    message = $message
                }
            }
        }

        [ordered]@{
            computer_name = $env:COMPUTERNAME
            collected_as = [Security.Principal.WindowsIdentity]::GetCurrent().Name
            single_session_per_user = [bool](
                $terminalServer.fSingleSessionPerUser
            )
            deny_rdp_connections = [bool]$terminalServer.fDenyTSConnections
            session_lines = $sessionLines
            interactive_processes = @(
                $processes |
                    Sort-Object session_id, name, process_id
            )
            terminal_services_events = @(
                $events |
                    Sort-Object time_utc -Descending |
                    Select-Object -First 80
            )
        }
    }

    $result = [ordered]@{
        recorded_at = (Get-Date).ToUniversalTime().ToString('o')
        vm_name = $VmName
        state = 'complete'
        guest = $guest
    }
    $resultJson = $result | ConvertTo-Json -Depth 8
    $resultJson | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    $resultJson
}
catch {
    $result = [ordered]@{
        recorded_at = (Get-Date).ToUniversalTime().ToString('o')
        vm_name = $VmName
        state = 'unavailable'
        error = $_.Exception.Message
    }
    $resultJson = $result | ConvertTo-Json
    $resultJson | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    $resultJson
    throw
}
finally {
    if ($session) {
        Remove-PSSession -Session $session -ErrorAction SilentlyContinue
    }
}
