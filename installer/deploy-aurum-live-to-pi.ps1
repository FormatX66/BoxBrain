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

$ssh = Get-Command ssh.exe -ErrorAction Stop
$scp = Get-Command scp.exe -ErrorAction Stop
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$source = Join-Path $repositoryRoot "Projects\Codelation"
if (-not (Test-Path -LiteralPath $source -PathType Container)) {
    throw "Codelation source is missing: $source"
}

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
    if ($LASTEXITCODE -eq 0) {
        $selected = $address
        break
    }
}
if ($null -eq $selected) {
    throw "BBPI4 was not reachable over the AP, USB-C, or LAN SSH routes."
}

$target = "$PiUser@$selected"
$transfer = "/tmp/aurum-live-$([Guid]::NewGuid().ToString('N'))"
$cleanup = "rm -rf -- '$transfer'"
try {
    & $ssh.Source @options $target "umask 077; mkdir -p -- '$transfer'"
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Pi transfer directory." }

    & $scp.Source @options -r "$source\*" "${target}:$transfer/"
    if ($LASTEXITCODE -ne 0) { throw "Aurum live transfer failed." }

    $install = @"
set -eu
cd '$transfer'
python3 -m unittest discover -s tests -v
stamp=`$(date -u +%Y%m%dT%H%M%SZ)
rollback="/opt/boxbrain/rollback/codelation-`$stamp"
if [ -d /opt/boxbrain/codelation ]; then
  sudo -n install -d -o root -g root -m 700 /opt/boxbrain/rollback
  sudo -n cp -a /opt/boxbrain/codelation "`$rollback"
fi
sudo -n install -d -o '$PiUser' -g '$PiUser' -m 700 /opt/boxbrain/codelation
sudo -n cp -a . /opt/boxbrain/codelation/
sudo -n chown -R '${PiUser}:${PiUser}' /opt/boxbrain/codelation
sudo -n chmod 700 /opt/boxbrain/codelation
cd /opt/boxbrain/codelation
mkdir -p state verification
chmod 700 state verification
if [ ! -f state/aurum-live.json ]; then
  python3 seed/aurum_live.py init \
    --graph state/aurum-live.json \
    --node-name 'BBPI4/Aurum' \
    --hostname "`$(hostname)" \
    --python-version "`$(python3 -c 'import platform; print(platform.python_version())')" \
    --architecture "`$(uname -m)" \
    --install-path /opt/boxbrain/codelation \
    --seed-version 1
fi
before=`$(python3 seed/aurum_live.py verify --graph state/aurum-live.json)
peer=`$(python3 seed/aurum_live.py peer-self-test --graph state/aurum-live.json)
after=`$(python3 seed/aurum_live.py verify --graph state/aurum-live.json)
mind=`$(python3 seed/aurum_dialogue.py --root /opt/boxbrain/codelation status)
seed=`$(python3 seed/codelation_seed.py summary --model seed.bin)
pythonv=`$(python3 --version 2>&1)
arch=`$(uname -m)
units=`$(systemctl list-unit-files --no-legend 2>/dev/null | grep -Eic 'aurum|codelation' || true)
usercron=`$(crontab -l 2>/dev/null | grep -Eic 'aurum|codelation' || true)
rootcron=`$(sudo -n crontab -l 2>/dev/null | grep -Eic 'aurum|codelation' || true)
cat > verification/AURUM_LIVE_VERIFY.txt <<EOF
AURUM LIVE VERIFY
identity=BBPI4/Aurum
path=/opt/boxbrain/codelation
python=`$pythonv
architecture=`$arch
before=`$before
peer=`$peer
after=`$after
mind=`$mind
seed=`$seed
matching_systemd_units=`$units
matching_user_cron=`$usercron
matching_root_cron=`$rootcron
rollback=`$rollback
EOF
chmod 600 verification/AURUM_LIVE_VERIFY.txt
printf '%s\n' "`$before" "`$peer" "`$after" "`$mind" "`$seed" "`$pythonv" "rollback=`$rollback" "matching_systemd_units=`$units" "matching_user_cron=`$usercron" "matching_root_cron=`$rootcron"
"@
    $install = $install -replace "`r", ""
    $install | & $ssh.Source @options $target "bash -s"
    if ($LASTEXITCODE -ne 0) { throw "Aurum live verification or installation failed." }
}
finally {
    & $ssh.Source @options $target $cleanup 2>$null
}

Write-Output "AURUM_LIVE_DEPLOYED address=$selected path=/opt/boxbrain/codelation"
