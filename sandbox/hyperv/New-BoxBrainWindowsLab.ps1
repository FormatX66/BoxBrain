[CmdletBinding()]
param(
    [string]$VmName = 'BoxBrain-Windows-Lab',
    [string]$LabRoot = 'C:\VMs\BoxBrain-Windows-Lab',
    [string]$IsoPath = 'C:\VMs\BoxBrain-Windows-Lab\media\Windows11EnterpriseEval-25H2-en-us.iso',
    [ValidatePattern('^[0-9A-Fa-f]{64}$')]
    [string]$ExpectedIsoSha256 = 'A61ADEAB895EF5A4DB436E0A7011C92A2FF17BB0357F58B13BBC4062E535E7B9',
    [string]$SwitchName = 'BoxBrain-Pi-USB',
    [string]$PiAdapterDescription = 'Raspberry Pi USB Remote NDIS Network Device',
    [ValidateRange(1, 16)]
    [int]$ProcessorCount = 2,
    [ValidateRange(1GB, 8GB)]
    [long]$StartupMemoryBytes = 2GB,
    [ValidateRange(512MB, 4GB)]
    [long]$MinimumMemoryBytes = 1GB,
    [ValidateRange(2GB, 12GB)]
    [long]$MaximumMemoryBytes = 4GB,
    [ValidateRange(40GB, 256GB)]
    [long]$VirtualDiskSizeBytes = 64GB
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run this script from an elevated Windows PowerShell session.'
    }
}

function Assert-SafeLabRoot {
    param([Parameter(Mandatory)][string]$Path)

    $fullPath = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    $volumeRoot = [IO.Path]::GetPathRoot($fullPath).TrimEnd('\')
    if ($fullPath -eq $volumeRoot -or $fullPath.Length -lt 10) {
        throw "Refusing unsafe lab root: $fullPath"
    }
    return $fullPath
}

Assert-Administrator
Import-Module Hyper-V -ErrorAction Stop

$LabRoot = Assert-SafeLabRoot -Path $LabRoot
$IsoPath = [IO.Path]::GetFullPath($IsoPath)
$expectedHash = $ExpectedIsoSha256.ToLowerInvariant()

if (-not (Test-Path -LiteralPath $IsoPath -PathType Leaf)) {
    throw "Windows installation media is missing: $IsoPath"
}

$actualHash = (Get-FileHash -LiteralPath $IsoPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -cne $expectedHash) {
    throw "Windows installation media hash mismatch. Expected $expectedHash; received $actualHash."
}

$existingVm = Get-VM -Name $VmName -ErrorAction SilentlyContinue
if ($null -ne $existingVm) {
    Write-Host "[ready] VM already exists; no changes made: $VmName"
    $existingVm | Select-Object Name, State, Generation, Path
    exit 0
}

$piAdapters = @(
    Get-NetAdapter -Physical |
        Where-Object {
            $_.InterfaceDescription -ceq $PiAdapterDescription -and
            $_.Status -eq 'Up'
        }
)
if ($piAdapters.Count -ne 1) {
    throw "Expected exactly one active Pi USB adapter named '$PiAdapterDescription'; found $($piAdapters.Count)."
}
$piAdapter = $piAdapters[0]

$switch = Get-VMSwitch -Name $SwitchName -ErrorAction SilentlyContinue
if ($null -eq $switch) {
    Write-Host "[network] Creating dedicated external switch on '$($piAdapter.Name)'."
    $switch = New-VMSwitch `
        -Name $SwitchName `
        -NetAdapterName $piAdapter.Name `
        -AllowManagementOS $true `
        -Notes 'Dedicated BoxBrain Raspberry Pi USB-C lab link'
} else {
    if ($switch.SwitchType -ne 'External') {
        throw "Existing switch '$SwitchName' is not external."
    }
    if ($switch.NetAdapterInterfaceDescription -cne $PiAdapterDescription) {
        throw "Existing switch '$SwitchName' is attached to a different adapter."
    }
}

$vmStorageRoot = Join-Path $LabRoot 'hyperv'
$vhdRoot = Join-Path $LabRoot 'disks'
$vhdPath = Join-Path $vhdRoot "$VmName.vhdx"
New-Item -ItemType Directory -Path $vmStorageRoot, $vhdRoot -Force | Out-Null

Write-Host "[vm] Creating powered-off Generation 2 lab VM."
$vm = New-VM `
    -Name $VmName `
    -Generation 2 `
    -MemoryStartupBytes $StartupMemoryBytes `
    -Path $vmStorageRoot `
    -NewVHDPath $vhdPath `
    -NewVHDSizeBytes $VirtualDiskSizeBytes `
    -SwitchName $SwitchName

Set-VMMemory `
    -VMName $VmName `
    -DynamicMemoryEnabled $true `
    -MinimumBytes $MinimumMemoryBytes `
    -StartupBytes $StartupMemoryBytes `
    -MaximumBytes $MaximumMemoryBytes
Set-VMProcessor -VMName $VmName -Count $ProcessorCount
Set-VM `
    -Name $VmName `
    -AutomaticStartAction Nothing `
    -AutomaticStopAction ShutDown `
    -AutomaticCheckpointsEnabled $false `
    -CheckpointType Standard `
    -Notes 'Disposable BoxBrain Windows target. No personal accounts, files, or credentials.'
Set-VMFirmware `
    -VMName $VmName `
    -EnableSecureBoot On `
    -SecureBootTemplate MicrosoftWindows
Set-VMKeyProtector -VMName $VmName -NewLocalKeyProtector
Enable-VMTPM -VMName $VmName

$dvd = Add-VMDvdDrive -VMName $VmName -Path $IsoPath -Passthru
Set-VMFirmware -VMName $VmName -FirstBootDevice $dvd

$summary = [ordered]@{
    vm_name = $VmName
    state = $vm.State.ToString()
    generation = $vm.Generation
    processors = $ProcessorCount
    memory_startup_bytes = $StartupMemoryBytes
    memory_minimum_bytes = $MinimumMemoryBytes
    memory_maximum_bytes = $MaximumMemoryBytes
    disk_path = $vhdPath
    disk_maximum_bytes = $VirtualDiskSizeBytes
    iso_path = $IsoPath
    iso_sha256 = $actualHash
    switch_name = $switch.Name
    switch_type = $switch.SwitchType.ToString()
    pi_adapter = $PiAdapterDescription
    secure_boot = $true
    virtual_tpm = $true
    automatic_checkpoints = $false
}

$summaryPath = Join-Path $LabRoot 'vm-definition.json'
$summary | ConvertTo-Json | Set-Content -LiteralPath $summaryPath -Encoding UTF8
$summary | ConvertTo-Json
Write-Host "[ready] VM created powered off. Definition: $summaryPath"
