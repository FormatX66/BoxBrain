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
    'storage_snapshot',
    'wiz_light_off',
    'wiz_scan',
    'wiz_light_off_unique_on',
    'wiz_room_identify_start',
    'wiz_room_identify_restore',
    'wiz_room_identify_all_off'
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

function Invoke-WizUdpJson {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Payload,

        [string]$Target = '192.168.0.14'
    )

    $target = $Target
    $port = 38899
    $client = [System.Net.Sockets.UdpClient]::new()
    try {
        $client.Client.ReceiveTimeout = 1800
        $client.Connect($target, $port)
        $bytes = [Text.Encoding]::UTF8.GetBytes($Payload)
        [void]$client.Send($bytes, $bytes.Length)
        $remote = [System.Net.IPEndPoint]::new([System.Net.IPAddress]::Any, 0)
        $responseBytes = $client.Receive([ref]$remote)
        $raw = [Text.Encoding]::UTF8.GetString($responseBytes)
        return ($raw | ConvertFrom-Json)
    }
    finally {
        $client.Dispose()
    }
}

function Invoke-WizLightOff {
    $target = '192.168.0.14'
    $system = Invoke-WizUdpJson -Payload '{"method":"getSystemConfig","params":{}}'
    if ($null -eq $system.result) { throw 'WIZ_TARGET_REFUSED reason=missing-system-config' }

    $module = [string]$system.result.moduleName
    if ($module -ne 'ESP24_SHRGB_01') {
        throw "WIZ_TARGET_REFUSED reason=unexpected-module actual=$module"
    }

    $before = Invoke-WizUdpJson -Payload '{"method":"getPilot","params":{}}'
    if ($null -eq $before.result -or -not ($before.result.PSObject.Properties.Name -contains 'state')) {
        throw 'WIZ_TARGET_REFUSED reason=missing-before-state'
    }

    $setResult = Invoke-WizUdpJson -Payload '{"method":"setPilot","params":{"state":false}}'
    Start-Sleep -Milliseconds 250
    $after = Invoke-WizUdpJson -Payload '{"method":"getPilot","params":{}}'
    if ($null -eq $after.result -or -not ($after.result.PSObject.Properties.Name -contains 'state')) {
        throw 'WIZ_VERIFY_FAILED reason=missing-after-state'
    }
    if ([bool]$after.result.state) {
        throw 'WIZ_VERIFY_FAILED reason=state-still-on'
    }

    return [ordered]@{
        target = $target
        module = $module
        firmware = [string]$system.result.fwVersion
        before_state = [bool]$before.result.state
        after_state = [bool]$after.result.state
        verified_off = $true
        observed_at = (Get-Date).ToUniversalTime().ToString('o')
    }
}

function Get-WizLanScan {
    $port = 38899
    $systems = @{}
    $client = [System.Net.Sockets.UdpClient]::new()
    try {
        $client.EnableBroadcast = $true
        $client.Client.ReceiveTimeout = 300
        $payload = [Text.Encoding]::UTF8.GetBytes('{"method":"getSystemConfig","params":{}}')
        foreach ($address in @('255.255.255.255', '192.168.0.255')) {
            $endpoint = [System.Net.IPEndPoint]::new([System.Net.IPAddress]::Parse($address), $port)
            [void]$client.Send($payload, $payload.Length, $endpoint)
        }

        $deadline = (Get-Date).AddMilliseconds(1800)
        while ((Get-Date) -lt $deadline) {
            try {
                $remote = [System.Net.IPEndPoint]::new([System.Net.IPAddress]::Any, 0)
                $bytes = $client.Receive([ref]$remote)
                $raw = [Text.Encoding]::UTF8.GetString($bytes)
                $obj = $raw | ConvertFrom-Json
                if ($null -ne $obj.result -and ($obj.result.PSObject.Properties.Name -contains 'moduleName')) {
                    $systems[$remote.Address.ToString()] = $obj.result
                }
            } catch [System.Net.Sockets.SocketException] {
                # Short receive timeout is expected while collecting broadcast responses.
            }
        }
    }
    finally {
        $client.Dispose()
    }

    $devices = @()
    foreach ($ip in @($systems.Keys | Sort-Object)) {
        $system = $systems[$ip]
        $pilot = $null
        $pilotError = $null
        try {
            $pilot = Invoke-WizUdpJson -Target $ip -Payload '{"method":"getPilot","params":{}}'
        } catch {
            $pilotError = $_.Exception.Message
        }
        $state = $null
        if ($null -ne $pilot -and $null -ne $pilot.result -and ($pilot.result.PSObject.Properties.Name -contains 'state')) {
            $state = [bool]$pilot.result.state
        }
        $devices += [ordered]@{
            ip = $ip
            mac = [string]$system.mac
            module = [string]$system.moduleName
            firmware = [string]$system.fwVersion
            room_id = if ($system.PSObject.Properties.Name -contains 'roomId') { [string]$system.roomId } else { $null }
            home_id = if ($system.PSObject.Properties.Name -contains 'homeId') { [string]$system.homeId } else { $null }
            state = $state
            dimming = if ($null -ne $pilot -and $null -ne $pilot.result -and ($pilot.result.PSObject.Properties.Name -contains 'dimming')) { [int]$pilot.result.dimming } else { $null }
            rssi = if ($null -ne $pilot -and $null -ne $pilot.result -and ($pilot.result.PSObject.Properties.Name -contains 'rssi')) { [int]$pilot.result.rssi } else { $null }
            pilot_error = $pilotError
        }
    }

    return [ordered]@{
        discovered_count = $devices.Count
        devices = $devices
        observed_at = (Get-Date).ToUniversalTime().ToString('o')
    }
}

function Invoke-WizUniqueActiveLightOff {
    $scan = Get-WizLanScan
    $active = @($scan.devices | Where-Object { $_.state -eq $true })
    if ($active.Count -ne 1) {
        throw "WIZ_UNIQUE_ACTIVE_REFUSED active_count=$($active.Count)"
    }

    $target = [string]$active[0].ip
    $module = [string]$active[0].module
    $beforeState = [bool]$active[0].state

    [void](Invoke-WizUdpJson -Target $target -Payload '{"method":"setPilot","params":{"state":false}}')
    Start-Sleep -Milliseconds 250
    $after = Invoke-WizUdpJson -Target $target -Payload '{"method":"getPilot","params":{}}'
    if ($null -eq $after.result -or -not ($after.result.PSObject.Properties.Name -contains 'state')) {
        throw 'WIZ_VERIFY_FAILED reason=missing-after-state'
    }
    if ([bool]$after.result.state) {
        throw 'WIZ_VERIFY_FAILED reason=state-still-on'
    }

    return [ordered]@{
        target = $target
        module = $module
        before_state = $beforeState
        after_state = [bool]$after.result.state
        verified_off = $true
        unique_active_count = $active.Count
        observed_at = (Get-Date).ToUniversalTime().ToString('o')
    }
}

function ConvertTo-WizWritablePilot {
    param([object]$Pilot)
    $out = [ordered]@{}
    foreach ($name in @('state','dimming','r','g','b','c','w','temp','sceneId','speed')) {
        if ($null -ne $Pilot -and $Pilot.PSObject.Properties.Name -contains $name) {
            $out[$name] = $Pilot.$name
        }
    }
    return $out
}

function Start-WizRoomIdentification {
    $snapshotRoot = Join-Path $env:ProgramData 'Aurum\SmartHome'
    New-Item -ItemType Directory -Path $snapshotRoot -Force | Out-Null
    $snapshotPath = Join-Path $snapshotRoot 'wiz-room-identify-snapshot.json'

    $markers = @(
        [ordered]@{ room_id='33767514'; ip='192.168.0.139'; marker='red'; payload='{"method":"setPilot","params":{"state":true,"dimming":40,"r":255,"g":0,"b":0}}' },
        [ordered]@{ room_id='9636136'; ip='192.168.0.14'; marker='green'; payload='{"method":"setPilot","params":{"state":true,"dimming":40,"r":0,"g":255,"b":0}}' },
        [ordered]@{ room_id='8855599'; ip='192.168.0.177'; marker='blue'; payload='{"method":"setPilot","params":{"state":true,"dimming":40,"r":0,"g":0,"b":255}}' },
        [ordered]@{ room_id='291528'; ip='192.168.0.217'; marker='dim-white'; payload='{"method":"setPilot","params":{"state":true,"dimming":10}}' }
    )

    $snapshots = @()
    foreach ($m in $markers) {
        $before = Invoke-WizUdpJson -Target $m.ip -Payload '{"method":"getPilot","params":{}}'
        if ($null -eq $before.result) { throw "WIZ_IDENTIFY_REFUSED ip=$($m.ip) reason=no-before-state" }
        $snapshots += [ordered]@{
            room_id = $m.room_id
            ip = $m.ip
            marker = $m.marker
            restore_params = ConvertTo-WizWritablePilot -Pilot $before.result
        }
    }

    [ordered]@{
        schema='aurum.wiz-room-identify-snapshot.v1'
        created_at=(Get-Date).ToUniversalTime().ToString('o')
        devices=$snapshots
    } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $snapshotPath -Encoding UTF8

    $applied = @()
    foreach ($m in $markers) {
        [void](Invoke-WizUdpJson -Target $m.ip -Payload $m.payload)
        Start-Sleep -Milliseconds 120
        $after = Invoke-WizUdpJson -Target $m.ip -Payload '{"method":"getPilot","params":{}}'
        $applied += [ordered]@{
            room_id=$m.room_id
            ip=$m.ip
            marker=$m.marker
            state=if ($null -ne $after.result) { [bool]$after.result.state } else { $null }
            dimming=if ($null -ne $after.result -and $after.result.PSObject.Properties.Name -contains 'dimming') { [int]$after.result.dimming } else { $null }
        }
    }

    return [ordered]@{
        snapshot_path=$snapshotPath
        markers=$applied
        observed_at=(Get-Date).ToUniversalTime().ToString('o')
    }
}

function Restore-WizRoomIdentification {
    $snapshotPath = Join-Path (Join-Path $env:ProgramData 'Aurum\SmartHome') 'wiz-room-identify-snapshot.json'
    if (-not (Test-Path -LiteralPath $snapshotPath -PathType Leaf)) {
        throw 'WIZ_IDENTIFY_RESTORE_REFUSED reason=snapshot-missing'
    }
    $snapshot = Get-Content -LiteralPath $snapshotPath -Raw | ConvertFrom-Json
    if ([string]$snapshot.schema -ne 'aurum.wiz-room-identify-snapshot.v1') {
        throw 'WIZ_IDENTIFY_RESTORE_REFUSED reason=snapshot-schema'
    }

    $restored = @()
    foreach ($d in @($snapshot.devices)) {
        $paramsJson = ($d.restore_params | ConvertTo-Json -Compress -Depth 5)
        $payload = '{"method":"setPilot","params":' + $paramsJson + '}'
        [void](Invoke-WizUdpJson -Target ([string]$d.ip) -Payload $payload)
        Start-Sleep -Milliseconds 120
        $after = Invoke-WizUdpJson -Target ([string]$d.ip) -Payload '{"method":"getPilot","params":{}}'
        $restored += [ordered]@{
            room_id=[string]$d.room_id
            ip=[string]$d.ip
            state=if ($null -ne $after.result) { [bool]$after.result.state } else { $null }
            dimming=if ($null -ne $after.result -and $after.result.PSObject.Properties.Name -contains 'dimming') { [int]$after.result.dimming } else { $null }
        }
    }
    Remove-Item -LiteralPath $snapshotPath -Force -ErrorAction SilentlyContinue
    return [ordered]@{
        restored=$restored
        snapshot_removed=(-not (Test-Path -LiteralPath $snapshotPath))
        observed_at=(Get-Date).ToUniversalTime().ToString('o')
    }
}

function Invoke-WizRoomIdentifyAllOff {
    $targets = @('192.168.0.139','192.168.0.14','192.168.0.177','192.168.0.217')
    $results = @()
    foreach ($ip in $targets) {
        [void](Invoke-WizUdpJson -Target $ip -Payload '{"method":"setPilot","params":{"state":false}}')
        Start-Sleep -Milliseconds 100
        $after = Invoke-WizUdpJson -Target $ip -Payload '{"method":"getPilot","params":{}}'
        $state = if ($null -ne $after.result -and $after.result.PSObject.Properties.Name -contains 'state') { [bool]$after.result.state } else { $null }
        if ($state -ne $false) { throw "WIZ_IDENTIFY_ALL_OFF_VERIFY_FAILED ip=$ip state=$state" }
        $results += [ordered]@{ ip=$ip; verified_off=$true }
    }
    return [ordered]@{
        targets=$results
        observed_at=(Get-Date).ToUniversalTime().ToString('o')
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
        'wiz_light_off' { $data = Invoke-WizLightOff }
        'wiz_scan' { $data = Get-WizLanScan }
        'wiz_light_off_unique_on' { $data = Invoke-WizUniqueActiveLightOff }
        'wiz_room_identify_start' { $data = Start-WizRoomIdentification }
        'wiz_room_identify_restore' { $data = Restore-WizRoomIdentification }
        'wiz_room_identify_all_off' { $data = Invoke-WizRoomIdentifyAllOff }
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
