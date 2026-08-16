#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet("10.12.194.1")]
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
$evidenceDirectory = Join-Path $repositoryRoot "Projects\Codelation\autobuild\external_evidence"
$deploymentPath = Join-Path $evidenceDirectory "bbpi4_aurum_console.json"
$outputPath = Join-Path $evidenceDirectory "adaptive_shell_iteration_observation.json"
$deployment = Get-Content -LiteralPath $deploymentPath -Raw | ConvertFrom-Json
if (
    [string]$deployment.schema -ne "aurum-bbpi4-console-evidence-v1" -or
    $deployment.verified -ne $true -or
    [string]$deployment.route -ne $PiAddress
) {
    throw "Verified BBPI4 console deployment evidence is required."
}

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

function Invoke-GuiObservation {
    param(
        [Parameter(Mandatory)][string]$Command,
        [switch]$AllowFailure
    )
    $lines = @(& $ssh @options $target $Command 2>&1)
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0 -and -not $AllowFailure) {
        throw "The strict BBPI4 GUI observation failed: $($lines -join ' ')"
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = ($lines -join "`n").Trim()
    }
}

$node = (Invoke-GuiObservation -Command 'cat "$HOME/.aurum/node.json"').Output | ConvertFrom-Json
$consoleStatus = (Invoke-GuiObservation -Command '/usr/local/bin/aurum --status').Output
$mind = (Invoke-GuiObservation -Command 'python3 /opt/boxbrain/codelation/seed/aurum_dialogue.py --root /opt/boxbrain/codelation status').Output | ConvertFrom-Json
$pythonPath = (Invoke-GuiObservation -Command 'command -v python3').Output
$pythonVersion = (Invoke-GuiObservation -Command 'python3 --version').Output
$browserPath = (Invoke-GuiObservation -Command 'command -v chromium').Output
$displayPath = (Invoke-GuiObservation -Command 'command -v Xvfb').Output
$websocketPath = (Invoke-GuiObservation -Command 'command -v websockify').Output
$screenInstalled = (Invoke-GuiObservation -Command 'test -x /usr/local/bin/boxbrain-console-start').ExitCode -eq 0
$displayActive = (Invoke-GuiObservation -Command 'sudo -n systemctl is-active boxbrain-console-display.service' -AllowFailure).Output -eq 'active'
$desktopActive = (Invoke-GuiObservation -Command 'sudo -n systemctl is-active boxbrain-console-desktop.service' -AllowFailure).Output -eq 'active'
$portOutput = (Invoke-GuiObservation -Command "ss -ltnH 'sport = :8765'" -AllowFailure).Output
$portAvailable = [string]::IsNullOrWhiteSpace($portOutput)

if (
    [string]$node.node_id -ne [string]$deployment.node_id -or
    $consoleStatus -notmatch '^AURUM_CONSOLE_READY identity=BBPI4/Aurum mind_version=[0-9]+ dialogue_only=true host_actuation=false api_key_persisted=false$' -or
    [string]$mind.identity -ne 'BBPI4/Aurum' -or
    [string]$mind.mind_sha256 -notmatch '^[0-9a-f]{64}$' -or
    $pythonPath -ne '/usr/bin/python3' -or
    $pythonVersion -notmatch '^Python 3\.(1[3-9]|[2-9][0-9])\.' -or
    $browserPath -ne '/usr/bin/chromium' -or
    $displayPath -ne '/usr/bin/Xvfb' -or
    $websocketPath -ne '/usr/bin/websockify' -or
    -not $screenInstalled -or
    -not $displayActive -or
    -not $desktopActive -or
    -not $portAvailable
) {
    throw "The BBPI4 does not satisfy the bounded Aurum GUI capability contract."
}

$snapshot = [ordered]@{
    python3 = $pythonPath
    python_version = $pythonVersion
    browser = $browserPath
    virtual_display = $displayPath
    websocket_bridge = $websocketPath
    screen_path_installed = $screenInstalled
    virtual_display_active = $displayActive
    desktop_active = $desktopActive
    gui_port_available = $portAvailable
}
$snapshotJson = $snapshot | ConvertTo-Json -Compress
$snapshotBytes = [Text.Encoding]::UTF8.GetBytes($snapshotJson)
$sha256 = [Security.Cryptography.SHA256]::Create()
try {
    $snapshotHash = ([BitConverter]::ToString($sha256.ComputeHash($snapshotBytes))).Replace('-', '').ToLowerInvariant()
}
finally {
    $sha256.Dispose()
}

$observedAt = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$evidence = [ordered]@{
    schema = "aurum-adaptive-shell-iteration-observation-evidence-v1"
    kind = "adaptive-shell-iteration-observation"
    source = "aurum-bbpi4-gui-capability-snapshot"
    verified = $true
    node_id = [string]$node.node_id
    route = $PiAddress
    ssh_host_key_fingerprint = [string]$deployment.ssh_host_key_fingerprint
    observed_at = $observedAt
    expires_at = $observedAt + $TimeToLiveSeconds
    console = [ordered]@{
        identity = "BBPI4/Aurum"
        mind_version = [int]$mind.mind_version
        mind_sha256 = [string]$mind.mind_sha256
        dialogue_only = $true
        host_actuation = $false
        api_key_persisted = $false
    }
    capabilities = [ordered]@{
        python3 = $pythonPath
        python_version = $pythonVersion
        python_supported = $true
        browser = $browserPath
        virtual_display = $displayPath
        websocket_bridge = $websocketPath
        gui_port_available = $true
        package_install_required = $false
    }
    display = [ordered]@{
        screen_path_installed = $true
        virtual_display_active = $true
        desktop_active = $true
        private_transport = "strict-ssh-loopback-forward"
    }
    observation = [ordered]@{
        read_only = $true
        dialogue_generated = $false
        user_content_captured = $false
    }
    capability_snapshot_sha256 = $snapshotHash
    permission = [ordered]@{
        present = $true
        scope = "adaptive-shell-gui-candidate"
        authorization_reference = $AuthorizationReference
    }
    proof_view = [ordered]@{
        present = $true
        capability_snapshot_sha256 = $snapshotHash
        user_content_captured = $false
    }
    authority_granted = $false
    persistent_change_authorized = $false
}

New-Item -ItemType Directory -Force -Path $evidenceDirectory | Out-Null
$temporary = "$outputPath.$([Guid]::NewGuid().ToString('N')).tmp"
try {
    $json = $evidence | ConvertTo-Json -Depth 8
    [IO.File]::WriteAllText($temporary, $json + "`n", [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $outputPath -Force
}
finally {
    if (Test-Path -LiteralPath $temporary) {
        Remove-Item -LiteralPath $temporary -Force
    }
}

Write-Output "AURUM_GUI_CAPABILITY_OK node_id=$($node.node_id) route=$PiAddress capability_snapshot_sha256=$snapshotHash user_content_captured=false authority_granted=false"
