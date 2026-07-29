[CmdletBinding()]
param(
    [string]$VmName = 'BoxBrain-Windows-Lab',
    [string]$LabRoot = 'C:\VMs\BoxBrain-Windows-Lab',
    [string]$WindowsIso = 'C:\VMs\BoxBrain-Windows-Lab\media\Windows11EnterpriseEval-25H2-en-us.iso',
    [string]$AnswerIso = 'C:\VMs\BoxBrain-Windows-Lab\media\BoxBrain-Autounattend.iso',
    [int]$ImageIndex = 1,
    [switch]$ResumePreparedDisk,
    [switch]$ResetPreparedDisk
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

$LabRoot = [IO.Path]::GetFullPath($LabRoot).TrimEnd('\')
$WindowsIso = [IO.Path]::GetFullPath($WindowsIso)
$AnswerIso = [IO.Path]::GetFullPath($AnswerIso)
$expectedVhd = Join-Path $LabRoot 'disks\BoxBrain-Windows-Lab.vhdx'
$statusPath = Join-Path $LabRoot 'offline-install-status.json'
$logPath = Join-Path $LabRoot 'logs\offline-install.log'

function Write-InstallStatus {
    param(
        [Parameter(Mandatory)][string]$Stage,
        [ValidateSet('running', 'complete', 'failed')][string]$State = 'running',
        [string]$Message = ''
    )

    [ordered]@{
        recorded_at = (Get-Date).ToUniversalTime().ToString('o')
        vm_name = $VmName
        state = $State
        stage = $Stage
        message = $Message
    } | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
}

function Mount-IsoForRead {
    param([Parameter(Mandatory)][string]$Path)

    $diskImage = Get-DiskImage -ImagePath $Path -ErrorAction SilentlyContinue
    $mountedHere = $false
    if (-not $diskImage -or -not $diskImage.Attached) {
        $diskImage = Mount-DiskImage -ImagePath $Path -PassThru
        $mountedHere = $true
    }

    $volume = $diskImage | Get-Volume | Where-Object DriveLetter | Select-Object -First 1
    if (-not $volume) {
        throw "Mounted ISO has no readable drive letter: $Path"
    }

    [pscustomobject]@{
        DiskImage = $diskImage
        DriveLetter = $volume.DriveLetter
        MountedHere = $mountedHere
    }
}

$mountedVhd = $false
$windowsMedia = $null
$answerMedia = $null
$currentStage = 'preflight'

Start-Transcript -LiteralPath $logPath -Append | Out-Null
try {
    Write-InstallStatus -Stage $currentStage -Message 'Validating the exact disposable VM and its blank virtual disk.'

    if (-not (Test-Path -LiteralPath $WindowsIso -PathType Leaf)) {
        throw "Windows ISO not found: $WindowsIso"
    }
    if (-not (Test-Path -LiteralPath $AnswerIso -PathType Leaf)) {
        throw "Answer ISO not found: $AnswerIso"
    }

    $vm = Get-VM -Name $VmName -ErrorAction Stop
    if ($vm.State -ne 'Off') {
        throw "VM must be off before offline installation; current state is $($vm.State)."
    }

    $hardDrives = @(Get-VMHardDiskDrive -VMName $VmName)
    if ($hardDrives.Count -ne 1) {
        throw "Expected exactly one VM hard disk; found $($hardDrives.Count)."
    }

    $vhdPath = [IO.Path]::GetFullPath($hardDrives[0].Path)
    if ($vhdPath -cne [IO.Path]::GetFullPath($expectedVhd)) {
        throw "Refusing unexpected VM disk path: $vhdPath"
    }
    if (-not (Test-Path -LiteralPath $vhdPath -PathType Leaf)) {
        throw "VM disk does not exist: $vhdPath"
    }

    $vhdInfo = Get-VHD -Path $vhdPath
    if ($vhdInfo.Attached) {
        throw 'VM disk is already attached outside this installer.'
    }
    if ($vhdInfo.Size -lt 60GB -or $vhdInfo.Size -gt 70GB) {
        throw "Refusing unexpected VM disk capacity: $($vhdInfo.Size) bytes."
    }

    $currentStage = 'mount-media'
    Write-InstallStatus -Stage $currentStage -Message 'Mounting verified Windows and BoxBrain answer media read-only.'
    $windowsMedia = Mount-IsoForRead -Path $WindowsIso
    $answerMedia = Mount-IsoForRead -Path $AnswerIso

    $installImage = "$($windowsMedia.DriveLetter):\sources\install.wim"
    $answerFile = "$($answerMedia.DriveLetter):\Autounattend.xml"
    if (-not (Test-Path -LiteralPath $installImage -PathType Leaf)) {
        throw "Windows image not found in the ISO: $installImage"
    }
    if (-not (Test-Path -LiteralPath $answerFile -PathType Leaf)) {
        throw "Autounattend.xml not found in the answer ISO: $answerFile"
    }

    $currentStage = 'prepare-virtual-disk'
    Write-InstallStatus -Stage $currentStage -Message 'Partitioning only the verified blank BoxBrain virtual disk.'
    $attachedVhd = Mount-VHD -Path $vhdPath -Passthru
    $mountedVhd = $true
    $diskNumber = $attachedVhd.DiskNumber
    if ($null -eq $diskNumber) {
        throw 'Hyper-V did not return a disk number for the mounted VHD.'
    }

    $disk = Get-Disk -Number $diskNumber
    $systemDisk = Get-Partition -DriveLetter $env:SystemDrive.TrimEnd(':') | Get-Disk
    if ($disk.Number -eq $systemDisk.Number -or $disk.IsBoot -or $disk.IsSystem) {
        throw "Safety stop: selected disk $diskNumber is a host boot or system disk."
    }
    if ([math]::Abs($disk.Size - $vhdInfo.Size) -gt 1MB) {
        throw 'Safety stop: mounted disk capacity does not match the verified VHD.'
    }

    if ($disk.PartitionStyle -eq 'RAW') {
        if (@(Get-Partition -DiskNumber $diskNumber -ErrorAction SilentlyContinue).Count -ne 0) {
            throw 'Safety stop: raw disposable VM disk unexpectedly contains partitions.'
        }

        Initialize-Disk -Number $diskNumber -PartitionStyle GPT -PassThru | Out-Null
        $efi = New-Partition -DiskNumber $diskNumber -Size 260MB `
            -GptType '{C12A7328-F81F-11D2-BA4B-00A0C93EC93B}' -AssignDriveLetter
        $efi | Format-Volume -FileSystem FAT32 -NewFileSystemLabel 'System' -Confirm:$false | Out-Null
        $windows = New-Partition -DiskNumber $diskNumber -UseMaximumSize `
            -GptType '{EBD0A0A2-B9E5-4433-87C0-68B6B72699C7}' -AssignDriveLetter
        $windows | Format-Volume -FileSystem NTFS -NewFileSystemLabel 'Windows' -Confirm:$false | Out-Null
    } elseif ($disk.PartitionStyle -eq 'GPT' -and $ResetPreparedDisk) {
        $partitions = @(Get-Partition -DiskNumber $diskNumber)
        $efiPartitions = @($partitions | Where-Object GptType -eq '{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}')
        $msrPartitions = @($partitions | Where-Object GptType -eq '{e3c9e316-0b5c-4db8-817d-f92df00215ae}')
        $windowsPartitions = @($partitions | Where-Object GptType -eq '{ebd0a0a2-b9e5-4433-87c0-68b6b72699c7}')
        if (
            $partitions.Count -ne 4 -or
            $efiPartitions.Count -ne 1 -or
            $msrPartitions.Count -ne 2 -or
            $windowsPartitions.Count -ne 1
        ) {
            throw 'Safety stop: VM disk does not match the known empty duplicate-MSR layout.'
        }
        $efiVolume = $efiPartitions[0] | Get-Volume
        $windowsVolume = $windowsPartitions[0] | Get-Volume
        if (
            $efiVolume.FileSystem -ne 'FAT32' -or $efiVolume.FileSystemLabel -ne 'System' -or
            $windowsVolume.FileSystem -ne 'NTFS' -or $windowsVolume.FileSystemLabel -ne 'Windows'
        ) {
            throw 'Safety stop: duplicate-MSR layout has unexpected volume formats or labels.'
        }
        if (Test-Path -LiteralPath "$($windowsPartitions[0].DriveLetter):\Windows") {
            throw 'Safety stop: duplicate-MSR Windows volume is no longer empty.'
        }

        Clear-Disk -Number $diskNumber -RemoveData -RemoveOEM -Confirm:$false
        Initialize-Disk -Number $diskNumber -PartitionStyle GPT -PassThru | Out-Null
        $efi = New-Partition -DiskNumber $diskNumber -Size 260MB `
            -GptType '{C12A7328-F81F-11D2-BA4B-00A0C93EC93B}' -AssignDriveLetter
        $efi | Format-Volume -FileSystem FAT32 -NewFileSystemLabel 'System' -Confirm:$false | Out-Null
        $windows = New-Partition -DiskNumber $diskNumber -UseMaximumSize `
            -GptType '{EBD0A0A2-B9E5-4433-87C0-68B6B72699C7}' -AssignDriveLetter
        $windows | Format-Volume -FileSystem NTFS -NewFileSystemLabel 'Windows' -Confirm:$false | Out-Null
    } elseif ($disk.PartitionStyle -eq 'GPT' -and $ResumePreparedDisk) {
        $partitions = @(Get-Partition -DiskNumber $diskNumber)
        $efi = @($partitions | Where-Object GptType -eq '{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}')
        $msr = @($partitions | Where-Object GptType -eq '{e3c9e316-0b5c-4db8-817d-f92df00215ae}')
        $windows = @($partitions | Where-Object GptType -eq '{ebd0a0a2-b9e5-4433-87c0-68b6b72699c7}')
        if ($partitions.Count -ne 3 -or $efi.Count -ne 1 -or $msr.Count -ne 1 -or $windows.Count -ne 1) {
            throw 'Safety stop: prepared VM disk does not have the exact BoxBrain EFI/MSR/Windows layout.'
        }
        $efi = $efi[0]
        $windows = $windows[0]
        if ($efi.Size -ne 260MB -or $msr[0].Size -lt 15MB -or $msr[0].Size -gt 17MB) {
            throw 'Safety stop: prepared VM boot partition sizes do not match the BoxBrain layout.'
        }
        $efiVolume = $efi | Get-Volume
        $windowsVolume = $windows | Get-Volume
        if (
            $efiVolume.FileSystem -ne 'FAT32' -or $efiVolume.FileSystemLabel -ne 'System' -or
            $windowsVolume.FileSystem -ne 'NTFS' -or $windowsVolume.FileSystemLabel -ne 'Windows'
        ) {
            throw 'Safety stop: prepared VM volume formats or labels do not match the BoxBrain layout.'
        }
        if (-not $efi.DriveLetter) {
            $efi | Add-PartitionAccessPath -AssignDriveLetter
        }
        if (-not $windows.DriveLetter) {
            $windows | Add-PartitionAccessPath -AssignDriveLetter
        }
        $efi = Get-Partition -DiskNumber $diskNumber -PartitionNumber $efi.PartitionNumber
        $windows = Get-Partition -DiskNumber $diskNumber -PartitionNumber $windows.PartitionNumber
        if (Test-Path -LiteralPath "$($windows.DriveLetter):\Windows") {
            throw 'Safety stop: prepared VM Windows volume is no longer empty.'
        }
    } else {
        throw "Safety stop: disposable VM disk is not blank (partition style $($disk.PartitionStyle))."
    }

    $efiLetter = (Get-Partition -DiskNumber $diskNumber -PartitionNumber $efi.PartitionNumber).DriveLetter
    $windowsLetter = (Get-Partition -DiskNumber $diskNumber -PartitionNumber $windows.PartitionNumber).DriveLetter
    if (-not $efiLetter -or -not $windowsLetter) {
        throw 'Required virtual-disk drive letters were not assigned.'
    }

    $currentStage = 'apply-windows'
    Write-InstallStatus -Stage $currentStage -Message 'Applying Windows 11 Enterprise Evaluation to the VM disk.'
    $windowsRoot = "$windowsLetter`:\"
    & "$env:SystemRoot\System32\dism.exe" `
        '/Apply-Image' `
        "/ImageFile:$installImage" `
        "/Index:$ImageIndex" `
        "/ApplyDir:$windowsRoot" `
        '/CheckIntegrity'
    if ($LASTEXITCODE -ne 0) {
        throw "DISM failed with exit code $LASTEXITCODE."
    }

    $currentStage = 'configure-first-boot'
    Write-InstallStatus -Stage $currentStage -Message 'Configuring UEFI boot and BoxBrain unattended first boot.'
    $efiRoot = "$efiLetter`:"
    & "$env:SystemRoot\System32\bcdboot.exe" "$windowsRoot`Windows" /s $efiRoot /f UEFI
    if ($LASTEXITCODE -ne 0) {
        throw "BCDBoot failed with exit code $LASTEXITCODE."
    }

    $panther = Join-Path $windowsRoot 'Windows\Panther'
    New-Item -ItemType Directory -Path $panther -Force | Out-Null
    Copy-Item -LiteralPath $answerFile -Destination (Join-Path $panther 'Unattend.xml') -Force

    $currentStage = 'finalize'
    Write-InstallStatus -Stage $currentStage -Message 'Finalizing the prepared Windows VM disk.'
} catch {
    Write-InstallStatus -Stage $currentStage -State failed -Message $_.Exception.Message
    throw
} finally {
    if ($mountedVhd) {
        Dismount-VHD -Path $vhdPath -ErrorAction Continue
    }
    if ($answerMedia -and $answerMedia.MountedHere) {
        Dismount-DiskImage -ImagePath $AnswerIso -ErrorAction Continue
    }
    if ($windowsMedia -and $windowsMedia.MountedHere) {
        Dismount-DiskImage -ImagePath $WindowsIso -ErrorAction Continue
    }
    Stop-Transcript -ErrorAction SilentlyContinue | Out-Null
}

$hardDrive = Get-VMHardDiskDrive -VMName $VmName
Set-VMFirmware -VMName $VmName -FirstBootDevice $hardDrive
Get-VMDvdDrive -VMName $VmName | Set-VMDvdDrive -Path $null

Write-InstallStatus -Stage 'ready-to-boot' -State complete `
    -Message 'Windows is applied, answer settings are staged, and the virtual disk is first in the boot order.'
Get-Content -LiteralPath $statusPath -Raw
