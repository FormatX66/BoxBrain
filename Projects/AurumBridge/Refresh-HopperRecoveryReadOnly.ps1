[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$OutputPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ssh = (Get-Command ssh.exe -ErrorAction Stop).Source
$keyscan = (Get-Command ssh-keyscan.exe -ErrorAction Stop).Source
$keys = @(
    (Join-Path $env:USERPROFILE '.ssh\boxbrain_pi_ed25519'),
    'C:\Users\Bruce\.ssh\boxbrain_pi_ed25519',
    'C:\Users\bruce\.ssh\boxbrain_pi_ed25519'
)
$keys += @(Get-ChildItem 'C:\Users' -Directory -ErrorAction SilentlyContinue | ForEach-Object {
    Join-Path $_.FullName '.ssh\boxbrain_pi_ed25519'
})
$key = $keys | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $key) {
    throw 'AURUM_HOPPER_RECOVERY_REFRESH_REFUSED reason=dedicated-boxbrain-key-unavailable'
}

$targets = @(
    'boxbrain.local',
    'bbpi4.local',
    'aurum-pi4.local',
    '10.42.194.1',
    '10.12.194.1',
    '192.168.0.194'
)
$selected = $null
$output = @()

foreach ($target in $targets) {
    $knownHosts = Join-Path $env:TEMP ('aurum-readonly-recovery-' + [Guid]::NewGuid().ToString('N') + '.known_hosts')
    $scanErr = $knownHosts + '.err'
    $saved = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        [void](Start-Process -FilePath $keyscan -ArgumentList @('-T','2','-t','ed25519',$target) -NoNewWindow -Wait -PassThru -RedirectStandardOutput $knownHosts -RedirectStandardError $scanErr)
    } finally {
        $ErrorActionPreference = $saved
    }
    Remove-Item $scanErr -Force -ErrorAction SilentlyContinue
    $hostKeys = @((Get-Content $knownHosts -ErrorAction SilentlyContinue) | Where-Object {
        $_ -and -not ([string]$_).StartsWith('#')
    })
    if ($hostKeys.Count -eq 0) {
        Remove-Item $knownHosts -Force -ErrorAction SilentlyContinue
        continue
    }

    $remote = @'
set -u
echo AURUM_HOPPER_RECOVERY_READONLY_REFRESH
echo "pi_host=$(hostname)"
H=""
for h in hopper hopper.local pc-01 pc-01.local 10.12.194.5; do
  if getent ahostsv4 "$h" >/dev/null 2>&1 || [ "$h" = "10.12.194.5" ]; then H="$h"; break; fi
done
echo "hopper_candidate=$H"
if [ -z "$H" ]; then
  echo "hopper_resolved=false"
  echo "remote_repair=unavailable"
  exit 0
fi
echo "hopper_resolved=true"
if timeout 3 bash -c "</dev/tcp/$H/22" 2>/dev/null; then echo "ssh_port_22=open"; else echo "ssh_port_22=closed"; fi
for spec in 8768/status 8767/proof 8765/api/status; do
  port="${spec%%/*}"; path="/${spec#*/}"
  code="$(curl -sS --connect-timeout 2 --max-time 4 -o /tmp/aurum-readonly-probe-body -w '%{http_code}' "http://$H:$port$path" 2>/dev/null || true)"
  echo "http_${port}=${code:-000}"
done
rm -f /tmp/aurum-readonly-probe-body
echo "remote_repair=unavailable"
'@

    $saved = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $lines = @(& $ssh -i $key -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=6 -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$knownHosts" "kali@$target" $remote 2>&1)
        $exit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $saved
        Remove-Item $knownHosts -Force -ErrorAction SilentlyContinue
    }
    if ($exit -eq 0) {
        $selected = $target
        $output = $lines
        break
    }
}

$kv = @{}
if ($selected) {
    foreach ($line in $output) {
        if ($line -match '^([^=]+)=(.*)$') {
            $kv[$Matches[1]] = $Matches[2]
        }
    }
}
$hopperResolved = ($kv['hopper_resolved'] -eq 'true')
$terminalReason = if (-not $selected) {
    'boxbrain-unreachable'
} else {
    'authorized-recovery-unavailable'
}

$payload = [ordered]@{
    schema = 'aurum.hopper.recovery-path-probe.v2'
    observed_at = [DateTime]::UtcNow.ToString('o')
    runner_host = $env:COMPUTERNAME
    boxbrain_address = $selected
    hopper_candidate = $kv['hopper_candidate']
    hopper_resolved = $hopperResolved
    ssh_port_22 = $kv['ssh_port_22']
    ssh_host_key = if ($selected) { 'pi-strict-host-key-verified' } else { $null }
    ssh_authorized_user = $null
    self_debug_8768 = $kv['http_8768']
    echo_proof_8767 = $kv['http_8767']
    gui_8765 = $kv['http_8765']
    remote_repair = 'unavailable'
    terminal_reason = $terminalReason
    read_only_probe = $true
    mutation_if_authorized = 'none-read-only-refresh'
}

$directory = Split-Path -Parent $OutputPath
if ($directory) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}
$json = $payload | ConvertTo-Json -Depth 6
[IO.File]::WriteAllText($OutputPath, $json + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
Write-Host "AURUM_HOPPER_RECOVERY_REFRESH_OK terminal_reason=$terminalReason remote_repair=unavailable output=$OutputPath"
