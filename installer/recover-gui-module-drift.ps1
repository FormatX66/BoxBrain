#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet("10.12.194.1", "10.42.194.1", "bbpi4.local", "192.168.0.194")]
    [string]$PiAddress,
    [ValidatePattern("^[a-z_][a-z0-9_-]{0,31}$")]
    [string]$PiUser = "kali",
    [Parameter(Mandatory)]
    [string]$KeyPath,
    [Parameter(Mandatory)]
    [string]$KnownHostsPath,
    [ValidatePattern("^[0-9a-f]{64}$")]
    [string]$RollbackSha
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

foreach ($required in @($KeyPath, $KnownHostsPath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required strict SSH file was not found: $required"
    }
}

$ssh = (Get-Command ssh.exe -CommandType Application -ErrorAction Stop).Source
$scp = (Get-Command scp.exe -CommandType Application -ErrorAction Stop).Source
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$modulePath = Join-Path $repositoryRoot "Projects\Codelation\seed\aurum_gui.py"
if (-not (Test-Path -LiteralPath $modulePath -PathType Leaf)) {
    throw "The reviewed Aurum GUI module is unavailable: $modulePath"
}

$target = "$PiUser@$PiAddress"
$transportOptions = @(
    "-i", $KeyPath,
    "-o", "BatchMode=yes",
    "-o", "IdentitiesOnly=yes",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "UserKnownHostsFile=$KnownHostsPath",
    "-o", "ConnectTimeout=8"
)

function Invoke-StrictNative {
    param(
        [Parameter(Mandatory)][string]$Executable,
        [Parameter(Mandatory)][string[]]$Arguments
    )
    $savedErrorActionPreference = $ErrorActionPreference
    try {
        # Windows PowerShell 5.1 promotes native stderr to ErrorRecord objects.
        # Capture both streams and treat the native exit code as authoritative.
        $ErrorActionPreference = "Continue"
        $lines = @(& $Executable @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $savedErrorActionPreference
    }
    foreach ($line in $lines) {
        Write-Host ([string]$line)
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = @($lines | ForEach-Object { [string]$_ })
    }
}

function Invoke-RemoteScript {
    param(
        [Parameter(Mandatory)][string]$Script,
        [Parameter(Mandatory)][string[]]$RemoteArguments
    )
    $normalized = $Script.Replace("`r`n", "`n")
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($normalized))
    $quoted = @($RemoteArguments | ForEach-Object {
        if ($_ -notmatch "^[A-Za-z0-9_./:-]+$") {
            throw "Unsafe bounded remote argument: $_"
        }
        "'$_'"
    }) -join " "
    $command = "printf %s '$encoded' | base64 -d | sudo -n sh -s -- $quoted"
    return Invoke-StrictNative -Executable $ssh -Arguments @($transportOptions + @($target, $command))
}

$destination = "/opt/boxbrain/codelation/seed/aurum_gui.py"
$rollbackRoot = "/opt/boxbrain/codelation/rollback/gui"

if ($RollbackSha) {
    $rollbackScript = @'
set -eu
previous="$1"
destination=/opt/boxbrain/codelation/seed/aurum_gui.py
backup="/opt/boxbrain/codelation/rollback/gui/aurum_gui.py.$previous"
test -f "$backup"
systemctl stop aurum-gui.service >/dev/null 2>&1 || true
install -o root -g root -m 0644 "$backup" "$destination"
restored="$(sha256sum "$destination" | awk '{print $1}')"
[ "$restored" = "$previous" ]
printf 'AURUM_GUI_MODULE_ROLLBACK_OK restored_sha=%s persistent_service=false\n' "$restored"
'@
    $rollback = Invoke-RemoteScript -Script $rollbackScript -RemoteArguments @($RollbackSha)
    if ($rollback.ExitCode -ne 0) {
        throw "The bounded Aurum GUI module rollback failed."
    }
    return
}

$expectedHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $modulePath).Hash.ToLowerInvariant()
$remoteRoot = "/tmp/aurum-gui-module-$([Guid]::NewGuid().ToString('N'))"
$mkdir = Invoke-StrictNative -Executable $ssh -Arguments @(
    $transportOptions + @($target, "umask 077; mkdir -- '$remoteRoot'")
)
if ($mkdir.ExitCode -ne 0) {
    throw "Could not create the bounded Aurum GUI module staging directory."
}

try {
    $transfer = Invoke-StrictNative -Executable $scp -Arguments @(
        $transportOptions + @($modulePath, "${target}:$remoteRoot/aurum_gui.py")
    )
    if ($transfer.ExitCode -ne 0) {
        throw "Could not transfer the reviewed Aurum GUI module."
    }

    $repairScript = @'
set -eu
source="$1"
expected="$2"
destination=/opt/boxbrain/codelation/seed/aurum_gui.py
rollback=/opt/boxbrain/codelation/rollback/gui
test -f "$source"
test -f "$destination"
incoming="$(sha256sum "$source" | awk '{print $1}')"
[ "$incoming" = "$expected" ]
existing="$(sha256sum "$destination" | awk '{print $1}')"
if [ "$existing" != "$expected" ]; then
  install -d -o root -g root -m 0755 "$rollback"
  backup="$rollback/aurum_gui.py.$existing"
  if [ ! -e "$backup" ]; then
    install -o root -g root -m 0644 "$destination" "$backup"
  fi
  systemctl stop aurum-gui.service >/dev/null 2>&1 || true
  install -o root -g root -m 0644 "$source" "$destination"
fi
installed="$(sha256sum "$destination" | awk '{print $1}')"
[ "$installed" = "$expected" ]
printf 'AURUM_GUI_MODULE_REPAIRED previous_sha=%s installed_sha=%s rollback=%s/aurum_gui.py.%s persistent_service=false\n' \
  "$existing" "$installed" "$rollback" "$existing"
'@
    $repair = Invoke-RemoteScript -Script $repairScript -RemoteArguments @(
        "$remoteRoot/aurum_gui.py",
        $expectedHash
    )
    if ($repair.ExitCode -ne 0) {
        throw "The bounded Aurum GUI module repair failed."
    }
}
finally {
    $cleanup = Invoke-StrictNative -Executable $ssh -Arguments @(
        $transportOptions + @($target, "rm -rf -- '$remoteRoot'")
    )
    if ($cleanup.ExitCode -ne 0) {
        Write-Warning "The remote Aurum GUI staging directory could not be removed."
    }
}
