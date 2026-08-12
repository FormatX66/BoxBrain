#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
$git = (Get-Command git.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
& $git -C $root checkout main
if ($LASTEXITCODE -ne 0) { throw "Could not select BoxBrain main." }
& $git -C $root pull --ff-only
if ($LASTEXITCODE -ne 0) { throw "Could not refresh BoxBrain main." }

$installer = Join-Path $root "installer\install-aurum-local-lane.ps1"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer -RepositoryRoot $root -ApproveAurumLane -StartNow
if ($LASTEXITCODE -ne 0) { throw "Aurum local lane installation failed." }

Write-Host "AURUM_LANE_READY - queued BBPI4 deploy will run locally and publish its result to Git."
