[CmdletBinding()]
param(
    [string]$VmName = 'BoxBrain-Windows-Lab',
    [string]$StatusPath = 'C:\VMs\BoxBrain-Windows-Lab\runtime-status.json',
    [string]$ErrorPath = 'C:\VMs\BoxBrain-Windows-Lab\logs\runtime-status-error.json'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

trap {
    [ordered]@{
        recorded_at = (Get-Date).ToUniversalTime().ToString('o')
        vm_name = $VmName
        error = $_.Exception.Message
        category = $_.CategoryInfo.Category.ToString()
        script_line = $_.InvocationInfo.ScriptLineNumber
    } | ConvertTo-Json | Set-Content -LiteralPath $ErrorPath -Encoding UTF8
    throw
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an elevated Windows PowerShell session.'
}

Import-Module Hyper-V -ErrorAction Stop

$vm = Get-VM -Name $VmName -ErrorAction Stop
$hardDrives = @(Get-VMHardDiskDrive -VMName $VmName)
$dvdDrives = @(Get-VMDvdDrive -VMName $VmName)
$networkAdapters = @(Get-VMNetworkAdapter -VMName $VmName)
$integrationServices = @(Get-VMIntegrationService -VMName $VmName)

$diskStatus = foreach ($drive in $hardDrives) {
    $file = if ($drive.Path -and (Test-Path -LiteralPath $drive.Path)) {
        Get-Item -LiteralPath $drive.Path
    } else {
        $null
    }

    [ordered]@{
        controller_type = $drive.ControllerType.ToString()
        controller_number = $drive.ControllerNumber
        controller_location = $drive.ControllerLocation
        path = $drive.Path
        exists = [bool]$file
        size_bytes = if ($file) { $file.Length } else { $null }
        last_write_utc = if ($file) { $file.LastWriteTimeUtc.ToString('o') } else { $null }
    }
}

$status = [ordered]@{
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
    vm_name = $VmName
    state = $vm.State.ToString()
    status = $vm.Status
    uptime_seconds = [math]::Floor($vm.Uptime.TotalSeconds)
    generation = $vm.Generation
    heartbeat = ($integrationServices | Where-Object Name -eq 'Heartbeat' | Select-Object -ExpandProperty PrimaryStatusDescription -First 1)
    disks = @($diskStatus)
    dvd_drives = @(
        $dvdDrives | ForEach-Object {
            [ordered]@{
                controller_number = $_.ControllerNumber
                controller_location = $_.ControllerLocation
                path = $_.Path
            }
        }
    )
    network_adapters = @(
        $networkAdapters | ForEach-Object {
            [ordered]@{
                name = $_.Name
                switch_name = $_.SwitchName
                status = if ($null -ne $_.Status) { $_.Status.ToString() } else { $null }
                ip_addresses = @($_.IPAddresses)
            }
        }
    )
}

$status | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $StatusPath -Encoding UTF8
$status | ConvertTo-Json -Depth 6
