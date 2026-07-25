#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet("Quick", "Full")]
    [string]$Mode = "Quick"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$controllerDirectory = Join-Path $repositoryRoot "controller"
$uiDirectory = Join-Path $repositoryRoot "ui"
$python = Join-Path $controllerDirectory ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Controller virtual environment is missing. Follow docs/DEVELOPMENT.md first."
}
if (-not (Get-Command flutter -ErrorAction SilentlyContinue)) {
    throw "Flutter is not available on PATH."
}

$results = [Collections.Generic.List[object]]::new()

function Invoke-ValidationStep {
    param(
        [Parameter(Mandatory)]
        [string]$Name,
        [Parameter(Mandatory)]
        [string]$WorkingDirectory,
        [Parameter(Mandatory)]
        [string]$FilePath,
        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    Write-Host "[running] $Name"
    $timer = [Diagnostics.Stopwatch]::StartNew()
    Push-Location $WorkingDirectory
    try {
        & $FilePath @Arguments
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
        $timer.Stop()
    }
    if ($exitCode -ne 0) {
        throw "$Name failed with exit code $exitCode."
    }
    $results.Add(
        [pscustomobject]@{
            Check = $Name
            Result = "passed"
            Seconds = [Math]::Round($timer.Elapsed.TotalSeconds, 1)
        }
    )
}

Invoke-ValidationStep `
    -Name "Backend tests" `
    -WorkingDirectory $controllerDirectory `
    -FilePath $python `
    -Arguments @("-m", "pytest", "-q")

Invoke-ValidationStep `
    -Name "Flutter analysis" `
    -WorkingDirectory $uiDirectory `
    -FilePath "flutter" `
    -Arguments @("analyze")

Invoke-ValidationStep `
    -Name "Flutter tests" `
    -WorkingDirectory $uiDirectory `
    -FilePath "flutter" `
    -Arguments @("test")

if ($Mode -eq "Full") {
    Invoke-ValidationStep `
        -Name "Flutter web build" `
        -WorkingDirectory $uiDirectory `
        -FilePath "flutter" `
        -Arguments @(
            "build",
            "web",
            "--release",
            "--dart-define=BOXBRAIN_API_URL=http://127.0.0.1:8000"
        )
}

Write-Host ""
Write-Host "[ready] BoxBrain $Mode validation passed."
$results | Format-Table -AutoSize
