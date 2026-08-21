#Requires -Version 5.1
[CmdletBinding()]
param(
    [string[]]$PiAddresses = @("10.12.194.1", "10.42.194.1", "192.168.0.194"),
    [string]$PiUser = "kali",
    [string]$KeyPath = (Join-Path $HOME ".ssh\boxbrain_pi_ed25519"),
    [string]$SshExecutable,
    [string]$ScpExecutable,
    [string]$UserKnownHostsFile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# The BBPI4 gold seed is already installed. The live-graph deploy entry point now
# performs an in-place reconciliation: it preserves the opaque seed and existing
# approved runtime persistence, installs only bounded Aurum files, and rejects
# newly introduced persistence. Morri currently reaches BBPI4 over USB SSH, so
# 10.12.194.1 is the first bounded route.
$reconciler = Join-Path $PSScriptRoot "reconcile-existing-aurum-gold-seed-on-pi.ps1"
if (-not (Test-Path -LiteralPath $reconciler -PathType Leaf)) {
    throw "The Aurum gold-seed reconciler is missing: $reconciler"
}

$arguments = @{
    PiAddresses = $PiAddresses
    PiUser = $PiUser
    KeyPath = $KeyPath
}
if ($SshExecutable) { $arguments.SshExecutable = $SshExecutable }
if ($ScpExecutable) { $arguments.ScpExecutable = $ScpExecutable }
if ($UserKnownHostsFile) { $arguments.UserKnownHostsFile = $UserKnownHostsFile }
& $reconciler @arguments

# The shared seed must carry executable human capabilities, not only trait names.
# Reuse the exact same pretrusted carrier and bounded arguments to install the
# seven tested Generation-0 trait bundles plus the Garden projection. This adds
# no service, cron entry, or automatic package mutation on the physical Pi.
$traitDeployer = Join-Path $PSScriptRoot "deploy-aurum-traits-to-pi.ps1"
if (-not (Test-Path -LiteralPath $traitDeployer -PathType Leaf)) {
    throw "The Aurum human-trait deployer is missing: $traitDeployer"
}
& $traitDeployer @arguments

# A verified physical seed is only the prerequisite for the current frontier.
# Once reconciliation succeeds, reuse the *same already-verified SSH carrier* to
# enroll BBPI4 with the Arkmatx node directory and emit one fresh outbound
# heartbeat. This stage is deliberately non-blocking for seed health: a temporary
# controller/network failure must not turn a verified gold seed into a false
# PI4_SEED_FAILURE. The event loop will only confirm BBPI4 if the controller
# independently exposes the resulting fresh Linux ARM64 heartbeat.
function Invoke-OpenSshNative {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$SuppressStderr
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $nativeOutput = @()
    $nativeExitCode = 1
    try {
        $ErrorActionPreference = "Continue"
        if ($SuppressStderr) {
            $nativeOutput = @(& $Executable @Arguments 2>$null)
        } else {
            $nativeOutput = @(& $Executable @Arguments 2>&1)
        }
        $nativeExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    [pscustomobject]@{ Output = $nativeOutput; ExitCode = $nativeExitCode }
}

function Write-OpenSshOutput($Result) {
    foreach ($item in $Result.Output) { Write-Output ([string]$item) }
}

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$bootstrap = Join-Path $repositoryRoot "Web\Aurum-Arkmatx\bootstrap.sh"
if (-not (Test-Path -LiteralPath $bootstrap -PathType Leaf)) {
    Write-Warning "The Arkmatx Linux bootstrap is missing: $bootstrap"
    Write-Output "AURUM_ARKMATX_ENROLLMENT_WAITING reason=bootstrap-missing"
    return
}

$sshPath = if ($SshExecutable) {
    if (-not (Test-Path -LiteralPath $SshExecutable -PathType Leaf)) {
        Write-Warning "The requested SSH executable is unavailable for Arkmatx enrollment: $SshExecutable"
        Write-Output "AURUM_ARKMATX_ENROLLMENT_WAITING reason=ssh-executable-missing"
        return
    }
    (Resolve-Path -LiteralPath $SshExecutable).Path
} else {
    $found = Get-Command ssh.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $found) {
        Write-Output "AURUM_ARKMATX_ENROLLMENT_WAITING reason=ssh-executable-missing"
        return
    }
    $found.Source
}
$scpPath = if ($ScpExecutable) {
    if (-not (Test-Path -LiteralPath $ScpExecutable -PathType Leaf)) {
        Write-Warning "The requested SCP executable is unavailable for Arkmatx enrollment: $ScpExecutable"
        Write-Output "AURUM_ARKMATX_ENROLLMENT_WAITING reason=scp-executable-missing"
        return
    }
    (Resolve-Path -LiteralPath $ScpExecutable).Path
} else {
    $found = Get-Command scp.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $found) {
        Write-Output "AURUM_ARKMATX_ENROLLMENT_WAITING reason=scp-executable-missing"
        return
    }
    $found.Source
}

$options = @(
    "-i", $KeyPath,
    "-o", "BatchMode=yes",
    "-o", "IdentitiesOnly=yes",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "ConnectTimeout=4"
)
if ($UserKnownHostsFile) {
    if (-not (Test-Path -LiteralPath $UserKnownHostsFile -PathType Leaf)) {
        Write-Output "AURUM_ARKMATX_ENROLLMENT_WAITING reason=verified-known-hosts-missing"
        return
    }
    $options += @("-o", "UserKnownHostsFile=$UserKnownHostsFile")
}

$selected = $null
foreach ($address in $PiAddresses) {
    $probe = Invoke-OpenSshNative -Executable $sshPath -Arguments ($options + @(
        "$PiUser@$address",
        "test -d /opt/boxbrain/codelation"
    )) -SuppressStderr
    if ($probe.ExitCode -eq 0) {
        $selected = $address
        break
    }
}
if (-not $selected) {
    Write-Output "AURUM_ARKMATX_ENROLLMENT_WAITING reason=verified-pi-route-unreachable"
    return
}

$target = "$PiUser@$selected"
$remoteBootstrap = "/tmp/aurum-arkmatx-bootstrap-$([Guid]::NewGuid().ToString('N')).sh"
try {
    $copy = Invoke-OpenSshNative -Executable $scpPath -Arguments ($options + @(
        $bootstrap,
        "${target}:$remoteBootstrap"
    ))
    Write-OpenSshOutput $copy
    if ($copy.ExitCode -ne 0) {
        Write-Output "AURUM_ARKMATX_ENROLLMENT_WAITING reason=bootstrap-transfer-failed address=$selected"
        return
    }

    $remoteCommand = "chmod 700 -- '$remoteBootstrap' && '$remoteBootstrap'; code=`$?; rm -f -- '$remoteBootstrap'; exit `$code"
    $run = Invoke-OpenSshNative -Executable $sshPath -Arguments ($options + @($target, $remoteCommand))
    Write-OpenSshOutput $run
    $text = ($run.Output | ForEach-Object { [string]$_ }) -join "`n"
    if ($run.ExitCode -ne 0) {
        Write-Output "AURUM_ARKMATX_ENROLLMENT_WAITING reason=remote-bootstrap-failed address=$selected"
        return
    }
    if (-not $text.Contains('Aurum node enrolled and heartbeat confirmed.')) {
        Write-Output "AURUM_ARKMATX_ENROLLMENT_WAITING reason=heartbeat-confirmation-marker-missing address=$selected"
        return
    }

    $nodeId = if ($text -match '(?m)^Node:\s*([A-Za-z0-9._-]+)\s*$') { $Matches[1] } else { 'unknown' }
    Write-Output "AURUM_ARKMATX_HEARTBEAT_VERIFIED address=$selected node_id=$nodeId carrier=https-outbound"
}
finally {
    [void](Invoke-OpenSshNative -Executable $sshPath -Arguments ($options + @(
        $target,
        "rm -f -- '$remoteBootstrap'"
    )) -SuppressStderr)
}
