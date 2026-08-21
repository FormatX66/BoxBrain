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

if ($PiUser -notmatch '^[a-z_][a-z0-9_-]*$') {
    throw "The BBPI4 SSH user is not a safe POSIX account name: $PiUser"
}
if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
    throw "The dedicated BoxBrain SSH identity was not found at $KeyPath."
}

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$source = Join-Path $repositoryRoot "Projects\AurumTraits"
foreach ($required in @("traits.json", "validate_traits.py", "aurum_traits.py", "tests\test_aurum_traits.py")) {
    $candidate = Join-Path $source $required
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "The executable Aurum human-trait payload is incomplete: $candidate"
    }
}

$sshPath = if ($SshExecutable) {
    if (-not (Test-Path -LiteralPath $SshExecutable -PathType Leaf)) {
        throw "The requested SSH executable was not found: $SshExecutable"
    }
    (Resolve-Path -LiteralPath $SshExecutable).Path
} else {
    (Get-Command ssh.exe -CommandType Application -ErrorAction Stop).Source
}
$scpPath = if ($ScpExecutable) {
    if (-not (Test-Path -LiteralPath $ScpExecutable -PathType Leaf)) {
        throw "The requested SCP executable was not found: $ScpExecutable"
    }
    (Resolve-Path -LiteralPath $ScpExecutable).Path
} else {
    (Get-Command scp.exe -CommandType Application -ErrorAction Stop).Source
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
        throw "The verified SSH known_hosts file was not found: $UserKnownHostsFile"
    }
    $options += @("-o", "UserKnownHostsFile=$UserKnownHostsFile")
}

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

$selected = $null
foreach ($address in $PiAddresses) {
    $probe = Invoke-OpenSshNative -Executable $sshPath -Arguments ($options + @(
        "$PiUser@$address",
        "test -d /opt/boxbrain/codelation || test -d /opt/aurum"
    )) -SuppressStderr
    if ($probe.ExitCode -eq 0) {
        $selected = $address
        break
    }
}
if (-not $selected) {
    throw "The verified BBPI4 seed route was not reachable for human-trait deployment."
}

$target = "$PiUser@$selected"
$transfer = "/tmp/aurum-traits-$([Guid]::NewGuid().ToString('N'))"
$remoteScript = "/tmp/aurum-traits-install-$([Guid]::NewGuid().ToString('N')).sh"
$localRemoteScript = Join-Path ([IO.Path]::GetTempPath()) ("aurum-traits-install-" + [Guid]::NewGuid().ToString('N') + ".sh")
$remote = @'
#!/usr/bin/env bash
set -euo pipefail
TRANSFER="$1"
PI_USER="$2"
STAGED="$TRANSFER/AurumTraits"
INSTALL=/opt/boxbrain/aurum-traits
ROLLBACK_ROOT=/opt/boxbrain/rollback
STAMP="$(date -u +%Y%m%dT%H%M%SZ)-$$"
ROLLBACK="$ROLLBACK_ROOT/aurum-traits-$STAMP"
NEXT="$INSTALL.next-$STAMP"

[ -f "$STAGED/traits.json" ]
[ -f "$STAGED/validate_traits.py" ]
[ -f "$STAGED/aurum_traits.py" ]
[ -f "$STAGED/tests/test_aurum_traits.py" ]

python3 "$STAGED/validate_traits.py"
python3 "$STAGED/aurum_traits.py" validate
python3 -m unittest discover -s "$STAGED/tests" -v
python3 "$STAGED/aurum_traits.py" build-all --output "$STAGED/bundles"
for bundle in "$STAGED"/bundles/*/bundle.json; do
  python3 "$STAGED/aurum_traits.py" verify-bundle --bundle "$bundle"
done
[ "$(find "$STAGED/bundles" -name bundle.json | wc -l)" -eq 7 ]

sudo -n install -d -o root -g root -m 700 "$ROLLBACK_ROOT"
if [ -d "$INSTALL" ]; then
  sudo -n cp -a "$INSTALL" "$ROLLBACK"
else
  ROLLBACK=none
fi
sudo -n rm -rf -- "$NEXT"
sudo -n install -d -o "$PI_USER" -g "$PI_USER" -m 700 "$NEXT"
sudo -n cp -a "$STAGED/." "$NEXT/"
sudo -n chown -R "$PI_USER:$PI_USER" "$NEXT"
sudo -n rm -rf -- "$INSTALL"
sudo -n mv -- "$NEXT" "$INSTALL"

GARDEN="$(python3 "$INSTALL/aurum_traits.py" garden --root "/home/$PI_USER")"
install -d -m 700 "$INSTALL/verification/provider-probes"
for trait in WEB FILES MEDIA WRITE INTENT CONNECT RECOVER; do
  python3 "$INSTALL/aurum_traits.py" probe --trait "TR8:$trait" \
    > "$INSTALL/verification/provider-probes/${trait,,}.json"
done

rm -rf -- "$TRANSFER"
printf '%s\n' \
  "AURUM_HUMAN_TRAITS_DEPLOYED" \
  "address=$(hostname -I 2>/dev/null | awk '{print $1}')" \
  "architecture=$(uname -m)" \
  "runtime=$INSTALL/aurum_traits.py" \
  "bundles=7" \
  "garden=$GARDEN" \
  "rollback=$ROLLBACK" \
  "persistence_added=0"
'@

$utf8NoBom = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText($localRemoteScript, $remote, $utf8NoBom)
try {
    $mkdir = Invoke-OpenSshNative -Executable $sshPath -Arguments ($options + @(
        $target,
        "umask 077; mkdir -p -- '$transfer'"
    ))
    Write-OpenSshOutput $mkdir
    if ($mkdir.ExitCode -ne 0) { throw "Could not create the bounded BBPI4 trait staging directory." }

    $payloadCopy = Invoke-OpenSshNative -Executable $scpPath -Arguments ($options + @(
        "-r",
        $source,
        "${target}:$transfer/"
    ))
    Write-OpenSshOutput $payloadCopy
    if ($payloadCopy.ExitCode -ne 0) { throw "Could not stage the Aurum human-trait payload on BBPI4." }

    $scriptCopy = Invoke-OpenSshNative -Executable $scpPath -Arguments ($options + @(
        $localRemoteScript,
        "${target}:$remoteScript"
    ))
    Write-OpenSshOutput $scriptCopy
    if ($scriptCopy.ExitCode -ne 0) { throw "Could not stage the bounded BBPI4 trait installer." }

    $remoteCommand = "chmod 700 -- '$remoteScript' && '$remoteScript' '$transfer' '$PiUser'; code=`$?; rm -f -- '$remoteScript'; exit `$code"
    $run = Invoke-OpenSshNative -Executable $sshPath -Arguments ($options + @($target, $remoteCommand))
    Write-OpenSshOutput $run
    if ($run.ExitCode -ne 0) { throw "The bounded BBPI4 human-trait deployment failed." }
    $text = ($run.Output | ForEach-Object { [string]$_ }) -join "`n"
    if (-not $text.Contains("AURUM_HUMAN_TRAITS_DEPLOYED")) {
        throw "The BBPI4 human-trait deployment marker was not emitted."
    }
    Write-Output "AURUM_PI4_HUMAN_TRAITS_OK address=$selected bundles=7"
}
finally {
    Remove-Item -LiteralPath $localRemoteScript -Force -ErrorAction SilentlyContinue
    [void](Invoke-OpenSshNative -Executable $sshPath -Arguments ($options + @(
        $target,
        "rm -rf -- '$transfer'; rm -f -- '$remoteScript'"
    )) -SuppressStderr)
}
