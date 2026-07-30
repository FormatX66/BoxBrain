[CmdletBinding()]
param(
    [string]$VmName = 'BoxBrain-Windows-Lab',
    [string]$StatusPath = 'C:\VMs\BoxBrain-Windows-Lab\disk-layout.json'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an elevated Windows PowerShell session.'
}

Import-Module Hyper-V -ErrorAction Stop
Import-Module Storage -ErrorAction Stop

$vm = Get-VM -Name $VmName -ErrorAction Stop
if ($vm.State -ne 'Off') {
    throw "VM must be off to inspect its disk; current state is $($vm.State)."
}

$hardDrives = @(Get-VMHardDiskDrive -VMName $VmName)
if ($hardDrives.Count -ne 1) {
    throw "Expected exactly one VM hard disk; found $($hardDrives.Count)."
}

$vhdPath = [IO.Path]::GetFullPath($hardDrives[0].Path)
$mounted = $false
try {
    $attached = Mount-VHD -Path $vhdPath -ReadOnly -Passthru
    $mounted = $true
    $disk = Get-Disk -Number $attached.DiskNumber
    $partitions = @(Get-Partition -DiskNumber $disk.Number)

    $result = [ordered]@{
        recorded_at = (Get-Date).ToUniversalTime().ToString('o')
        vm_name = $VmName
        vhd_path = $vhdPath
        disk_number = $disk.Number
        disk_size = $disk.Size
        partition_style = $disk.PartitionStyle.ToString()
        is_boot = $disk.IsBoot
        is_system = $disk.IsSystem
        partitions = @(
            $partitions | ForEach-Object {
                $volume = $_ | Get-Volume -ErrorAction SilentlyContinue
                [ordered]@{
                    number = $_.PartitionNumber
                    size = $_.Size
                    type = $_.Type.ToString()
                    gpt_type = $_.GptType
                    drive_letter = $_.DriveLetter
                    file_system = if ($volume) { $volume.FileSystem } else { $null }
                    label = if ($volume) { $volume.FileSystemLabel } else { $null }
                }
            }
        )
    }
    $result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $StatusPath -Encoding UTF8
    $result | ConvertTo-Json -Depth 6
} finally {
    if ($mounted) {
        Dismount-VHD -Path $vhdPath -ErrorAction Continue
    }
}
