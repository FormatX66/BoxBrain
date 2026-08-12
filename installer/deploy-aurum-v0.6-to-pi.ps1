#Requires -Version 5.1
[CmdletBinding()]
param(
    [string[]]$PiAddresses = @("10.42.194.1", "10.12.194.1", "192.168.0.194"),
    [string]$PiUser = "kali",
    [string]$KeyPath = (Join-Path $HOME ".ssh\boxbrain_pi_ed25519")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ExpectedSha256 = "b53f3ba3c87d9a78d3058edc02587f304a68d00e2860f6e83820a1f22b9bc142"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$artifactB64 = Join-Path $repositoryRoot "Projects\Aurum\Aurum_Seed_v0_6_EngineerLoop.zip.b64"
if (-not (Test-Path -LiteralPath $artifactB64 -PathType Leaf)) {
    throw "Aurum v0.6 artifact is missing: $artifactB64"
}
if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
    throw "The dedicated BoxBrain SSH identity was not found at $KeyPath."
}

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("aurum-deploy-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
$artifactZip = Join-Path $tempRoot "Aurum_Seed_v0_6_EngineerLoop.zip"
try {
    $encoded = [IO.File]::ReadAllText($artifactB64).Trim()
    [IO.File]::WriteAllBytes($artifactZip, [Convert]::FromBase64String($encoded))
    $actual = (Get-FileHash -LiteralPath $artifactZip -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $ExpectedSha256) { throw "Aurum artifact hash mismatch." }

    $ssh = Get-Command ssh.exe -ErrorAction Stop
    $scp = Get-Command scp.exe -ErrorAction Stop
    $options = @(
        "-i", $KeyPath,
        "-o", "BatchMode=yes",
        "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "ConnectTimeout=4"
    )

    $selected = $null
    foreach ($address in $PiAddresses) {
        & $ssh.Source @options "$PiUser@$address" "true" 2>$null
        if ($LASTEXITCODE -eq 0) { $selected = $address; break }
    }
    if ($null -eq $selected) { throw "BBPI4 was not reachable over the AP, USB-C, or LAN SSH routes." }

    $target = "$PiUser@$selected"
    $remoteZip = "/tmp/aurum-v0.6-$([Guid]::NewGuid().ToString('N')).zip"
    & $scp.Source @options $artifactZip "${target}:$remoteZip"
    if ($LASTEXITCODE -ne 0) { throw "Aurum transfer failed." }

    $remote = @'
set -eu
ZIP_PATH="$1"
EXPECTED_SHA="$2"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="/tmp/aurum-install-$STAMP-$$"
BACKUP_ROOT="/opt/boxbrain/backups"
BACKUP="$BACKUP_ROOT/aurum-$STAMP.tar.gz"
RESTORE_NEEDED=0
cleanup() { rm -rf -- "$WORK" "$ZIP_PATH"; }
rollback() {
  set +e
  systemctl stop aurum-boxbrain-peer.service aurum-engineer.service aurum-momentum.service aurum-relay.service >/dev/null 2>&1 || true
  if [ -f "$BACKUP" ]; then
    rm -rf /opt/aurum
    tar -xzf "$BACKUP" -C /
  fi
  systemctl daemon-reload >/dev/null 2>&1 || true
}
trap 'rc=$?; if [ "$rc" -ne 0 ] && [ "$RESTORE_NEEDED" -eq 1 ]; then rollback; fi; cleanup; exit "$rc"' EXIT INT TERM

ACTUAL_SHA="$(sha256sum "$ZIP_PATH" | awk '{print $1}')"
[ "$ACTUAL_SHA" = "$EXPECTED_SHA" ] || { echo 'artifact_hash_mismatch'; exit 20; }
mkdir -p "$WORK" "$BACKUP_ROOT"
chmod 700 "$WORK" "$BACKUP_ROOT"
python3 - <<PY "$ZIP_PATH" "$WORK"
import sys, zipfile
zip_path, work = sys.argv[1:]
with zipfile.ZipFile(zip_path) as z:
    for n in z.namelist():
        p = __import__('pathlib').PurePosixPath(n)
        if p.is_absolute() or '..' in p.parts:
            raise SystemExit('unsafe_zip_path')
    z.extractall(work)
PY
python3 -m py_compile "$WORK"/*.py

if [ -d /opt/aurum ]; then
  tar -czf "$BACKUP" -C / opt/aurum
  chmod 600 "$BACKUP"
fi
RESTORE_NEEDED=1

install -d -m 755 /opt/aurum
find /opt/aurum -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
cp -a "$WORK"/. /opt/aurum/
install -d -m 755 /opt/aurum/generated_adapters

python3 -m venv /opt/aurum/.venv
/opt/aurum/.venv/bin/python -m pip install --disable-pip-version-check -q -r /opt/aurum/requirements.txt

install -d -m 700 /etc/aurum
if [ ! -f /etc/aurum/aurum.env ]; then
  TOKEN="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)"
  cat > /etc/aurum/aurum.env <<ENV
AURUM_RELAY_TOKEN=$TOKEN
AURUM_RELAY_WS=ws://127.0.0.1:8767/peer
BOXBRAIN_URL=http://127.0.0.1:8000/api/v1
ENV
  chmod 600 /etc/aurum/aurum.env
fi

for unit in /opt/aurum/systemd/*.service; do
  install -m 644 "$unit" "/etc/systemd/system/$(basename "$unit")"
done
systemctl daemon-reload
systemctl enable --now aurum-relay.service aurum-momentum.service aurum-engineer.service aurum-boxbrain-peer.service

sleep 3
for unit in aurum-relay.service aurum-momentum.service aurum-engineer.service aurum-boxbrain-peer.service; do
  systemctl is-active --quiet "$unit" || { systemctl status --no-pager "$unit"; exit 30; }
done

HEALTH="$(curl -fsS http://127.0.0.1:8767/health)"
echo "$HEALTH" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("version")=="0.6" and d.get("status")=="ok", d'

set -a
. /etc/aurum/aurum.env
set +a
PEERS="$(curl -fsS -H "Authorization: Bearer $AURUM_RELAY_TOKEN" http://127.0.0.1:8767/peers)"
echo "$PEERS" | python3 -c 'import json,sys; p=json.load(sys.stdin); caps={c for x in p for c in x.get("capabilities",[])}; need={"system.identity","continuity.blocked","primitive.build"}; assert need <= caps, (need,caps)'

IDENTITY="$(curl -fsS -X POST -H "Authorization: Bearer $AURUM_RELAY_TOKEN" -H 'Content-Type: application/json' --data '{"want":"system.identity","args":{},"constraints":{"destructive":false}}' http://127.0.0.1:8767/intent)"
echo "$IDENTITY" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("status")=="done", d; assert d.get("result",{}).get("host"), d'

RESTORE_NEEDED=0
printf 'AURUM_DEPLOY_OK\nversion=0.6\nroute=%s\nhealth=%s\npeers=%s\nidentity=%s\n' "$SSH_CONNECTION" "$HEALTH" "$PEERS" "$IDENTITY"
'@

    $remoteScript = $remote.Replace("`r", "")
    $payload = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remoteScript))
    $command = "python3 -c 'import base64;open(\"/tmp/aurum-deploy.sh\",\"wb\").write(base64.b64decode(\"$payload\"))' && chmod 700 /tmp/aurum-deploy.sh && sudo -n /tmp/aurum-deploy.sh '$remoteZip' '$ExpectedSha256'; rc=`$?; rm -f /tmp/aurum-deploy.sh; exit `$rc"
    & $ssh.Source @options $target $command
    if ($LASTEXITCODE -ne 0) { throw "Aurum deployment or verification failed; remote rollback was attempted." }

    Write-Output "AURUM_DEPLOY_VERIFIED target=$selected version=0.6 artifact_sha256=$ExpectedSha256"
}
finally {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
