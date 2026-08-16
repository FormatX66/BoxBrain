#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$OutputDirectory = 'evidence',
    [string]$RunTag = $env:GITHUB_RUN_ID,
    [string]$ExpectedHostKeyFingerprint = 'SHA256:X3DUtYg6vgC0krGnD2iQAi/CJfkMHKWB9avM6gXUDXY',
    [string]$PiUser = 'kali',
    [string]$KeyPath = (Join-Path $HOME '.ssh\boxbrain_pi_ed25519')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-NativeCaptured {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$Arguments
    )
    $old = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = @(& $FilePath @Arguments 2>&1)
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $old
    }
    [pscustomobject]@{ ExitCode = $code; Output = $output }
}

if ([string]::IsNullOrWhiteSpace($RunTag)) {
    $RunTag = [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssZ')
}
if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
    throw "Dedicated BoxBrain Pi SSH key is missing: $KeyPath"
}

$ssh = (Get-Command ssh.exe -CommandType Application -ErrorAction Stop).Source
$scp = (Get-Command scp.exe -CommandType Application -ErrorAction Stop).Source
$keyscan = (Get-Command ssh-keyscan.exe -CommandType Application -ErrorAction Stop).Source
$keygen = (Get-Command ssh-keygen.exe -CommandType Application -ErrorAction Stop).Source

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$logPath = Join-Path $OutputDirectory 'bbpi4-single-driver-trial.txt'

$candidates = @(
    [pscustomobject]@{ Address = '10.12.194.1'; Route = 'usb-c' },
    [pscustomobject]@{ Address = '10.42.194.1'; Route = 'bbpi4-ap' },
    [pscustomobject]@{ Address = '192.168.0.194'; Route = 'lan' }
)

$selected = $null
$selectedHostLine = $null
foreach ($candidate in $candidates) {
    $reachable = $false
    try {
        $reachable = Test-NetConnection -ComputerName $candidate.Address -Port 22 -InformationLevel Quiet -WarningAction SilentlyContinue
    }
    catch {
        $reachable = $false
    }
    Write-Host "AURUM_PI4_DRIVER_ROUTE route=$($candidate.Route) address=$($candidate.Address) tcp22=$reachable"
    if (-not $reachable) { continue }

    $scan = Invoke-NativeCaptured -FilePath $keyscan -Arguments @('-T','4','-t','ed25519',$candidate.Address)
    $hostLines = @($scan.Output | Where-Object {
        -not [string]::IsNullOrWhiteSpace([string]$_) -and -not ([string]$_).StartsWith('#')
    })
    if ($scan.ExitCode -ne 0 -or $hostLines.Count -eq 0) {
        Write-Host "AURUM_PI4_DRIVER_ROUTE route=$($candidate.Route) address=$($candidate.Address) host_key=missing"
        continue
    }

    $tempKey = Join-Path $env:TEMP ('bbpi4-single-driver-hostkey-' + [Guid]::NewGuid().ToString('N'))
    try {
        [IO.File]::WriteAllLines($tempKey, @([string]$hostLines[0]), [Text.Encoding]::ASCII)
        $fingerprint = Invoke-NativeCaptured -FilePath $keygen -Arguments @('-lf',$tempKey,'-E','sha256')
        $match = [regex]::Match(($fingerprint.Output -join ' '), 'SHA256:[A-Za-z0-9+/=]+')
        $verified = $match.Success -and $match.Value -eq $ExpectedHostKeyFingerprint
        $observed = if ($match.Success) { $match.Value } else { 'unreadable' }
        Write-Host "AURUM_PI4_DRIVER_ROUTE route=$($candidate.Route) address=$($candidate.Address) fingerprint=$observed verified=$verified"
        if ($null -eq $selected -and $verified) {
            $selected = $candidate
            $selectedHostLine = [string]$hostLines[0]
        }
    }
    finally {
        Remove-Item -LiteralPath $tempKey -Force -ErrorAction SilentlyContinue
    }
}

if ($null -eq $selected -or [string]::IsNullOrWhiteSpace($selectedHostLine)) {
    throw 'No reachable route presented the approved BBPI4 ED25519 host key.'
}

$sshDirectory = Join-Path $HOME '.ssh'
New-Item -ItemType Directory -Force -Path $sshDirectory | Out-Null
$knownHosts = Join-Path $sshDirectory 'known_hosts'
if (Test-Path -LiteralPath $knownHosts -PathType Leaf) {
    Invoke-NativeCaptured -FilePath $keygen -Arguments @('-R',$selected.Address,'-f',$knownHosts) | Out-Null
}
[IO.File]::AppendAllLines($knownHosts, @($selectedHostLine), [Text.Encoding]::ASCII)
Write-Host "AURUM_PI4_DRIVER_ROUTE_SELECTED route=$($selected.Route) address=$($selected.Address) host_key=verified"

$repoRoot = Split-Path -Parent $PSScriptRoot
$generator = Join-Path $repoRoot 'Projects\Codelation\pi4_driver_synthesizer.py'
$trial = Join-Path $repoRoot 'Projects\Codelation\run_pi4_single_driver_trial.sh'
if (-not (Test-Path -LiteralPath $generator -PathType Leaf)) { throw "Missing synthesizer: $generator" }
if (-not (Test-Path -LiteralPath $trial -PathType Leaf)) { throw "Missing trial script: $trial" }

$target = "$PiUser@$($selected.Address)"
$remoteRoot = "/tmp/aurum-pi4-single-driver-$RunTag"
$sshBase = @(
    '-i',$KeyPath,
    '-o','BatchMode=yes',
    '-o','IdentitiesOnly=yes',
    '-o','StrictHostKeyChecking=yes',
    '-o','ConnectTimeout=6'
)

try {
    $mkdir = Invoke-NativeCaptured -FilePath $ssh -Arguments ($sshBase + @($target,"rm -rf '$remoteRoot' && mkdir -p '$remoteRoot'"))
    if ($mkdir.ExitCode -ne 0) {
        throw "Could not create bounded BBPI4 trial directory: $($mkdir.Output -join ' ')"
    }

    $copyGenerator = Invoke-NativeCaptured -FilePath $scp -Arguments @(
        '-i',$KeyPath,'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes',
        $generator,"${target}:$remoteRoot/pi4_driver_synthesizer.py"
    )
    if ($copyGenerator.ExitCode -ne 0) { throw "Failed to stage Aurum driver synthesizer: $($copyGenerator.Output -join ' ')" }

    $copyTrial = Invoke-NativeCaptured -FilePath $scp -Arguments @(
        '-i',$KeyPath,'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes',
        $trial,"${target}:$remoteRoot/run_pi4_single_driver_trial.sh"
    )
    if ($copyTrial.ExitCode -ne 0) { throw "Failed to stage Aurum driver trial: $($copyTrial.Output -join ' ')" }

    $remoteCommand = "cd '$remoteRoot' && chmod +x run_pi4_single_driver_trial.sh && AURUM_RUN_TAG='$RunTag' ./run_pi4_single_driver_trial.sh ./pi4_driver_synthesizer.py"
    $run = Invoke-NativeCaptured -FilePath $ssh -Arguments ($sshBase + @($target,$remoteCommand))
    @($run.Output) | Set-Content -Encoding UTF8 $logPath
    $run.Output | ForEach-Object { Write-Host ([string]$_) }
    if ($run.ExitCode -ne 0) {
        throw "BBPI4 single-driver trial failed with exit code $($run.ExitCode)."
    }
}
finally {
    Invoke-NativeCaptured -FilePath $ssh -Arguments ($sshBase + @($target,"rm -rf '$remoteRoot'")) | Out-Null
}

Write-Host "AURUM_PI4_SINGLE_DRIVER_COMPLETE route=$($selected.Route) address=$($selected.Address) log=$logPath"
