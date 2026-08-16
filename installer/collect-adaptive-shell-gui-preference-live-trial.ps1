#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet("10.12.194.1")]
    [string]$PiAddress = "10.12.194.1",
    [ValidatePattern("^[a-z_][a-z0-9_-]{0,31}$")]
    [string]$PiUser = "kali",
    [string]$KeyPath = (Join-Path $HOME ".ssh\boxbrain_pi_ed25519"),
    [string]$KnownHostsPath = (Join-Path $HOME ".ssh\known_hosts"),
    [ValidateRange(1024, 65525)]
    [int]$LocalPort = 8765,
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
$outputPath = Join-Path $evidenceDirectory "adaptive_shell_gui_preference_live_trial.json"
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

function Invoke-PreferenceTrialSsh {
    param(
        [Parameter(Mandatory)][string]$Command,
        [switch]$AllowFailure
    )
    $lines = @(& $ssh @options $target $Command 2>&1)
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0 -and -not $AllowFailure) {
        throw "The strict BBPI4 preference-trial command failed: $($lines -join ' ')"
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = ($lines -join "`n").Trim()
    }
}

function Get-SemanticStateHash {
    param(
        [Parameter(Mandatory)][bool]$SafeLayout,
        [Parameter(Mandatory)][bool]$AdaptationLocked
    )
    $canonical = "safe_layout=$($SafeLayout.ToString().ToLowerInvariant());adaptation_locked=$($AdaptationLocked.ToString().ToLowerInvariant())"
    $bytes = [Text.Encoding]::UTF8.GetBytes($canonical)
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha256.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $sha256.Dispose()
    }
}

$listener = Get-NetTCPConnection `
    -LocalAddress "127.0.0.1" `
    -LocalPort $LocalPort `
    -State Listen `
    -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($null -eq $listener) {
    throw "The Windows-loopback Aurum GUI tunnel is not active on port $LocalPort."
}
$tunnelProcess = Get-CimInstance Win32_Process `
    -Filter "ProcessId = $($listener.OwningProcess)" `
    -ErrorAction Stop
$expectedForward = "127.0.0.1:${LocalPort}:127.0.0.1:8765"
if (
    $tunnelProcess.Name -ne 'ssh.exe' -or
    $tunnelProcess.CommandLine -notlike "*$expectedForward*" -or
    $tunnelProcess.CommandLine -notlike "*$target*"
) {
    throw "Port $LocalPort is not the approved strict BBPI4 GUI tunnel."
}

$node = (Invoke-PreferenceTrialSsh -Command 'cat "$HOME/.aurum/node.json"').Output | ConvertFrom-Json
$start = (Invoke-PreferenceTrialSsh -Command 'sudo -n /usr/local/bin/aurum-gui-start').Output
$moduleHash = (Invoke-PreferenceTrialSsh -Command "sha256sum /opt/boxbrain/codelation/seed/aurum_gui.py | awk '{print `$1}'").Output
$serviceState = (Invoke-PreferenceTrialSsh -Command 'sudo -n systemctl is-active aurum-gui.service').Output
$enabledState = (Invoke-PreferenceTrialSsh -Command 'sudo -n systemctl is-enabled aurum-gui.service' -AllowFailure).Output
$piListener = (Invoke-PreferenceTrialSsh -Command "ss -ltnH 'sport = :8765'").Output

$baseUrl = "http://127.0.0.1:$LocalPort"
$page = Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/" -TimeoutSec 5
if ($page.StatusCode -ne 200 -or $page.Content -notmatch '<meta name="aurum-csrf" content="(?<Token>[A-Za-z0-9_-]{32,})">') {
    throw "The Aurum GUI page did not expose a bounded request proof."
}
$csrf = $Matches['Token']
$headers = @{
    Origin = $baseUrl
    'X-Aurum-CSRF' = $csrf
}
$baseline = Invoke-RestMethod -Uri "$baseUrl/api/status" -TimeoutSec 5
if (
    [string]$baseline.schema -ne 'aurum.gui.v2' -or
    [string]$baseline.preferences.schema -ne 'aurum.gui.preferences.v1'
) {
    throw "The Aurum GUI preference baseline was invalid."
}
$baselineRevision = [int]$baseline.preferences.revision
$baselineSafe = [bool]$baseline.preferences.safe_layout
$baselineLocked = [bool]$baseline.preferences.adaptation_locked
$trialSafe = -not $baselineSafe

$applyBody = [ordered]@{
    expected_revision = $baselineRevision
    safe_layout = $trialSafe
    adaptation_locked = $baselineLocked
} | ConvertTo-Json -Compress
$applied = Invoke-RestMethod `
    -Method Post `
    -Uri "$baseUrl/api/preferences" `
    -Headers $headers `
    -ContentType 'application/json' `
    -Body $applyBody `
    -TimeoutSec 5
if (
    [int]$applied.preferences.revision -ne $baselineRevision + 1 -or
    [bool]$applied.preferences.safe_layout -ne $trialSafe -or
    [bool]$applied.preferences.adaptation_locked -ne $baselineLocked -or
    $applied.user_content_captured -ne $false -or
    $applied.host_actuation -ne $false
) {
    throw "The bounded GUI preference application was not observed."
}

$staleRejected = $false
try {
    Invoke-WebRequest `
        -UseBasicParsing `
        -Method Post `
        -Uri "$baseUrl/api/preferences" `
        -Headers $headers `
        -ContentType 'application/json' `
        -Body $applyBody `
        -TimeoutSec 5 | Out-Null
}
catch {
    if ($null -ne $_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 409) {
        $staleRejected = $true
    }
    else {
        throw
    }
}
if (-not $staleRejected) {
    throw "The GUI preference revision guard did not reject a stale write."
}

$rollbackBody = [ordered]@{
    expected_revision = $baselineRevision + 1
    safe_layout = $baselineSafe
    adaptation_locked = $baselineLocked
} | ConvertTo-Json -Compress
$rolledBack = Invoke-RestMethod `
    -Method Post `
    -Uri "$baseUrl/api/preferences" `
    -Headers $headers `
    -ContentType 'application/json' `
    -Body $rollbackBody `
    -TimeoutSec 5
$restored = Invoke-RestMethod -Uri "$baseUrl/api/status" -TimeoutSec 5
if (
    [int]$rolledBack.preferences.revision -ne $baselineRevision + 2 -or
    [bool]$restored.preferences.safe_layout -ne $baselineSafe -or
    [bool]$restored.preferences.adaptation_locked -ne $baselineLocked
) {
    throw "The GUI preference rollback did not restore the semantic baseline."
}

$applyEvidenceName = [string]$applied.evidence
$rollbackEvidenceName = [string]$rolledBack.evidence
if (
    $applyEvidenceName -notmatch '^AURUM_GUI_PREFERENCE_[0-9]{8}_[0-9a-f]{12}\.json$' -or
    $rollbackEvidenceName -notmatch '^AURUM_GUI_PREFERENCE_[0-9]{8}_[0-9a-f]{12}\.json$'
) {
    throw "The GUI preference Proof View references were invalid."
}
$evidenceHashes = (Invoke-PreferenceTrialSsh -Command "sha256sum '/opt/boxbrain/codelation/verification/interface/$applyEvidenceName' '/opt/boxbrain/codelation/verification/interface/$rollbackEvidenceName'").Output
$hashMatches = [regex]::Matches($evidenceHashes, '(?m)^(?<Hash>[0-9a-f]{64})\s+/\S+$')
if ($hashMatches.Count -ne 2) {
    throw "The GUI preference Proof View files were not verifiable."
}
$applyEvidenceHash = $hashMatches[0].Groups['Hash'].Value
$rollbackEvidenceHash = $hashMatches[1].Groups['Hash'].Value

$statusJson = $restored | ConvertTo-Json -Depth 9 -Compress
$statusBytes = [Text.Encoding]::UTF8.GetBytes($statusJson)
$statusHasher = [Security.Cryptography.SHA256]::Create()
try {
    $statusHash = ([BitConverter]::ToString($statusHasher.ComputeHash($statusBytes))).Replace('-', '').ToLowerInvariant()
}
finally {
    $statusHasher.Dispose()
}
$baselineHash = Get-SemanticStateHash -SafeLayout $baselineSafe -AdaptationLocked $baselineLocked
$restoredHash = Get-SemanticStateHash -SafeLayout ([bool]$restored.preferences.safe_layout) -AdaptationLocked ([bool]$restored.preferences.adaptation_locked)

if (
    [string]$deployment.schema -ne 'aurum-bbpi4-console-evidence-v1' -or
    [string]$deployment.node_id -ne [string]$node.node_id -or
    $start -notmatch '^AURUM_GUI_READY address=127\.0\.0\.1 port=8765 transient=true$' -or
    $moduleHash -ne $expectedModuleHash -or
    $serviceState -ne 'active' -or
    $enabledState -eq 'enabled' -or
    $piListener -notmatch '127\.0\.0\.1:8765' -or
    $piListener -match '0\.0\.0\.0:8765|10\.12\.194\.1:8765' -or
    $baselineHash -ne $restoredHash
) {
    throw "The GUI preference live trial did not satisfy its runtime boundary."
}

$observedAt = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$evidence = [ordered]@{
    schema = "aurum-adaptive-shell-gui-preference-live-trial-evidence-v1"
    kind = "adaptive-shell-gui-preference-live-trial"
    source = "aurum-bbpi4-reversible-gui-preference-proof"
    verified = $true
    node_id = [string]$node.node_id
    route = $PiAddress
    ssh_host_key_fingerprint = [string]$deployment.ssh_host_key_fingerprint
    observed_at = $observedAt
    expires_at = $observedAt + $TimeToLiveSeconds
    candidate = [ordered]@{
        module = "/opt/boxbrain/codelation/seed/aurum_gui.py"
        module_sha256 = $moduleHash
        gui_schema = "aurum.gui.v2"
        preference_schema = "aurum.gui.preferences.v1"
        tests_passed = $true
    }
    runtime = [ordered]@{
        service_active = $true
        service_enabled = $false
        transient = $true
        address = "127.0.0.1"
        port = 8765
        listener_loopback_only = $true
        status_schema = "aurum.gui.v2"
        status_sha256 = $statusHash
    }
    trial = [ordered]@{
        baseline = [ordered]@{
            revision = $baselineRevision
            safe_layout = $baselineSafe
            adaptation_locked = $baselineLocked
            state_sha256 = $baselineHash
        }
        proposal = [ordered]@{
            field = "safe_layout"
            from = $baselineSafe
            to = $trialSafe
        }
        stale_revision_rejected = $true
        application = [ordered]@{
            verified = $true
            revision = $baselineRevision + 1
            safe_layout = $trialSafe
            adaptation_locked = $baselineLocked
        }
        rollback = [ordered]@{
            verified = $true
            revision = $baselineRevision + 2
            safe_layout = [bool]$restored.preferences.safe_layout
            adaptation_locked = [bool]$restored.preferences.adaptation_locked
            state_sha256 = $restoredHash
        }
        revision_monotonic = $true
    }
    interface = [ordered]@{
        human_constants = @($restored.interface.human_constants)
        safe_layout_available = $true
        adaptation_lock_available = $true
        proof_view_present = $true
        preference_path = "/opt/boxbrain/codelation/state/interface/gui_preferences.json"
        user_content_captured = $false
    }
    transport = [ordered]@{
        strict_host_key_checking = $true
        dedicated_identity = $true
        usb_route = $PiAddress
        windows_endpoint_loopback = $true
        pi_endpoint_loopback = $true
    }
    safety = [ordered]@{
        packages_installed = $false
        persistent_service_enabled = $false
        dialogue_generated = $false
        api_key_persisted = $false
        raw_disk_changed = $false
        firmware_changed = $false
        bootloader_changed = $false
        host_actuation = $false
    }
    permission = [ordered]@{
        present = $true
        scope = "adaptive-shell-gui-preference-live-trial"
        authorization_reference = $AuthorizationReference
    }
    proof_view = [ordered]@{
        present = $true
        baseline_state_sha256 = $baselineHash
        restored_state_sha256 = $restoredHash
        application_evidence_sha256 = $applyEvidenceHash
        rollback_evidence_sha256 = $rollbackEvidenceHash
        user_content_captured = $false
    }
    authority_granted = $false
}

New-Item -ItemType Directory -Force -Path $evidenceDirectory | Out-Null
$temporary = "$outputPath.$([Guid]::NewGuid().ToString('N')).tmp"
try {
    $json = $evidence | ConvertTo-Json -Depth 10
    [IO.File]::WriteAllText($temporary, $json + "`n", [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $outputPath -Force
}
finally {
    if (Test-Path -LiteralPath $temporary) {
        Remove-Item -LiteralPath $temporary -Force
    }
}

Write-Output "AURUM_GUI_PREFERENCE_TRIAL_OK node_id=$($node.node_id) route=$PiAddress baseline_revision=$baselineRevision restored_revision=$($baselineRevision + 2) rollback_verified=true user_content_captured=false authority_granted=false"
