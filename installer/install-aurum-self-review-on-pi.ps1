#Requires -Version 5.1
[CmdletBinding()]
param(
    [string[]]$PiAddresses = @("10.12.194.1", "10.42.194.1", "192.168.0.194"),
    [string]$PiUser = "kali",
    [string]$KeyPath = (Join-Path $HOME ".ssh\boxbrain_pi_ed25519")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$source = Join-Path $repositoryRoot "Projects\Codelation\seed\aurum_self_review.py"
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "The bounded Aurum self-review supervisor is missing: $source"
}
if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
    throw "The dedicated BoxBrain SSH identity was not found at $KeyPath."
}

$expectedSha256 = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
$ssh = (Get-Command ssh.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$scp = (Get-Command scp.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$options = @(
    "-i", $KeyPath,
    "-o", "BatchMode=yes",
    "-o", "IdentitiesOnly=yes",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "ConnectTimeout=4"
)

$selected = $null
foreach ($address in $PiAddresses) {
    & $ssh @options "$PiUser@$address" "test -f /opt/boxbrain/codelation/seed/aurum_dialogue.py" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $selected = $address
        break
    }
}
if ($null -eq $selected) {
    throw "BBPI4 with the existing Aurum dialogue supervisor was not reachable over the approved USB-C, AP, or LAN SSH routes."
}

$target = "$PiUser@$selected"
$remoteSource = "/tmp/aurum-self-review-$([Guid]::NewGuid().ToString('N')).py"
& $scp @options $source "${target}:$remoteSource"
if ($LASTEXITCODE -ne 0) {
    throw "The bounded self-review supervisor transfer failed."
}

$remoteScript = @'
set -eu
SOURCE="$1"
EXPECTED_SHA="$2"
DEST="/opt/boxbrain/codelation/seed/aurum_self_review.py"
DIALOGUE="/opt/boxbrain/codelation/seed/aurum_dialogue.py"
BACKUP_DIR="/opt/boxbrain/codelation/verification/dialogue/supervisor-backups"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$BACKUP_DIR/aurum_self_review.py.$STAMP"
BACKUP_REPORT=none
HAD_PRIOR=0
INSTALLED=0
cleanup() { rm -f -- "$SOURCE"; }
rollback() {
  set +e
  if [ "$INSTALLED" -eq 1 ]; then
    if [ "$HAD_PRIOR" -eq 1 ] && [ -f "$BACKUP" ]; then
      sudo -n install -m 0644 "$BACKUP" "$DEST"
    else
      sudo -n rm -f -- "$DEST"
    fi
  fi
}
trap 'rc=$?; if [ "$rc" -ne 0 ]; then rollback; fi; cleanup; exit "$rc"' EXIT INT TERM

[ -f "$DIALOGUE" ] || { echo 'existing_dialogue_supervisor_missing'; exit 20; }
ACTUAL_SHA="$(sha256sum "$SOURCE" | awk '{print $1}')"
[ "$ACTUAL_SHA" = "$EXPECTED_SHA" ] || { echo 'self_review_hash_mismatch'; exit 21; }
python3 -m py_compile "$SOURCE"
sudo -n install -d -m 0700 "$BACKUP_DIR"
if [ -f "$DEST" ]; then
  HAD_PRIOR=1
  sudo -n cp -a "$DEST" "$BACKUP"
  BACKUP_REPORT="$BACKUP"
fi
sudo -n install -m 0644 "$SOURCE" "$DEST"
INSTALLED=1
sudo -n python3 -m py_compile "$DEST"
STATUS="$(cd /opt/boxbrain/codelation && python3 seed/aurum_self_review.py --root /opt/boxbrain/codelation status)"
INSTALLED=0
printf 'AURUM_SELF_REVIEW_SUPERVISOR_INSTALLED\nsha256=%s\nstatus=%s\nbackup=%s\n' "$ACTUAL_SHA" "$STATUS" "$BACKUP_REPORT"
'@

$payload = [Convert]::ToBase64String(
    [Text.Encoding]::UTF8.GetBytes($remoteScript.Replace("`r", ""))
)
$command = "python3 -c 'import base64;open(\"/tmp/aurum-self-review-install.sh\",\"wb\").write(base64.b64decode(\"$payload\"))' && chmod 700 /tmp/aurum-self-review-install.sh && /tmp/aurum-self-review-install.sh '$remoteSource' '$expectedSha256'; rc=`$?; rm -f /tmp/aurum-self-review-install.sh; exit `$rc"
& $ssh @options $target $command
if ($LASTEXITCODE -ne 0) {
    throw "The iterative self-review supervisor failed verification; the previous supervisor state was restored when present."
}

Write-Output "AURUM_SELF_REVIEW_INSTALL_VERIFIED address=$selected sha256=$expectedSha256"
