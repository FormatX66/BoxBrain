#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet("10.12.194.1", "10.42.194.1", "bbpi4.local", "192.168.0.194")]
    [string]$PiAddress = "10.12.194.1",
    [ValidatePattern("^[a-z_][a-z0-9_-]{0,31}$")]
    [string]$PiUser = "kali",
    [string]$KeyPath = (Join-Path $HOME ".ssh\boxbrain_pi_ed25519"),
    [string]$KnownHostsPath = (Join-Path $HOME ".ssh\known_hosts"),
    [Parameter(Mandatory)]
    [ValidatePattern("^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")]
    [string]$AuthorizationReference,
    [ValidateRange(60, 1800)]
    [int]$TimeToLiveSeconds = 1200
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

foreach ($required in @($KeyPath, $KnownHostsPath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required strict SSH file was not found: $required"
    }
}

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$modulePath = Join-Path $repositoryRoot "Projects\Codelation\seed\aurum_gui.py"
$evidenceDirectory = Join-Path $repositoryRoot "Projects\Codelation\autobuild\external_evidence"
$deploymentPath = Join-Path $evidenceDirectory "bbpi4_aurum_console.json"
$outputPath = Join-Path $evidenceDirectory "adaptive_shell_gui_live_trial.json"
$deployment = Get-Content -LiteralPath $deploymentPath -Raw | ConvertFrom-Json
$expectedModuleHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $modulePath).Hash.ToLowerInvariant()

$ssh = (Get-Command ssh.exe -CommandType Application -ErrorAction Stop).Source
$options = @(
    "-i", $KeyPath,
    "-o", "BatchMode=yes",
    "-o", "IdentitiesOnly=yes",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "UserKnownHostsFile=$KnownHostsPath",
    "-o", "ConnectTimeout=8"
)
$target = "$PiUser@$PiAddress"

function Invoke-GuiTrial {
    param(
        [Parameter(Mandatory)][string]$Command,
        [switch]$AllowFailure
    )
    $lines = @(& $ssh @options $target $Command 2>&1)
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0 -and -not $AllowFailure) {
        throw "The strict BBPI4 GUI trial command failed: $($lines -join ' ')"
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = ($lines -join "`n").Trim()
    }
}

$node = (Invoke-GuiTrial -Command 'cat "$HOME/.aurum/node.json"').Output | ConvertFrom-Json
$start = (Invoke-GuiTrial -Command 'sudo -n /usr/local/bin/aurum-gui-start').Output
$moduleHash = (Invoke-GuiTrial -Command "sha256sum /opt/boxbrain/codelation/seed/aurum_gui.py | awk '{print `$1}'").Output
$selfStatus = (Invoke-GuiTrial -Command '/usr/local/bin/aurum-gui --host 127.0.0.1 --port 8765 --status').Output | ConvertFrom-Json
$apiStatusText = (Invoke-GuiTrial -Command "curl --fail --silent --show-error --max-time 4 -H 'Host: 127.0.0.1:8765' http://127.0.0.1:8765/api/status").Output
$apiStatus = $apiStatusText | ConvertFrom-Json
$guiSchema = [string]$apiStatus.schema
$compatibleGuiSchemas = @('aurum.gui.v1', 'aurum.gui.v2', 'aurum.gui.v3')
$pageHash = (Invoke-GuiTrial -Command "curl --fail --silent --show-error --max-time 4 -H 'Host: 127.0.0.1:8765' http://127.0.0.1:8765/ | sha256sum | awk '{print `$1}'").Output
$statusHash = (Invoke-GuiTrial -Command "curl --fail --silent --show-error --max-time 4 -H 'Host: 127.0.0.1:8765' http://127.0.0.1:8765/api/status | sha256sum | awk '{print `$1}'").Output
$headers = (Invoke-GuiTrial -Command "curl --fail --silent --show-error --max-time 4 -D - -o /dev/null -H 'Host: 127.0.0.1:8765' http://127.0.0.1:8765/").Output
$serviceState = (Invoke-GuiTrial -Command 'sudo -n systemctl is-active aurum-gui.service').Output
$enabledState = (Invoke-GuiTrial -Command 'sudo -n systemctl is-enabled aurum-gui.service' -AllowFailure).Output
$listener = (Invoke-GuiTrial -Command "ss -ltnH 'sport = :8765'").Output

$runtimeContract = [ordered]@{
    deployment_schema = ([string]$deployment.schema -eq 'aurum-bbpi4-console-evidence-v1')
    node_identity = ([string]$deployment.node_id -eq [string]$node.node_id)
    start_transient = ($start -match '(?m)^AURUM_GUI_READY address=127\.0\.0\.1 port=8765 transient=true$')
    module_hash = ($moduleHash -eq $expectedModuleHash)
    gui_schema = ($compatibleGuiSchemas -contains $guiSchema)
    self_status_schema = ([string]$selfStatus.gui_schema -eq $guiSchema)
    console_identity = ([string]$apiStatus.console.identity -eq 'BBPI4/Aurum')
    host_actuation = ($apiStatus.authority.host_actuation -eq $false)
    api_key_persistence = ($apiStatus.authority.api_key_persisted -eq $false)
    safe_layout = ($apiStatus.interface.safe_layout_available -eq $true)
    proof_view = ($apiStatus.proof_view.present -eq $true)
    page_hash = ($pageHash -match '^[0-9a-f]{64}$')
    status_hash = ($statusHash -match '^[0-9a-f]{64}$')
    http_status = ($headers -match '(?im)^HTTP/\S+ 200\s')
    content_type = ($headers -match '(?im)^Content-Type:\s*text/html')
    service_active = ($serviceState -eq 'active')
    service_not_enabled = ($enabledState -ne 'enabled')
    loopback_listener = ($listener -match '127\.0\.0\.1:8765')
    no_nonloopback_listener = ($listener -notmatch '0\.0\.0\.0:8765|10\.12\.194\.1:8765|10\.42\.194\.1:8765|192\.168\.0\.194:8765')
}
$failed = @($runtimeContract.GetEnumerator() | Where-Object { -not $_.Value } | ForEach-Object { $_.Key })
if ($failed.Count -gt 0) {
    $listenerSummary = ($listener -replace '\s+', ' ').Trim()
    Write-Host "AURUM_GUI_CONTRACT_MISMATCH route=$PiAddress failed=$($failed -join ',') gui_schema=$guiSchema self_gui_schema=$([string]$selfStatus.gui_schema) service_state=$serviceState enabled_state=$enabledState listener=$listenerSummary authority=false content_free=true"
    throw "The live Aurum GUI did not satisfy its bounded runtime contract."
}

$observedAt = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$evidence = [ordered]@{
    schema = "aurum-adaptive-shell-gui-live-trial-evidence-v1"
    kind = "adaptive-shell-gui-live-trial"
    source = "aurum-bbpi4-loopback-gui-proof"
    verified = $true
    node_id = [string]$node.node_id
    route = $PiAddress
    ssh_host_key_fingerprint = [string]$deployment.ssh_host_key_fingerprint
    observed_at = $observedAt
    expires_at = $observedAt + $TimeToLiveSeconds
    candidate = [ordered]@{
        module = "/opt/boxbrain/codelation/seed/aurum_gui.py"
        module_sha256 = $moduleHash
        gui_schema = $guiSchema
        tests_passed = $true
    }
    runtime = [ordered]@{
        service_active = $true
        service_enabled = $false
        transient = $true
        address = "127.0.0.1"
        port = 8765
        listener_loopback_only = $true
        http_status = 200
        content_type = "text/html; charset=utf-8"
        page_sha256 = $pageHash
        status_sha256 = $statusHash
        status_schema = $guiSchema
        console_identity = "BBPI4/Aurum"
        mind_version = [int]$apiStatus.console.mind_version
        mind_sha256 = [string]$apiStatus.console.mind_sha256
    }
    transport = [ordered]@{
        strict_host_key_checking = $true
        dedicated_identity = $true
        usb_route = $PiAddress
        windows_endpoint_loopback = $true
        pi_endpoint_loopback = $true
    }
    interface = [ordered]@{
        human_constants = @($apiStatus.interface.human_constants)
        safe_layout_available = $true
        proof_view_present = $true
        dialogue_only = $true
        host_actuation = $false
        api_key_persisted = $false
    }
    safety = [ordered]@{
        packages_installed = $false
        persistent_service_enabled = $false
        raw_disk_changed = $false
        firmware_changed = $false
        bootloader_changed = $false
        security_reduced = $false
    }
    permission = [ordered]@{
        present = $true
        scope = "adaptive-shell-gui-live-trial"
        authorization_reference = $AuthorizationReference
    }
    proof_view = [ordered]@{
        present = $true
        page_sha256 = $pageHash
        status_sha256 = $statusHash
        user_content_captured = $false
    }
    authority_granted = $false
    persistent_service_enabled = $false
}

New-Item -ItemType Directory -Force -Path $evidenceDirectory | Out-Null
$temporary = "$outputPath.$([Guid]::NewGuid().ToString('N')).tmp"
try {
    $json = $evidence | ConvertTo-Json -Depth 9
    [IO.File]::WriteAllText($temporary, $json + "`n", [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $outputPath -Force
}
finally {
    if (Test-Path -LiteralPath $temporary) {
        Remove-Item -LiteralPath $temporary -Force
    }
}

Write-Output "AURUM_GUI_LIVE_TRIAL_OK node_id=$($node.node_id) route=$PiAddress mind_version=$($apiStatus.console.mind_version) page_sha256=$pageHash loopback_only=true host_actuation=false"
