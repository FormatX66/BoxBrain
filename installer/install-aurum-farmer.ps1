#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "BoxBrain\AurumFarmer"),
    [string]$TaskName = "Aurum Farmer",
    [switch]$SkipStart,
    [switch]$ForceEmbeddedPython
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$sourceRoot = Join-Path $repositoryRoot "Projects\AurumFarmer"
$sourceCommit = (& git -C $repositoryRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($sourceCommit)) {
    throw "Could not resolve the BoxBrain source commit."
}

$releaseId = "{0}-{1}" -f (Get-Date -Format "yyyyMMddHHmmss"), $sourceCommit.Substring(0, 12)
$releaseRoot = Join-Path $InstallRoot (Join-Path "releases" $releaseId)
$runtimeRoot = Join-Path $InstallRoot "runtime"
$configPath = Join-Path $runtimeRoot "farmer.json"
$receiptPath = Join-Path $runtimeRoot "install-receipt.json"

New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $sourceRoot "aurum_farmer") -Destination $releaseRoot -Recurse
Copy-Item -LiteralPath (Join-Path $sourceRoot "tests") -Destination $releaseRoot -Recurse

function Test-PythonCandidate {
    param([Parameter(Mandatory=$true)][string]$Path)
    try {
        $null = & $Path -c "import sys; assert sys.version_info >= (3, 10)"
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

$python = $null
$pythonRuntime = "system"
if (-not $ForceEmbeddedPython.IsPresent) {
    $candidate = Get-Command python.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($candidate -and (Test-PythonCandidate -Path $candidate.Source)) {
        $python = $candidate.Source
    }
}

if (-not $python) {
    # Farmer must be installable on a clean Windows node without a pre-existing
    # Python installation. Keep the interpreter release-local and checksum-pinned
    # so the deployment remains reversible and prior releases remain intact.
    $pythonRuntime = "embedded"
    $pythonVersion = "3.13.15"
    $pythonArchiveSha256 = "d1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf"
    $pythonArchiveUrl = "https://www.python.org/ftp/python/$pythonVersion/python-$pythonVersion-embed-amd64.zip"
    $cacheRoot = Join-Path $InstallRoot "cache"
    $archivePath = Join-Path $cacheRoot "python-$pythonVersion-embed-amd64.zip"
    $pythonRoot = Join-Path $releaseRoot "python"
    New-Item -ItemType Directory -Path $cacheRoot -Force | Out-Null

    $cacheValid = $false
    if (Test-Path -LiteralPath $archivePath -PathType Leaf) {
        $cacheHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
        $cacheValid = $cacheHash -eq $pythonArchiveSha256
    }
    if (-not $cacheValid) {
        $partial = "$archivePath.partial"
        Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $pythonArchiveUrl -OutFile $partial -UseBasicParsing
        $downloadHash = (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($downloadHash -ne $pythonArchiveSha256) {
            Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
            throw "Embedded Python archive checksum mismatch."
        }
        Move-Item -LiteralPath $partial -Destination $archivePath -Force
    }

    New-Item -ItemType Directory -Path $pythonRoot -Force | Out-Null
    Expand-Archive -LiteralPath $archivePath -DestinationPath $pythonRoot -Force
    $pth = Get-ChildItem -LiteralPath $pythonRoot -Filter "python*._pth" -File | Select-Object -First 1
    if (-not $pth) { throw "Embedded Python path file is missing." }
    $pthLines = @(Get-Content -LiteralPath $pth.FullName)
    if ($pthLines -notcontains "..") {
        $pthLines += ".."
        Set-Content -LiteralPath $pth.FullName -Value $pthLines -Encoding ascii
    }
    $python = Join-Path $pythonRoot "python.exe"
    if (-not (Test-Path -LiteralPath $python -PathType Leaf) -or -not (Test-PythonCandidate -Path $python)) {
        throw "Embedded Python runtime failed validation."
    }
}

$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = $releaseRoot
    & $python -m unittest discover -s (Join-Path $releaseRoot "tests") -v
    if ($LASTEXITCODE -ne 0) { throw "Installed Farmer release tests failed." }
    & $python -m aurum_farmer --config $configPath init --root $runtimeRoot | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Farmer runtime initialization failed." }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}

$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$identity = "{0}\{1}" -f $env:USERDOMAIN, $env:USERNAME
foreach ($secretPath in @([string]$config.api_token_path, [string]$config.signing_key_path)) {
    if (-not (Test-Path -LiteralPath $secretPath -PathType Leaf)) {
        throw "Expected Farmer secret file is missing: $secretPath"
    }
    & icacls.exe $secretPath /inheritance:r /grant:r "${identity}:(F)" "SYSTEM:(F)" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not restrict Farmer secret ACL: $secretPath" }
}

$arguments = '-m aurum_farmer --config "{0}" daemon' -f $configPath
$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $releaseRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing -and $existing.State -eq "Running") {
    Stop-ScheduledTask -TaskName $TaskName
}
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings `
    -Description "Persistent Aurum/BoxBrain Farmer supervisor and watchdog." -Force | Out-Null

$healthy = $false
if (-not $SkipStart.IsPresent) {
    Start-ScheduledTask -TaskName $TaskName
    $deadline = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Milliseconds 500
        try {
            $health = Invoke-RestMethod -Method Get -Uri ("http://{0}:{1}/health" -f $config.api_host, $config.api_port) -TimeoutSec 2
            $healthy = $health.status -eq "healthy" -and $health.event_chain_valid -eq $true
        }
        catch {
            $healthy = $false
        }
    } until ($healthy -or (Get-Date) -ge $deadline)
    if (-not $healthy) { throw "Aurum Farmer task started but the loopback health gate did not pass." }
}

$task = Get-ScheduledTask -TaskName $TaskName
$receipt = [ordered]@{
    schema = "aurum.farmer.install-receipt.v1"
    installed_at = (Get-Date).ToUniversalTime().ToString("o")
    source_commit = $sourceCommit
    release_root = $releaseRoot
    runtime_root = $runtimeRoot
    python_exe = $python
    python_runtime = $pythonRuntime
    task_name = $TaskName
    task_state = [string]$task.State
    health_verified = $healthy
    previous_releases_preserved = $true
}
$receipt | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $receiptPath -Encoding utf8
$receipt | ConvertTo-Json -Depth 4
