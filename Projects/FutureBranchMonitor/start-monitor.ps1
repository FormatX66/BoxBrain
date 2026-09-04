$ErrorActionPreference = 'Stop'
$monitorRoot = $PSScriptRoot
try {
    $status = Invoke-RestMethod 'http://127.0.0.1:19467/api/status' -TimeoutSec 2
    if ($status.schema -eq 'aurum.future-branch.dashboard.v1') {
        Write-Output 'Future Branch monitor is already running.'
        exit 0
    }
    throw 'Port 19467 belongs to another application.'
} catch {
    if (Get-NetTCPConnection -LocalPort 19467 -State Listen -ErrorAction SilentlyContinue) {
        throw 'Port 19467 is occupied; existing service was preserved.'
    }
}
$python = (Get-Command python -ErrorAction Stop).Source
$monitorScript = Join-Path $monitorRoot 'monitor.py'
if (-not (Test-Path -LiteralPath $monitorScript -PathType Leaf)) { throw 'Monitor script missing.' }
$process = Start-Process -FilePath $python -ArgumentList @(('"{0}"' -f $monitorScript), 'serve') -WorkingDirectory $monitorRoot -WindowStyle Hidden -PassThru
$deadline = (Get-Date).AddSeconds(10)
do {
    Start-Sleep -Milliseconds 250
    try { $status = Invoke-RestMethod 'http://127.0.0.1:19467/api/status' -TimeoutSec 1 } catch { $status = $null }
} until (($status -and $status.schema -eq 'aurum.future-branch.dashboard.v1') -or (Get-Date) -ge $deadline)
if (-not $status) { throw "Monitor did not become ready; process ID $($process.Id)." }
Write-Output "Future Branch monitor ready at http://127.0.0.1:19467 (process $($process.Id))."
