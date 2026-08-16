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
    [int]$TimeToLiveSeconds = 900
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
    throw "The dedicated BoxBrain SSH identity was not found at $KeyPath."
}
if (-not (Test-Path -LiteralPath $KnownHostsPath -PathType Leaf)) {
    throw "The strict SSH known-hosts file was not found at $KnownHostsPath."
}

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$evidenceDirectory = Join-Path $repositoryRoot "Projects\Codelation\autobuild\external_evidence"
$deploymentPath = Join-Path $evidenceDirectory "bbpi4_aurum_console.json"
$outputPath = Join-Path $evidenceDirectory "adaptive_shell_iteration_observation_readiness.json"
if (-not (Test-Path -LiteralPath $deploymentPath -PathType Leaf)) {
    throw "The verified BBPI4 console deployment evidence is missing."
}
$deployment = Get-Content -LiteralPath $deploymentPath -Raw | ConvertFrom-Json
if (
    [string]$deployment.schema -ne "aurum-bbpi4-console-evidence-v1" -or
    $deployment.verified -ne $true -or
    [string]$deployment.route -ne $PiAddress -or
    [string]$deployment.console.command -ne "/usr/local/bin/aurum" -or
    $deployment.console.dialogue_only -ne $true -or
    $deployment.console.host_actuation -ne $false -or
    $deployment.console.api_key_persisted -ne $false
) {
    throw "The BBPI4 console deployment evidence is not eligible for observation."
}

$ssh = Get-Command ssh.exe -CommandType Application -ErrorAction Stop
$options = @(
    "-i", $KeyPath,
    "-o", "BatchMode=yes",
    "-o", "IdentitiesOnly=yes",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "UserKnownHostsFile=$KnownHostsPath",
    "-o", "ConnectTimeout=8"
)
$target = "$PiUser@$PiAddress"

function Invoke-ObservationSsh {
    param([Parameter(Mandatory)][string]$Command)

    $lines = @(& $ssh.Source @options $target $Command 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "The strict BBPI4 observation command failed: $($lines -join ' ')"
    }
    return ($lines -join "`n").Trim()
}

$node = Invoke-ObservationSsh -Command 'cat "$HOME/.aurum/node.json"' | ConvertFrom-Json
$consoleStatus = Invoke-ObservationSsh -Command '/usr/local/bin/aurum --status'
$mind = Invoke-ObservationSsh -Command 'python3 /opt/boxbrain/codelation/seed/aurum_dialogue.py --root /opt/boxbrain/codelation status' | ConvertFrom-Json
$hashText = Invoke-ObservationSsh -Command 'sha256sum /usr/local/bin/aurum /opt/boxbrain/codelation/seed/aurum_console.py /opt/boxbrain/codelation/seed/aurum_dialogue.py'

if (
    [string]$node.schema -ne "aurum.node.v0" -or
    [string]$node.node_id -ne [string]$deployment.node_id -or
    [string]$node.name -ne [string]$deployment.name -or
    [string]$node.arch -ne [string]$deployment.architecture
) {
    throw "The fresh BBPI4 identity does not match the console deployment evidence."
}
$statusPattern = '^AURUM_CONSOLE_READY identity=BBPI4/Aurum mind_version=(?<Version>[0-9]+) dialogue_only=true host_actuation=false api_key_persisted=false$'
if ($consoleStatus -notmatch $statusPattern) {
    throw "The Aurum console did not report the bounded readiness contract."
}
$consoleMindVersion = [int]$Matches["Version"]
if (
    [string]$mind.identity -ne "BBPI4/Aurum" -or
    [int]$mind.mind_version -ne $consoleMindVersion -or
    [string]$mind.mind_sha256 -notmatch '^[0-9a-f]{64}$'
) {
    throw "The Aurum console and dialogue mind status do not match."
}

$hashes = @{}
foreach ($line in ($hashText -split "`n")) {
    if ($line -notmatch '^(?<Hash>[0-9a-f]{64})\s+(?<Path>/\S+)$') {
        throw "The BBPI4 console hash output was invalid."
    }
    $hashes[$Matches["Path"]] = $Matches["Hash"]
}
$commandSha256 = [string]$hashes["/usr/local/bin/aurum"]
$moduleSha256 = [string]$hashes["/opt/boxbrain/codelation/seed/aurum_console.py"]
$dialogueSha256 = [string]$hashes["/opt/boxbrain/codelation/seed/aurum_dialogue.py"]
if (
    $commandSha256 -ne [string]$deployment.console.command_sha256 -or
    $moduleSha256 -ne [string]$deployment.console.module_sha256 -or
    $dialogueSha256 -ne [string]$deployment.console.dialogue_supervisor_sha256
) {
    throw "The live BBPI4 console files do not match the deployed verified hashes."
}

$observedAt = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$expiresAt = $observedAt + $TimeToLiveSeconds
$evidence = [ordered]@{
    schema = "aurum-adaptive-shell-iteration-observation-readiness-evidence-v1"
    kind = "adaptive-shell-iteration-observation-readiness"
    source = "aurum-bbpi4-console-status-proof"
    verified = $true
    node_id = [string]$node.node_id
    route = $PiAddress
    ssh_host_key_fingerprint = [string]$deployment.ssh_host_key_fingerprint
    observed_at = $observedAt
    expires_at = $expiresAt
    console = [ordered]@{
        status_verified = $true
        command = "/usr/local/bin/aurum"
        command_sha256 = $commandSha256
        module = "/opt/boxbrain/codelation/seed/aurum_console.py"
        module_sha256 = $moduleSha256
        dialogue_supervisor_sha256 = $dialogueSha256
        identity = "BBPI4/Aurum"
        mind_version = [int]$mind.mind_version
        mind_sha256 = [string]$mind.mind_sha256
        dialogue_only = $true
        host_actuation = $false
        api_key_persisted = $false
    }
    observation = [ordered]@{
        type = "console-status-and-capability-snapshot"
        read_only = $true
        dialogue_generated = $false
        user_content_captured = $false
    }
    permission = [ordered]@{
        present = $true
        scope = "adaptive-shell-iteration-observation"
        authorization_reference = $AuthorizationReference
    }
    proof_view = [ordered]@{
        present = $true
        mind_sha256 = [string]$mind.mind_sha256
        user_content_captured = $false
    }
    authority_granted = $false
    persistent_change_authorized = $false
}

New-Item -ItemType Directory -Force -Path $evidenceDirectory | Out-Null
$temporary = "$outputPath.$([Guid]::NewGuid().ToString('N')).tmp"
try {
    $evidence | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporary -Encoding utf8NoBOM
    Move-Item -LiteralPath $temporary -Destination $outputPath -Force
}
finally {
    if (Test-Path -LiteralPath $temporary) {
        Remove-Item -LiteralPath $temporary -Force
    }
}

Write-Output (
    "AURUM_ITERATION_OBSERVATION_READINESS_OK " +
    "node_id=$($node.node_id) route=$PiAddress mind_version=$($mind.mind_version) " +
    "mind_sha256=$($mind.mind_sha256) user_content_captured=false authority_granted=false"
)
