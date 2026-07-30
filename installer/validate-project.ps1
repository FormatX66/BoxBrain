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
$edgeAgentDirectory = Join-Path $repositoryRoot "edge\kali-pi-agent"
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
    $previousErrorAction = $ErrorActionPreference
    try {
        # Native tools such as Python unittest legitimately write successful
        # progress to stderr. Capture both streams and use the process exit code
        # as the validation boundary instead of PowerShell's stream promotion.
        $ErrorActionPreference = "Continue"
        $output = & $FilePath @Arguments 2>&1
        $exitCode = $LASTEXITCODE
        $output | ForEach-Object {
            $line = if ($_ -is [Management.Automation.ErrorRecord]) {
                $_.Exception.Message
            }
            else {
                [string]$_
            }
            if (-not [string]::IsNullOrWhiteSpace($line)) {
                Write-Host $line
            }
        }
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
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
    -Name "Pi console Windows tests" `
    -WorkingDirectory $repositoryRoot `
    -FilePath "powershell.exe" `
    -Arguments @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        (Join-Path $PSScriptRoot "test-pi-console-scripts.ps1")
    )

Invoke-ValidationStep `
    -Name "Backend tests" `
    -WorkingDirectory $controllerDirectory `
    -FilePath $python `
    -Arguments @("-m", "pytest", "-q")

Invoke-ValidationStep `
    -Name "Kali Pi edge-agent tests" `
    -WorkingDirectory $edgeAgentDirectory `
    -FilePath $python `
    -Arguments @("-m", "unittest", "discover", "-s", "tests", "-v")

Invoke-ValidationStep `
    -Name "Flutter package resolution" `
    -WorkingDirectory $uiDirectory `
    -FilePath "flutter" `
    -Arguments @("pub", "get")

Invoke-ValidationStep `
    -Name "Flutter analysis" `
    -WorkingDirectory $uiDirectory `
    -FilePath "flutter" `
    -Arguments @("analyze", "--no-pub")

Invoke-ValidationStep `
    -Name "Flutter tests" `
    -WorkingDirectory $uiDirectory `
    -FilePath "flutter" `
    -Arguments @("test", "--no-pub")

if ($Mode -eq "Full") {
    Invoke-ValidationStep `
        -Name "Flutter web build" `
        -WorkingDirectory $uiDirectory `
        -FilePath "flutter" `
        -Arguments @(
            "build",
            "web",
            "--release",
            "--no-pub",
            "--dart-define=BOXBRAIN_API_URL=http://127.0.0.1:8000"
        )
}

Write-Host ""
Write-Host "[ready] BoxBrain $Mode validation passed."
$results | Format-Table -AutoSize
