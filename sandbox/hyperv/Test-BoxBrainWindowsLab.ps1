[CmdletBinding()]
param(
    [string]$VmName = 'BoxBrain-Windows-Lab',
    [string]$SwitchName = 'BoxBrain-Pi-USB',
    [string]$PiAdapterDescription = 'Raspberry Pi USB Remote NDIS Network Device',
    [string]$OutputPath = 'C:\VMs\BoxBrain-Windows-Lab\validation.json',
    [switch]$RequireAnswerMedia
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

trap {
    $failure = [ordered]@{
        checked_at = (Get-Date).ToUniversalTime().ToString('o')
        vm_name = $VmName
        error = $_.Exception.Message
    }
    $outputDirectory = Split-Path -Parent ([IO.Path]::GetFullPath($OutputPath))
    if (Test-Path -LiteralPath $outputDirectory -PathType Container) {
        $failure | ConvertTo-Json | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    }
    exit 1
}

Import-Module Hyper-V -ErrorAction Stop

$vm = Get-VM -Name $VmName -ErrorAction Stop
$switch = Get-VMSwitch -Name $SwitchName -ErrorAction Stop
$firmware = Get-VMFirmware -VMName $VmName
$security = Get-VMSecurity -VMName $VmName
$memory = Get-VMMemory -VMName $VmName
$processor = Get-VMProcessor -VMName $VmName
$network = Get-VMNetworkAdapter -VMName $VmName
$dvd = Get-VMDvdDrive -VMName $VmName
$disk = Get-VMHardDiskDrive -VMName $VmName
$windowsMedia = @(
    $dvd |
        Where-Object {
            -not [string]::IsNullOrWhiteSpace($_.Path) -and
            (Split-Path -Leaf $_.Path) -ceq 'Windows11EnterpriseEval-25H2-en-us.iso'
        }
)
$answerMedia = @(
    $dvd |
        Where-Object {
            -not [string]::IsNullOrWhiteSpace($_.Path) -and
            (Split-Path -Leaf $_.Path) -ceq 'BoxBrain-Autounattend.iso'
        }
)

$checks = [ordered]@{
    vm_exists = $null -ne $vm
    powered_off = $vm.State -eq 'Off'
    generation_2 = $vm.Generation -eq 2
    automatic_checkpoints_disabled = -not $vm.AutomaticCheckpointsEnabled
    standard_checkpoint_type = $vm.CheckpointType -eq 'Standard'
    dynamic_memory = $memory.DynamicMemoryEnabled
    processor_count = $processor.Count
    secure_boot = $firmware.SecureBoot -eq 'On'
    virtual_tpm = $security.TpmEnabled
    one_network_adapter = @($network).Count -eq 1
    expected_switch = @($network).Count -eq 1 -and $network.SwitchName -ceq $SwitchName
    external_switch = $switch.SwitchType -eq 'External'
    expected_pi_adapter = $switch.NetAdapterInterfaceDescription -ceq $PiAdapterDescription
    windows_installation_media_attached = $windowsMedia.Count -eq 1
    answer_media_attached_when_required = -not $RequireAnswerMedia -or $answerMedia.Count -eq 1
    no_unexpected_dvd_media = @($dvd).Count -eq ($windowsMedia.Count + $answerMedia.Count)
    one_virtual_disk = @($disk).Count -eq 1
}

$failed = @($checks.GetEnumerator() | Where-Object { -not $_.Value })
$validation = [ordered]@{
    checked_at = (Get-Date).ToUniversalTime().ToString('o')
    vm_name = $VmName
    checks = $checks
}
$validationJson = $validation | ConvertTo-Json -Depth 4
$validationJson
$outputDirectory = Split-Path -Parent ([IO.Path]::GetFullPath($OutputPath))
if (-not (Test-Path -LiteralPath $outputDirectory -PathType Container)) {
    throw "Validation output directory does not exist: $outputDirectory"
}
$validationJson | Set-Content -LiteralPath $OutputPath -Encoding UTF8
if ($failed.Count -gt 0) {
    throw "BoxBrain lab validation failed: $($failed.Name -join ', ')"
}

Write-Host '[ready] BoxBrain Hyper-V lab definition passed all checks.'
