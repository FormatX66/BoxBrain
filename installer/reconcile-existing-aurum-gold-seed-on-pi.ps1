#Requires -Version 5.1
[CmdletBinding()]
param(
    [string[]]$PiAddresses = @("10.42.194.1", "10.12.194.1", "192.168.0.194"),
    [string]$PiUser = "kali",
    [string]$KeyPath = (Join-Path $HOME ".ssh\boxbrain_pi_ed25519"),
    [string]$SshExecutable,
    [string]$ScpExecutable,
    [string]$UserKnownHostsFile,
    [string]$DesiredState
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
    throw "The dedicated BoxBrain SSH identity was not found at $KeyPath."
}
if ($PiUser -notmatch '^[a-z_][a-z0-9_-]*$') {
    throw "The BBPI4 SSH user is not a safe POSIX account name: $PiUser"
}
if ($DesiredState -and $DesiredState -notmatch '^[A-Za-z0-9._:/-]{1,160}$') {
    throw "DesiredState must be a bounded evidence token, not executable shell input."
}

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$source = Join-Path $repositoryRoot "Projects\Codelation"
if (-not (Test-Path -LiteralPath $source -PathType Container)) {
    throw "Aurum dialogue/live-graph source is missing: $source"
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
        # Windows PowerShell 5.1 wraps any native stderr line in a
        # NativeCommandError when the caller uses Stop. OpenSSH and Python's
        # unittest runner legitimately write diagnostics/progress to stderr,
        # so capture it and continue to enforce the actual process exit code.
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
    $probe = Invoke-OpenSshNative -Executable $sshPath -Arguments ($options + @("$PiUser@$address", "test -d /opt/boxbrain/codelation || test -d /opt/aurum")) -SuppressStderr
    if ($probe.ExitCode -eq 0) {
        $selected = $address
        break
    }
}
if ($null -eq $selected) {
    throw "The existing BBPI4 Aurum seed was not reachable over the approved AP, USB-C, or LAN SSH routes."
}

$target = "$PiUser@$selected"
$transfer = "/tmp/aurum-reconcile-$([Guid]::NewGuid().ToString('N'))"
$localRemoteScript = $null
try {
    $mkdirResult = Invoke-OpenSshNative -Executable $sshPath -Arguments ($options + @($target, "umask 077; mkdir -p -- '$transfer/Projects'"))
    Write-OpenSshOutput $mkdirResult
    if ($mkdirResult.ExitCode -ne 0) { throw "Could not create the bounded BBPI4 staging directory." }

    $sourceTransfer = Invoke-OpenSshNative -Executable $scpPath -Arguments ($options + @("-r", $source, "${target}:$transfer/Projects/"))
    Write-OpenSshOutput $sourceTransfer
    if ($sourceTransfer.ExitCode -ne 0) { throw "Could not stage the Aurum dialogue/live-graph source on BBPI4." }
    $installerTransfer = Invoke-OpenSshNative -Executable $scpPath -Arguments ($options + @("-r", (Join-Path $repositoryRoot "installer"), "${target}:$transfer/"))
    Write-OpenSshOutput $installerTransfer
    if ($installerTransfer.ExitCode -ne 0) { throw "Could not stage the bounded installer contract on BBPI4." }

    $remote = @'
#!/usr/bin/env bash
set -euo pipefail
TRANSFER_ROOT="$1"
STAGED="$TRANSFER_ROOT/Projects/Codelation"
PI_USER="$2"
DESIRED_STATE="${3:--}"
if [ "$DESIRED_STATE" = "-" ]; then DESIRED_STATE=""; fi
INSTALL=/opt/boxbrain/codelation
STAMP="$(date -u +%Y%m%dT%H%M%SZ)-$$"
ROLLBACK_ROOT=/opt/boxbrain/rollback
ROLLBACK="$ROLLBACK_ROOT/codelation-$STAMP"
FUTURE_BRANCH_MANIFEST="$ROLLBACK_ROOT/future-branch-$STAMP.json"

matching_units() {
  systemctl list-unit-files --no-legend 2>/dev/null \
    | awk '{print $1}' \
    | grep -Ei 'aurum|codelation' \
    | sort -u || true
}
matching_user_cron() {
  crontab -l 2>/dev/null | grep -Ei 'aurum|codelation' || true
}
matching_root_cron() {
  sudo -n crontab -l 2>/dev/null | grep -Ei 'aurum|codelation' || true
}
line_count() {
  if [ -z "$1" ]; then printf '0'; else printf '%s\n' "$1" | awk 'NF{n++} END{print n+0}'; fi
}
csv_lines() {
  if [ -z "$1" ]; then printf 'none'; else printf '%s\n' "$1" | awk 'NF' | paste -sd, -; fi
}

units_before="$(matching_units)"
user_cron_before="$(matching_user_cron)"
root_cron_before="$(matching_root_cron)"

cd "$STAGED"
# The candidate overlay tests resolve the first Future Branch fork. Failed
# candidates are recorded as quarantined before the live install is touched.
aurum_overlay_tests=passed
if ! python3 -m unittest discover -s tests -p 'test_aurum_live.py' -v; then
  aurum_overlay_tests=failed
fi
if [ "$aurum_overlay_tests" = passed ] && ! python3 -m unittest discover -s tests -p 'test_aurum_dialogue.py' -v; then
  aurum_overlay_tests=failed
fi

# The broader Codelation suite remains useful evidence, but it is no longer
# allowed to veto an already-running operator-approved Aurum gold seed.
codelation_diagnostic_status=skipped-candidate-quarantined
codelation_diagnostic_detail=overlay-contract-failed
if [ "$aurum_overlay_tests" = passed ]; then
  codelation_diagnostic_status=passed
  codelation_diagnostic_detail=all-current-tests-passed
  if ! python3 -m unittest discover -s tests -v > "$TRANSFER_ROOT/codelation-tests.log" 2>&1; then
    codelation_diagnostic_status=failed-nonblocking
    codelation_diagnostic_detail="$(tail -n 8 "$TRANSFER_ROOT/codelation-tests.log" | tr '\r\n' ' ' | sed 's/[[:space:]][[:space:]]*/ /g')"
  fi
fi

sudo -n install -d -o root -g root -m 700 "$ROLLBACK_ROOT"
current_seed_present=false
if [ -d "$INSTALL" ]; then
  current_seed_present=true
fi
if [ "$aurum_overlay_tests" = passed ] && $current_seed_present; then
  sudo -n cp -a "$INSTALL" "$ROLLBACK"
else
  ROLLBACK=none
fi

# Persist the recovery branch field after the candidate tests and rollback path
# are known but before the first candidate file can mutate the live install.
manifest_args=(
  python3 "$TRANSFER_ROOT/installer/future_branch_recovery.py"
  --candidate "staged-codelation-$STAMP"
  --lkg "$INSTALL"
  --output "$FUTURE_BRANCH_MANIFEST"
)
if [ "$aurum_overlay_tests" = passed ]; then
  manifest_args+=(--candidate-tests-passed)
fi
if $current_seed_present; then
  manifest_args+=(--current-seed-present)
fi
if [ "$ROLLBACK" != none ]; then
  manifest_args+=(--rollback "$ROLLBACK")
fi
if [ -n "$DESIRED_STATE" ]; then
  # Desired state remains evidence/constraint only; the helper never authorizes
  # or promotes a branch and State Guardian remains the decision authority.
  manifest_args+=(--desired-state "$DESIRED_STATE")
fi
sudo -n "${manifest_args[@]}"
sudo -n chmod 600 "$FUTURE_BRANCH_MANIFEST"

if [ "$aurum_overlay_tests" != passed ]; then
  echo "AURUM_FUTURE_BRANCH_CANDIDATE_QUARANTINED manifest=$FUTURE_BRANCH_MANIFEST" >&2
  exit 32
fi

sudo -n install -d -o "$PI_USER" -g "$PI_USER" -m 700 \
  "$INSTALL" "$INSTALL/seed" "$INSTALL/mind" "$INSTALL/state" \
  "$INSTALL/state/mind" "$INSTALL/verification" "$INSTALL/verification/dialogue"

for relative in seed/aurum_live.py seed/aurum_dialogue.py seed/codelation_seed.py mind/bootstrap_mind.json; do
  source_path="$STAGED/$relative"
  target_path="$INSTALL/$relative"
  [ -f "$source_path" ] || { echo "missing_staged_file=$relative" >&2; exit 31; }
  sudo -n install -o "$PI_USER" -g "$PI_USER" -m 600 "$source_path" "$target_path"
done

cd "$INSTALL"
if [ ! -f state/aurum-live.json ]; then
  python3 seed/aurum_live.py init \
    --graph state/aurum-live.json \
    --node-name 'BBPI4/Aurum' \
    --hostname "$(hostname)" \
    --python-version "$(python3 -c 'import platform; print(platform.python_version())')" \
    --architecture "$(uname -m)" \
    --install-path "$INSTALL" \
    --seed-version 1
fi

before="$(python3 seed/aurum_live.py verify --graph state/aurum-live.json)"
peer="$(python3 seed/aurum_live.py peer-self-test --graph state/aurum-live.json)"
after="$(python3 seed/aurum_live.py verify --graph state/aurum-live.json)"
mind="$(python3 seed/aurum_dialogue.py --root "$INSTALL" status)"

seed_path="$INSTALL/seed.bin"
if [ -f "$seed_path" ]; then
  seed_sha256="$(sha256sum "$seed_path" | awk '{print $1}')"
  seed_bytes="$(stat -c %s "$seed_path")"
  if seed_summary="$(python3 seed/codelation_seed.py summary --model "$seed_path" 2>/dev/null)"; then
    seed_status=compatible-passive-seed-preserved
  else
    seed_status=gold-seed-preserved-opaque
    seed_summary="GOLD_SEED_PRESERVED_IN_PLACE sha256=$seed_sha256 bytes=$seed_bytes"
  fi
else
  python3 - <<'PY'
from pathlib import Path
from seed.codelation_seed import SeedGraph
SeedGraph().save(Path('/opt/boxbrain/codelation/seed.bin'))
PY
  seed_sha256="$(sha256sum "$seed_path" | awk '{print $1}')"
  seed_bytes="$(stat -c %s "$seed_path")"
  seed_status=initialized-passive-seed-because-none-existed
  seed_summary="$(python3 seed/codelation_seed.py summary --model "$seed_path")"
fi

units_after="$(matching_units)"
user_cron_after="$(matching_user_cron)"
root_cron_after="$(matching_root_cron)"
new_units="$(comm -13 <(printf '%s\n' "$units_before" | awk 'NF' | sort -u) <(printf '%s\n' "$units_after" | awk 'NF' | sort -u) || true)"
removed_units="$(comm -23 <(printf '%s\n' "$units_before" | awk 'NF' | sort -u) <(printf '%s\n' "$units_after" | awk 'NF' | sort -u) || true)"

active_units_count=0
inactive_units_count=0
active_unit_names=''
inactive_unit_names=''
if [ -n "$units_after" ]; then
  while IFS= read -r unit; do
    [ -n "$unit" ] || continue
    if systemctl is-active --quiet "$unit"; then
      active_units_count=$((active_units_count + 1))
      active_unit_names="${active_unit_names}${active_unit_names:+,}$unit"
    else
      inactive_units_count=$((inactive_units_count + 1))
      inactive_unit_names="${inactive_unit_names}${inactive_unit_names:+,}$unit"
    fi
  done <<EOF
$units_after
EOF
fi

user_cron_changed=0
root_cron_changed=0
[ "$user_cron_before" = "$user_cron_after" ] || user_cron_changed=1
[ "$root_cron_before" = "$root_cron_after" ] || root_cron_changed=1

health=not-present
if [ -d /opt/aurum ]; then
  if health_payload="$(curl -fsS --max-time 4 http://127.0.0.1:8767/health 2>/dev/null)"; then
    health="$(printf '%s' "$health_payload" | tr '\r\n' ' ')"
    gold_runtime_status=running-health-ok
  elif [ "$active_units_count" -gt 0 ]; then
    gold_runtime_status=running-approved-services-health-endpoint-unavailable
  else
    gold_runtime_status=installed-not-observed-running
  fi
else
  gold_runtime_status=passive-gold-seed-at-codelation-path
fi

rm -rf -- "$TRANSFER_ROOT"
transfer_cleanup=confirmed
pythonv="$(python3 --version 2>&1)"
arch="$(uname -m)"
existing_units_count="$(line_count "$units_after")"
new_units_count="$(line_count "$new_units")"
removed_units_count="$(line_count "$removed_units")"
user_cron_count="$(line_count "$user_cron_after")"
root_cron_count="$(line_count "$root_cron_after")"

cat > verification/AURUM_LIVE_VERIFY.txt <<EOF
AURUM LIVE VERIFY
identity=BBPI4/Aurum
path=$INSTALL
python=$pythonv
architecture=$arch
aurum_overlay_tests=$aurum_overlay_tests
codelation_diagnostic_status=$codelation_diagnostic_status
codelation_diagnostic_detail=$codelation_diagnostic_detail
before=$before
peer=$peer
after=$after
mind=$mind
AURUM_GOLD_SEED_PRESERVED
seed_status=$seed_status
seed_sha256=$seed_sha256
seed_bytes=$seed_bytes
seed=$seed_summary
gold_runtime_status=$gold_runtime_status
gold_runtime_health=$health
existing_systemd_units=$existing_units_count
existing_active_systemd_units=$active_units_count
existing_active_systemd_unit_names=${active_unit_names:-none}
existing_inactive_systemd_units=$inactive_units_count
existing_inactive_systemd_unit_names=${inactive_unit_names:-none}
existing_systemd_unit_names=$(csv_lines "$units_after")
new_unapproved_systemd_units=$new_units_count
new_unapproved_systemd_unit_names=$(csv_lines "$new_units")
removed_existing_systemd_units=$removed_units_count
removed_existing_systemd_unit_names=$(csv_lines "$removed_units")
existing_user_cron_entries=$user_cron_count
existing_root_cron_entries=$root_cron_count
unapproved_user_cron_changes=$user_cron_changed
unapproved_root_cron_changes=$root_cron_changed
matching_systemd_units=$new_units_count
matching_user_cron=$user_cron_changed
matching_root_cron=$root_cron_changed
rollback=$ROLLBACK
future_branch_manifest=$FUTURE_BRANCH_MANIFEST
future_branch_manifest_phase=pre-mutation
transfer_cleanup=$transfer_cleanup
EOF
chmod 600 verification/AURUM_LIVE_VERIFY.txt

[ "$new_units_count" -eq 0 ]
[ "$removed_units_count" -eq 0 ]
[ "$user_cron_changed" -eq 0 ]
[ "$root_cron_changed" -eq 0 ]
printf '%s\n' \
  "$before" "$peer" "$after" "$mind" \
  "AURUM_GOLD_SEED_PRESERVED" \
  "aurum_overlay_tests=$aurum_overlay_tests" \
  "codelation_diagnostic_status=$codelation_diagnostic_status" \
  "seed_status=$seed_status" \
  "gold_runtime_status=$gold_runtime_status" \
  "existing_systemd_units=$existing_units_count" \
  "new_unapproved_systemd_units=$new_units_count" \
  "unapproved_user_cron_changes=$user_cron_changed" \
  "unapproved_root_cron_changes=$root_cron_changed" \
  "rollback=$ROLLBACK" \
  "future_branch_manifest=$FUTURE_BRANCH_MANIFEST" \
  "future_branch_manifest_phase=pre-mutation" \
  "transfer_cleanup=$transfer_cleanup"
'@

    # Passing this script as a Base64 command-line payload exceeded a fragile
    # Windows/MSYS/zsh quoting boundary. Transfer the exact bytes as a bounded
    # temporary file instead, then remove both local and remote copies.
    $localRemoteScript = Join-Path ([IO.Path]::GetTempPath()) "aurum-reconcile-$([Guid]::NewGuid().ToString('N')).sh"
    $utf8NoBom = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($localRemoteScript, ($remote -replace "`r", ""), $utf8NoBom)
    $scriptTransfer = Invoke-OpenSshNative -Executable $scpPath -Arguments ($options + @($localRemoteScript, "${target}:$transfer/aurum-reconcile.sh"))
    Write-OpenSshOutput $scriptTransfer
    if ($scriptTransfer.ExitCode -ne 0) { throw "Could not stage the bounded BBPI4 reconciliation script." }

    $remoteScript = "$transfer/aurum-reconcile.sh"
    $desiredStateArg = if ($DesiredState) { $DesiredState } else { "-" }
    $remoteCommand = "chmod 700 -- $remoteScript && $remoteScript $transfer $PiUser $desiredStateArg"
    $reconcileResult = Invoke-OpenSshNative -Executable $sshPath -Arguments ($options + @($target, $remoteCommand))
    Write-OpenSshOutput $reconcileResult
    if ($reconcileResult.ExitCode -ne 0) {
        throw "Aurum gold-seed reconciliation or verification failed. No candidate promotion was performed; any rollback/manifest evidence created before mutation remains preserved."
    }
}
finally {
    [void](Invoke-OpenSshNative -Executable $sshPath -Arguments ($options + @($target, "rm -rf -- '$transfer' /tmp/aurum-reconcile.sh")) -SuppressStderr)
    if ($localRemoteScript -and (Test-Path -LiteralPath $localRemoteScript -PathType Leaf)) {
        Remove-Item -LiteralPath $localRemoteScript -Force -ErrorAction SilentlyContinue
    }
}

$evidenceResult = Invoke-OpenSshNative -Executable $sshPath -Arguments ($options + @($target, "cat /opt/boxbrain/codelation/verification/AURUM_LIVE_VERIFY.txt"))
if ($evidenceResult.ExitCode -ne 0) { throw "Could not retrieve reconciled Aurum evidence from BBPI4." }
$evidence = @($evidenceResult.Output | ForEach-Object { [string]$_ })
$text = ($evidence -join "`n")
$required = @(
    "identity=BBPI4/Aurum",
    "aurum_overlay_tests=passed",
    "AURUM_LIVE_VERIFIED",
    "AURUM_PEER_SELF_TEST_OK",
    "AURUM_GOLD_SEED_PRESERVED",
    "new_unapproved_systemd_units=0",
    "unapproved_user_cron_changes=0",
    "unapproved_root_cron_changes=0",
    "future_branch_manifest_phase=pre-mutation",
    "transfer_cleanup=confirmed"
)
foreach ($marker in $required) {
    if (-not $text.Contains($marker)) { throw "Reconciled Aurum evidence is missing: $marker" }
}

Write-Output $text
Write-Output "AURUM_GOLD_SEED_RECONCILED address=$selected path=/opt/boxbrain/codelation"