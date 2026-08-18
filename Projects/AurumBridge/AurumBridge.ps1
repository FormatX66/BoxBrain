param(
    [Parameter(Mandatory = $true)]
    [string]$JobPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$AllowedActions = @(
    'bridge_health',
    'inventory',
    'seed_status',
    'docker_status',
    'process_snapshot',
    'network_snapshot',
    'storage_snapshot'
)

function Test-BridgeAdmin {
    try {
        $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
        return [bool]$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    }
    catch {
        return $false
    }
}

function Get-BridgeHealth {
    $os = Get-CimInstance Win32_OperatingSystem
    return [ordered]@{
        computer_name = $env:COMPUTERNAME
        user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        administrator = (Test-BridgeAdmin)
        runner_name = [string]$env:RUNNER_NAME
        runner_os = [string]$env:RUNNER_OS
        powershell = $PSVersionTable.PSVersion.ToString()
        os_caption = [string]$os.Caption
        os_version = [string]$os.Version
        boot_time = $os.LastBootUpTime.ToUniversalTime().ToString('o')
        observed_at = (Get-Date).ToUniversalTime().ToString('o')
    }
}

function Get-InventorySnapshot {
    $os = Get-CimInstance Win32_OperatingSystem
    $computer = Get-CimInstance Win32_ComputerSystem
    $disks = @(Get-Disk | Sort-Object Number | ForEach-Object {
        [ordered]@{
            number = [int]$_.Number
            friendly_name = [string]$_.FriendlyName
            serial = [string]$_.SerialNumber
            bus_type = [string]$_.BusType
            size_bytes = [int64]$_.Size
            is_boot = [bool]$_.IsBoot
            is_system = [bool]$_.IsSystem
            is_offline = [bool]$_.IsOffline
        }
    })
    $network = @(Get-NetAdapter -ErrorAction SilentlyContinue | Sort-Object Name | ForEach-Object {
        [ordered]@{
            name = [string]$_.Name
            description = [string]$_.InterfaceDescription
            status = [string]$_.Status
            mac_address = [string]$_.MacAddress
            link_speed = [string]$_.LinkSpeed
        }
    })
    return [ordered]@{
        computer = [ordered]@{
            name = [string]$computer.Name
            manufacturer = [string]$computer.Manufacturer
            model = [string]$computer.Model
            total_physical_memory = [int64]$computer.TotalPhysicalMemory
        }
        os = [ordered]@{
            caption = [string]$os.Caption
            version = [string]$os.Version
            build = [string]$os.BuildNumber
            architecture = [string]$os.OSArchitecture
        }
        disks = $disks
        network = $network
    }
}

function Get-SeedStatus {
    $aurumRoot = Join-Path $env:ProgramData 'Aurum'
    $sentinels = @()
    if (Test-Path -LiteralPath $aurumRoot) {
        $sentinels = @(Get-ChildItem -LiteralPath $aurumRoot -File -Filter 'pc01-flash-*.done' -ErrorAction SilentlyContinue | Sort-Object LastWriteTimeUtc -Descending | ForEach-Object {
            [ordered]@{
                name = $_.Name
                modified_utc = $_.LastWriteTimeUtc.ToString('o')
                size_bytes = [int64]$_.Length
            }
        })
    }
    $usb = @(Get-Disk | Where-Object { $_.BusType -eq 'USB' } | Sort-Object Number | ForEach-Object {
        [ordered]@{
            number = [int]$_.Number
            friendly_name = [string]$_.FriendlyName
            serial = [string]$_.SerialNumber
            size_bytes = [int64]$_.Size
            is_boot = [bool]$_.IsBoot
            is_system = [bool]$_.IsSystem
            is_offline = [bool]$_.IsOffline
        }
    })
    return [ordered]@{
        flash_sentinels = $sentinels
        usb_disks = $usb
        sentinel_root_exists = (Test-Path -LiteralPath $aurumRoot)
    }
}

function Get-DockerStatus {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) {
        return [ordered]@{ available = $false }
    }
    $version = $null
    $containers = @()
    try {
        $version = (& docker version --format '{{.Server.Version}}' 2>$null | Select-Object -First 1)
        $containers = @(& docker ps --format '{{.ID}}|{{.Image}}|{{.Names}}|{{.Status}}' 2>$null | ForEach-Object {
            $parts = [string]$_ -split '\|', 4
            [ordered]@{
                id = if ($parts.Count -gt 0) { $parts[0] } else { '' }
                image = if ($parts.Count -gt 1) { $parts[1] } else { '' }
                name = if ($parts.Count -gt 2) { $parts[2] } else { '' }
                status = if ($parts.Count -gt 3) { $parts[3] } else { '' }
            }
        })
        return [ordered]@{
            available = $true
            server_version = [string]$version
            containers = $containers
        }
    }
    catch {
        return [ordered]@{
            available = $true
            reachable = $false
            error = $_.Exception.Message
        }
    }
}

function Get-ProcessSnapshot {
    return @(Get-Process | Sort-Object CPU -Descending | Select-Object -First 25 | ForEach-Object {
        [ordered]@{
            id = [int]$_.Id
            name = [string]$_.ProcessName
            cpu_seconds = if ($null -ne $_.CPU) { [double]$_.CPU } else { 0.0 }
            working_set_bytes = [int64]$_.WorkingSet64
        }
    })
}

function Get-NetworkSnapshot {
    $adapters = @(Get-NetAdapter -ErrorAction SilentlyContinue | Sort-Object Name | ForEach-Object {
        [ordered]@{
            name = [string]$_.Name
            description = [string]$_.InterfaceDescription
            status = [string]$_.Status
            mac_address = [string]$_.MacAddress
            link_speed = [string]$_.LinkSpeed
        }
    })
    $addresses = @(Get-NetIPAddress -ErrorAction SilentlyContinue | Where-Object { $_.AddressFamily -in @('IPv4', 'IPv6') } | Sort-Object InterfaceAlias, AddressFamily | ForEach-Object {
        [ordered]@{
            interface = [string]$_.InterfaceAlias
            family = [string]$_.AddressFamily
            address = [string]$_.IPAddress
            prefix_length = [int]$_.PrefixLength
        }
    })
    return [ordered]@{
        adapters = $adapters
        addresses = $addresses
    }
}

function Get-StorageSnapshot {
    return @(Get-Disk | Sort-Object Number | ForEach-Object {
        $partitions = @(Get-Partition -DiskNumber $_.Number -ErrorAction SilentlyContinue | Sort-Object PartitionNumber | ForEach-Object {
            [ordered]@{
                partition_number = [int]$_.PartitionNumber
                drive_letter = if ($_.DriveLetter) { [string]$_.DriveLetter } else { $null }
                size_bytes = [int64]$_.Size
                type = [string]$_.Type
            }
        })
        [ordered]@{
            number = [int]$_.Number
            friendly_name = [string]$_.FriendlyName
            serial = [string]$_.SerialNumber
            bus_type = [string]$_.BusType
            size_bytes = [int64]$_.Size
            is_boot = [bool]$_.IsBoot
            is_system = [bool]$_.IsSystem
            partitions = $partitions
        }
    })
}

$started = (Get-Date).ToUniversalTime()
$result = [ordered]@{
    schema = 'aurum-pc-bridge-result-v1'
    job_id = $null
    action = $null
    status = 'error'
    host = $env:COMPUTERNAME
    started_at = $started.ToString('o')
    finished_at = $null
    data = $null
    error = $null
}

try {
    $job = Get-Content -LiteralPath $JobPath -Raw | ConvertFrom-Json
    if ([string]$job.schema -ne 'aurum-pc-bridge-job-v1') {
        throw 'invalid job schema'
    }
    $jobId = [string]$job.id
    if ($jobId -notmatch '^[A-Za-z0-9._-]{1,80}$') {
        throw 'invalid job id'
    }
    $action = [string]$job.action
    if ($AllowedActions -notcontains $action) {
        throw "action not allowed: $action"
    }

    foreach ($forbidden in @('command', 'script', 'shell', 'powershell', 'raw_command')) {
        if ($job.PSObject.Properties.Name -contains $forbidden) {
            throw "forbidden free-form execution field: $forbidden"
        }
    }

    $result.job_id = $jobId
    $result.action = $action

    $processedRoot = Join-Path (Join-Path $env:ProgramData 'Aurum') 'Bridge\processed'
    New-Item -ItemType Directory -Path $processedRoot -Force | Out-Null
    $sentinel = Join-Path $processedRoot "$jobId.json"
    if (Test-Path -LiteralPath $sentinel) {
        $previous = Get-Content -LiteralPath $sentinel -Raw | ConvertFrom-Json
        $previous | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
        Write-Host "AURUM_PC_BRIDGE_REPLAY job=$jobId action=$action status=returned-cached-evidence"
        exit 0
    }

    switch ($action) {
        'bridge_health' { $data = Get-BridgeHealth }
        'inventory' { $data = Get-InventorySnapshot }
        'seed_status' { $data = Get-SeedStatus }
        'docker_status' { $data = Get-DockerStatus }
        'process_snapshot' { $data = Get-ProcessSnapshot }
        'network_snapshot' { $data = Get-NetworkSnapshot }
        'storage_snapshot' { $data = Get-StorageSnapshot }
        default { throw "unreachable action: $action" }
    }

    $result.status = 'ok'
    $result.data = $data
    $result.finished_at = (Get-Date).ToUniversalTime().ToString('o')

    $outDir = Split-Path -Parent $OutputPath
    if ($outDir) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
    $json = $result | ConvertTo-Json -Depth 12
    $json | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    $json | Set-Content -LiteralPath $sentinel -Encoding UTF8
    Write-Host "AURUM_PC_BRIDGE_OK job=$jobId action=$action host=$env:COMPUTERNAME"
}
catch {
    $result.finished_at = (Get-Date).ToUniversalTime().ToString('o')
    $result.error = [ordered]@{
        type = $_.Exception.GetType().FullName
        message = $_.Exception.Message
    }
    $outDir = Split-Path -Parent $OutputPath
    if ($outDir) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
    $result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    Write-Error "AURUM_PC_BRIDGE_ERROR $($_.Exception.Message)"
    exit 1
}
