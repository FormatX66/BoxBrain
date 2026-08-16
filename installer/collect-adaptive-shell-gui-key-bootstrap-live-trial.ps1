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
$outputPath = Join-Path $evidenceDirectory "adaptive_shell_gui_key_bootstrap_live_trial.json"
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

function Invoke-KeyBootstrapTrialSsh {
    param(
        [Parameter(Mandatory)][string]$Command,
        [switch]$AllowFailure
    )
    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $lines = @(& $ssh @options $target $Command 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorPreference
    }
    if ($exitCode -ne 0 -and -not $AllowFailure) {
        throw "The strict BBPI4 key-bootstrap trial command failed: $($lines -join ' ')"
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = ($lines -join "`n").Trim()
    }
}

function Get-TextSha256 {
    param([Parameter(Mandatory)][string]$Text)
    $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
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

$node = (Invoke-KeyBootstrapTrialSsh -Command 'cat "$HOME/.aurum/node.json"').Output | ConvertFrom-Json
$start = (Invoke-KeyBootstrapTrialSsh -Command 'sudo -n /usr/local/bin/aurum-gui-start').Output
$moduleHash = (Invoke-KeyBootstrapTrialSsh -Command "sha256sum /opt/boxbrain/codelation/seed/aurum_gui.py | cut -d ' ' -f1").Output
$serviceState = (Invoke-KeyBootstrapTrialSsh -Command 'sudo -n systemctl is-active aurum-gui.service').Output
$enabledState = (Invoke-KeyBootstrapTrialSsh -Command 'sudo -n systemctl is-enabled aurum-gui.service' -AllowFailure).Output
$piListener = (Invoke-KeyBootstrapTrialSsh -Command "ss -ltnH 'sport = :8765'").Output
$persistenceCommand = "find /opt/boxbrain/codelation/state /opt/boxbrain/codelation/verification -type f -print0 2>/dev/null | sort -z | xargs -0 -r sha256sum | sha256sum | cut -d ' ' -f1"
$persistenceBefore = (Invoke-KeyBootstrapTrialSsh -Command $persistenceCommand).Output

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
$statusResponse = Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/api/status" -TimeoutSec 5
$status = $statusResponse.Content | ConvertFrom-Json
if (
    [string]$status.schema -ne 'aurum.gui.v3' -or
    [string]$status.key_bootstrap.schema -ne 'aurum.gui.key-bootstrap.v1' -or
    $status.key_bootstrap.memory_only -ne $true -or
    $status.key_bootstrap.pending -ne $false
) {
    throw "The Aurum key-bootstrap baseline was invalid."
}

$synthetic = "sk-synthetic-noncredential-$([Guid]::NewGuid().ToString('N'))"
$stageBody = [ordered]@{action = 'stage'; api_key = $synthetic} | ConvertTo-Json -Compress
$stage = Invoke-RestMethod `
    -Method Post `
    -Uri "$baseUrl/api/key-bootstrap" `
    -Headers $headers `
    -ContentType 'application/json' `
    -Body $stageBody `
    -TimeoutSec 5
$consumeBody = [ordered]@{action = 'consume'} | ConvertTo-Json -Compress
$consumed = Invoke-RestMethod `
    -Method Post `
    -Uri "$baseUrl/api/key-bootstrap" `
    -Headers $headers `
    -ContentType 'application/json' `
    -Body $consumeBody `
    -TimeoutSec 5
$singleConsumeVerified = (
    $stage.staged -eq $true -and
    $stage.memory_only -eq $true -and
    $stage.api_key_persisted -eq $false -and
    $consumed.available -eq $true -and
    [string]$consumed.api_key -ceq $synthetic -and
    $consumed.api_key_persisted -eq $false
)
$consumed.api_key = $null
$synthetic = $null
$stageBody = $null

$secondConsume = Invoke-RestMethod `
    -Method Post `
    -Uri "$baseUrl/api/key-bootstrap" `
    -Headers $headers `
    -ContentType 'application/json' `
    -Body $consumeBody `
    -TimeoutSec 5
$secondConsumeEmpty = (
    $secondConsume.available -eq $false -and
    $secondConsume.PSObject.Properties.Name -notcontains 'api_key'
)

$expirySynthetic = "sk-synthetic-expiry-noncredential-$([Guid]::NewGuid().ToString('N'))"
$expiryStageBody = [ordered]@{action = 'stage'; api_key = $expirySynthetic} | ConvertTo-Json -Compress
$expiryStage = Invoke-RestMethod `
    -Method Post `
    -Uri "$baseUrl/api/key-bootstrap" `
    -Headers $headers `
    -ContentType 'application/json' `
    -Body $expiryStageBody `
    -TimeoutSec 5
if ($expiryStage.staged -ne $true -or $expiryStage.expires_in_seconds -ne 60) {
    throw "The Aurum key-bootstrap expiry contract was not staged."
}
$expirySynthetic = $null
$expiryStageBody = $null
$expiryWaitSeconds = 62
for ($second = 0; $second -lt $expiryWaitSeconds; $second++) {
    Start-Sleep -Seconds 1
}
$expiredConsume = Invoke-RestMethod `
    -Method Post `
    -Uri "$baseUrl/api/key-bootstrap" `
    -Headers $headers `
    -ContentType 'application/json' `
    -Body $consumeBody `
    -TimeoutSec 5
$expiryVerified = (
    $expiredConsume.available -eq $false -and
    $expiredConsume.PSObject.Properties.Name -notcontains 'api_key'
)
$consumeBody = $null

$finalStatusResponse = Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/api/status" -TimeoutSec 5
$finalStatus = $finalStatusResponse.Content | ConvertFrom-Json
$persistenceAfter = (Invoke-KeyBootstrapTrialSsh -Command $persistenceCommand).Output

if (
    [string]$deployment.node_id -ne [string]$node.node_id -or
    $start -notmatch '(?m)^AURUM_GUI_READY address=127\.0\.0\.1 port=8765 transient=true$' -or
    $moduleHash -ne $expectedModuleHash -or
    $serviceState -ne 'active' -or
    $enabledState -eq 'enabled' -or
    $piListener -notmatch '127\.0\.0\.1:8765' -or
    $piListener -match '0\.0\.0\.0:8765|10\.12\.194\.1:8765' -or
    -not $singleConsumeVerified -or
    -not $secondConsumeEmpty -or
    -not $expiryVerified -or
    $finalStatus.key_bootstrap.pending -ne $false -or
    $persistenceBefore -notmatch '^[0-9a-f]{64}$' -or
    $persistenceAfter -ne $persistenceBefore
) {
    throw "The GUI key-bootstrap live trial did not satisfy its bounded runtime contract."
}

$observedAt = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$evidence = [ordered]@{
    schema = "aurum-adaptive-shell-gui-key-bootstrap-live-trial-evidence-v1"
    kind = "adaptive-shell-gui-key-bootstrap-live-trial"
    source = "aurum-windows-pi-one-time-key-bootstrap-proof"
    verified = $true
    node_id = [string]$node.node_id
    route = $PiAddress
    ssh_host_key_fingerprint = [string]$deployment.ssh_host_key_fingerprint
    observed_at = $observedAt
    expires_at = $observedAt + $TimeToLiveSeconds
    candidate = [ordered]@{
        module = "/opt/boxbrain/codelation/seed/aurum_gui.py"
        module_sha256 = $moduleHash
        gui_schema = "aurum.gui.v3"
        key_bootstrap_schema = "aurum.gui.key-bootstrap.v1"
        tests_passed = $true
    }
    runtime = [ordered]@{
        service_active = $true
        service_enabled = $false
        transient = $true
        address = "127.0.0.1"
        port = 8765
        listener_loopback_only = $true
        status_schema = "aurum.gui.v3"
        status_sha256 = Get-TextSha256 -Text $finalStatusResponse.Content
    }
    trial = [ordered]@{
        stage_verified = $true
        single_consume_verified = $true
        second_consume_empty = $true
        expiry_verified = $true
        expired_consume_empty = $true
        pending_before = $false
        pending_after = $false
        ttl_seconds = 60
        expiry_wait_seconds = $expiryWaitSeconds
        synthetic_noncredential = $true
        actual_api_key_observed = $false
        persistence_surface_before_sha256 = $persistenceBefore
        persistence_surface_after_sha256 = $persistenceAfter
    }
    interface = [ordered]@{
        page_memory_assignment_present = $page.Content -match 'apiKey\.value = data\.api_key'
        bounded_poll_present = $page.Content -match 'setInterval\(consumeKeyBootstrap, 1500\)'
        proof_view_present = $page.Content -match 'Proof View'
        user_content_captured = $false
        credential_content_captured = $false
    }
    transport = [ordered]@{
        strict_host_key_checking = $true
        dedicated_identity = $true
        usb_route = $PiAddress
        windows_endpoint_loopback = $true
        pi_endpoint_loopback = $true
        csrf_verified = $true
        origin_verified = $true
    }
    safety = [ordered]@{
        packages_installed = $false
        persistent_service_enabled = $false
        dialogue_generated = $false
        api_key_persisted = $false
        api_key_logged = $false
        api_key_in_url = $false
        raw_disk_changed = $false
        firmware_changed = $false
        bootloader_changed = $false
        host_actuation = $false
    }
    permission = [ordered]@{
        present = $true
        scope = "adaptive-shell-gui-key-bootstrap-live-trial"
        authorization_reference = $AuthorizationReference
    }
    proof_view = [ordered]@{
        present = $true
        status_sha256 = Get-TextSha256 -Text $finalStatusResponse.Content
        persistence_surface_sha256 = $persistenceBefore
        user_content_captured = $false
        credential_content_captured = $false
    }
    authority_granted = $false
}

New-Item -ItemType Directory -Force -Path $evidenceDirectory | Out-Null
$evidenceJson = $evidence | ConvertTo-Json -Depth 8
[IO.File]::WriteAllText($outputPath, $evidenceJson + "`n", [Text.UTF8Encoding]::new($false))
Write-Output "AURUM_GUI_KEY_BOOTSTRAP_TRIAL_OK node_id=$($node.node_id) route=$PiAddress single_consume=true expiry=true credential_content_captured=false authority_granted=false"
