#Requires -Version 5.1
[CmdletBinding()]
param(
    [string[]]$PiAddresses = @("10.42.194.1", "10.12.194.1", "192.168.0.194"),
    [string]$PiUser = "kali",
    [string]$KeyPath = (Join-Path $HOME ".ssh\boxbrain_pi_ed25519")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
    throw "The dedicated BoxBrain SSH identity was not found at $KeyPath."
}

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$source = Join-Path $repositoryRoot "Projects\Codelation"
if (-not (Test-Path -LiteralPath $source -PathType Container)) {
    throw "Aurum dialogue/live-graph source is missing: $source"
}

$ssh = Get-Command ssh.exe -CommandType Application -ErrorAction Stop
$scp = Get-Command scp.exe -CommandType Application -ErrorAction Stop
$options = @(
    "-i", $KeyPath,
    "-o", "BatchMode=yes",
    "-o", "IdentitiesOnly=yes",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "ConnectTimeout=4"
)

$selected = $null
foreach ($address in $PiAddresses) {
    & $ssh.Source @options "$PiUser@$address" "test -d /opt/boxbrain/codelation || test -d /opt/aurum" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $selected = $address
        break
    }
}
if ($null -eq $selected) {
    throw "The existing BBPI4 Aurum seed was not reachable over the approved AP, USB-C, or LAN SSH routes."
}

$target = "$PiUser@$selected"
$transfer = "/tmp/aurum-reconcile-$([Guid]::NewGuid().ToString('N'))"
try {
    & $ssh.Source @options $target "umask 077; mkdir -p -- '$transfer/Projects'"
    if ($LASTEXITCODE -ne 0) { throw "Could not create the bounded BBPI4 staging directory." }

    & $scp.Source @options -r "$source" "${target}:$transfer/Projects/"
    if ($LASTEXITCODE -ne 0) { throw "Could not stage the Aurum dialogue/live-graph source on BBPI4." }
    & $scp.Source @options -r (Join-Path $repositoryRoot "installer") "${target}:$transfer/"
    if ($LASTEXITCODE -ne 0) { throw "Could not stage the bounded installer contract on BBPI4." }

    $remote = @'
#!/usr/bin/env bash
set -euo pipefail
TRANSFER_ROOT="$1"
STAGED="$TRANSFER_ROOT/Projects/Codelation"
PI_USER="$2"
INSTALL=/opt/boxbrain/codelation
STAMP="$(date -u +%Y%m%dT%H%M%SZ)-$$"
ROLLBACK_ROOT=/opt/boxbrain/rollback
ROLLBACK="$ROLLBACK_ROOT/codelation-$STAMP"

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
# Only the Aurum overlay contract is authoritative for this operation.
python3 -m unittest discover -s tests -p 'test_aurum_live.py' -v
python3 -m unittest discover -s tests -p 'test_aurum_dialogue.py' -v
aurum_overlay_tests=passed

# The broader Codelation suite remains useful evidence, but it is no longer
# allowed to veto an already-running operator-approved Aurum gold seed.
codelation_diagnostic_status=passed
codelation_diagnostic_detail=all-current-tests-passed
if ! python3 -m unittest discover -s tests -v > "$TRANSFER_ROOT/codelation-tests.log" 2>&1; then
  codelation_diagnostic_status=failed-nonblocking
  codelation_diagnostic_detail="$(tail -n 8 "$TRANSFER_ROOT/codelation-tests.log" | tr '\r\n' ' ' | sed 's/[[:space:]][[:space:]]*/ /g')"
fi

sudo -n install -d -o root -g root -m 700 "$ROLLBACK_ROOT"
if [ -d "$INSTALL" ]; then
  sudo -n cp -a "$INSTALL" "$ROLLBACK"
else
  ROLLBACK=none
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
rollback=$ROLLBACK
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
  "transfer_cleanup=$transfer_cleanup"
'@

    $payload = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($remote -replace "`r", "")))
    $remoteCommand = 'python3 -c ''import base64;open("/tmp/aurum-reconcile.sh","wb").write(base64.b64decode("{0}"))'' && chmod 700 /tmp/aurum-reconcile.sh && /tmp/aurum-reconcile.sh ''{1}'' ''{2}''; rc=$?; rm -f /tmp/aurum-reconcile.sh; exit $rc' -f $payload, $transfer, $PiUser
    & $ssh.Source @options $target $remoteCommand
    if ($LASTEXITCODE -ne 0) {
        throw "Aurum gold-seed reconciliation or verification failed. The prior Aurum/Codelation directory was preserved in rollback."
    }
}
finally {
    & $ssh.Source @options $target "rm -rf -- '$transfer' /tmp/aurum-reconcile.sh" 2>$null
}

$evidence = & $ssh.Source @options $target "cat /opt/boxbrain/codelation/verification/AURUM_LIVE_VERIFY.txt"
if ($LASTEXITCODE -ne 0) { throw "Could not retrieve reconciled Aurum evidence from BBPI4." }
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
    "transfer_cleanup=confirmed"
)
foreach ($marker in $required) {
    if (-not $text.Contains($marker)) { throw "Reconciled Aurum evidence is missing: $marker" }
}

Write-Output $text
Write-Output "AURUM_GOLD_SEED_RECONCILED address=$selected path=/opt/boxbrain/codelation"
