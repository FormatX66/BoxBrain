#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet("10.12.194.1")]
    [string]$PiAddress = "10.12.194.1",
    [string]$PiUser = "kali",
    [string]$KeyPath = (Join-Path ([Environment]::GetFolderPath("UserProfile")) ".ssh\boxbrain_pi_ed25519"),
    [string]$KnownHostsPath = (Join-Path ([Environment]::GetFolderPath("UserProfile")) ".ssh\known_hosts"),
    [ValidateRange(1024, 65535)]
    [int]$KvmPort = 27883,
    [Parameter(Mandatory)]
    [ValidatePattern("^[A-Za-z0-9._:-]{1,128}$")]
    [string]$AuthorizationReference,
    [ValidateRange(60, 1800)]
    [int]$EvidenceLifetimeSeconds = 900
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$physicalPath = Join-Path $repositoryRoot "Projects\Codelation\autobuild\external_evidence\bbpi4_presence.json"
$outputPath = Join-Path $repositoryRoot "Projects\Codelation\autobuild\external_evidence\adaptive_shell_live_trial_readiness.json"

function Get-Sha256Hex {
    param([Parameter(Mandatory)][byte[]]$Bytes)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace("-", "").ToLowerInvariant()
    }
    finally { $sha.Dispose() }
}

function Write-JsonAtomic {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)]$Value)
    $directory = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    $temporary = "$Path.tmp-$PID-$([Guid]::NewGuid().ToString('N'))"
    [IO.File]::WriteAllText(
        $temporary,
        (($Value | ConvertTo-Json -Depth 10) + [Environment]::NewLine),
        [Text.UTF8Encoding]::new($false)
    )
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Test-NeutralInputState {
    param([Parameter(Mandatory)]$Payload)
    return (
        $Payload.ok -eq $true -and
        $Payload.status.keyboard_ready -eq $true -and
        $Payload.status.mouse_ready -eq $true -and
        [int]$Payload.status.pressed_key_count -eq 0 -and
        [int]$Payload.status.modifier_mask -eq 0 -and
        [int]$Payload.status.button_mask -eq 0
    )
}

if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
    throw "The dedicated BoxBrain Pi SSH key is missing: $KeyPath"
}
if (-not (Test-Path -LiteralPath $KnownHostsPath -PathType Leaf)) {
    throw "The SSH known-hosts file is missing: $KnownHostsPath"
}
if (-not (Test-Path -LiteralPath $physicalPath -PathType Leaf)) {
    throw "Fresh BBPI4 physical-presence evidence is missing: $physicalPath"
}

$physical = Get-Content -LiteralPath $physicalPath -Raw | ConvertFrom-Json -ErrorAction Stop
$now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
if (
    [string]$physical.schema -ne "aurum-external-prerequisite-evidence-v0" -or
    [string]$physical.kind -ne "bbpi4-physical-presence" -or
    $physical.verified -ne $true -or
    [int64]$physical.expires_at -lt $now
) {
    throw "BBPI4 physical-presence evidence is invalid or expired."
}

$hostRecords = @(& ssh-keygen.exe -F $PiAddress -f $KnownHostsPath 2>$null)
$hostRecord = $hostRecords | Where-Object { $_ -and -not $_.StartsWith("#") } | Select-Object -First 1
if (-not $hostRecord) { throw "The approved USB SSH route has no pinned host key." }
$hostFields = @($hostRecord -split "\s+")
if ($hostFields.Count -lt 3 -or $hostFields[1] -ne "ssh-ed25519") {
    throw "The approved USB SSH route does not have the expected pinned ED25519 key."
}
$hostKeyBytes = [Convert]::FromBase64String($hostFields[2])
$sha = [Security.Cryptography.SHA256]::Create()
try {
    $hostKeyFingerprint = "SHA256:" + [Convert]::ToBase64String($sha.ComputeHash($hostKeyBytes)).TrimEnd("=")
}
finally { $sha.Dispose() }

$sshOptions = @(
    "-i", $KeyPath,
    "-o", "BatchMode=yes",
    "-o", "IdentitiesOnly=yes",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "UserKnownHostsFile=$KnownHostsPath",
    "-o", "ConnectTimeout=5",
    "-o", "ConnectionAttempts=1"
)
$identityText = @(& ssh.exe @sshOptions "$PiUser@$PiAddress" 'cat "$HOME/.aurum/node.json"' 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw "Strict SSH identity read failed for the approved USB route: $($identityText -join ' ')"
}
$identity = ($identityText -join [Environment]::NewLine) | ConvertFrom-Json -ErrorAction Stop
if (
    [string]$identity.node_id -ne [string]$physical.node_id -or
    [string]$identity.name -ne "kali-raspberrypi" -or
    [string]$identity.arch -ne "aarch64"
) {
    throw "The strict SSH node identity does not match the fresh BBPI4 controller evidence."
}

$baseUri = "http://${PiAddress}:$KvmPort"
$before = Invoke-RestMethod -Uri "$baseUri/api/v1/hid-kvm/status" -Method Get -TimeoutSec 5
if (-not (Test-NeutralInputState -Payload $before)) {
    throw "The HID input carrier is not ready in a neutral pre-trial state."
}

$client = [Net.Http.HttpClient]::new()
$cancellation = [Threading.CancellationTokenSource]::new([TimeSpan]::FromSeconds(5))
try {
    $videoResponse = $client.GetAsync(
        "$baseUri/api/v1/kvm/video",
        [Net.Http.HttpCompletionOption]::ResponseHeadersRead,
        $cancellation.Token
    ).GetAwaiter().GetResult()
    $videoStream = $videoResponse.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
    try {
        $sample = [byte[]]::new(4096)
        $sampleBytes = $videoStream.ReadAsync($sample, 0, $sample.Length, $cancellation.Token).GetAwaiter().GetResult()
        if ($sampleBytes -lt 1024) { throw "The display carrier returned too little bounded frame evidence." }
        $boundedSample = [byte[]]::new($sampleBytes)
        [Array]::Copy($sample, $boundedSample, $sampleBytes)
        $displaySha256 = Get-Sha256Hex -Bytes $boundedSample
        $displayContentType = [string]$videoResponse.Content.Headers.ContentType
        if (
            [int]$videoResponse.StatusCode -ne 200 -or
            -not $displayContentType.StartsWith("multipart/x-mixed-replace")
        ) {
            throw "The display carrier did not return the expected bounded MJPEG stream."
        }
    }
    finally { $videoStream.Dispose() }
}
finally {
    $cancellation.Dispose()
    $client.Dispose()
}

$kvmPage = (Invoke-WebRequest -Uri "$baseUri/kvm" -Method Get -TimeoutSec 5).Content
if ($kvmPage.Length -gt 262144) { throw "The KVM proof page exceeded the bounded size." }
$tokenMatch = [regex]::Match($kvmPage, 'const\s+csrf\s*=\s*("(?:\\.|[^"\\])*")\s*;')
if (-not $tokenMatch.Success) { throw "The KVM input proof token is unavailable." }
$csrfToken = $tokenMatch.Groups[1].Value | ConvertFrom-Json
$releaseParameters = @{
    Uri = "$baseUri/api/v1/hid-kvm/input"
    Method = "Post"
    Headers = @{ "X-BoxBrain-CSRF" = $csrfToken }
    ContentType = "application/json"
    Body = '{"action":"release"}'
    TimeoutSec = 5
}
$release = Invoke-RestMethod @releaseParameters
if ($release.ok -ne $true -or $release.released -ne $true) {
    throw "The neutral HID release roundtrip was not acknowledged."
}
$after = Invoke-RestMethod -Uri "$baseUri/api/v1/hid-kvm/status" -Method Get -TimeoutSec 5
if (-not (Test-NeutralInputState -Payload $after)) {
    throw "The HID input carrier did not return to a neutral post-trial state."
}

$observedAt = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$expiresAt = [Math]::Min([int64]$physical.expires_at, $observedAt + $EvidenceLifetimeSeconds)
if ($expiresAt -le $observedAt) { throw "The readiness evidence would already be expired." }
$evidence = [ordered]@{
    schema = "aurum-adaptive-shell-live-trial-readiness-evidence-v1"
    kind = "adaptive-shell-live-trial-readiness"
    source = "aurum-windows-usb-kvm-bounded-proof"
    verified = $true
    node_id = [string]$physical.node_id
    route = $PiAddress
    ssh_host_key_fingerprint = $hostKeyFingerprint
    observed_at = $observedAt
    expires_at = $expiresAt
    display = [ordered]@{
        verified = $true
        http_status = [int]$videoResponse.StatusCode
        content_type = $displayContentType
        sample_bytes = $sampleBytes
        sample_sha256 = $displaySha256
    }
    input = [ordered]@{
        verified = $true
        action = "release"
        acknowledged = $true
        before_neutral = $true
        after_neutral = $true
    }
    permission = [ordered]@{
        present = $true
        scope = "bounded-adaptive-shell-live-trial"
        authorization_reference = $AuthorizationReference
    }
    rollback = [ordered]@{
        verified = $true
        method = "neutral-hid-release-and-ephemeral-state"
    }
    proof_view = [ordered]@{
        present = $true
        display_sample_sha256 = $displaySha256
        retained_user_content = $false
    }
    authority_granted = $false
    persistent_change_authorized = $false
}
Write-JsonAtomic -Path $outputPath -Value $evidence
Write-Output (
    "AURUM_ADAPTIVE_SHELL_READINESS_OK " +
    "node_id=$($physical.node_id) route=$PiAddress " +
    "display_sha256=$displaySha256 input_action=release persistent_change=false"
)
