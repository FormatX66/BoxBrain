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
$keygen = (Get-Command ssh-keygen.exe -CommandType Application -ErrorAction Stop).Source
$knownHosts = Join-Path (Join-Path $HOME '.ssh') 'known_hosts'
if (-not (Test-Path -LiteralPath $knownHosts -PathType Leaf)) {
    throw "Approved SSH known_hosts store is missing: $knownHosts"
}

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$logPath = Join-Path $OutputDirectory 'bbpi4-single-driver-trial.txt'

$candidates = @(
    [pscustomobject]@{ Address = '10.42.194.1'; Route = 'bbpi4-ap' },
    [pscustomobject]@{ Address = '10.12.194.1'; Route = 'usb-c' },
    [pscustomobject]@{ Address = '192.168.0.194'; Route = 'lan' }
)

$selected = $null
$sshBaseCommon = @(
    '-i',$KeyPath,
    '-o','BatchMode=yes',
    '-o','IdentitiesOnly=yes',
    '-o','StrictHostKeyChecking=yes',
    '-o','ConnectTimeout=6'
)

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

    $known = Invoke-NativeCaptured -FilePath $keygen -Arguments @('-F',$candidate.Address,'-f',$knownHosts)
    $knownKeyLines = @($known.Output | Where-Object {
        $text = [string]$_
        -not [string]::IsNullOrWhiteSpace($text) -and -not $text.StartsWith('#') -and $text -match '\s(ssh-ed25519|ecdsa-sha2-|ssh-rsa)\s'
    })
    if ($knownKeyLines.Count -eq 0) {
        Write-Host "AURUM_PI4_DRIVER_ROUTE route=$($candidate.Route) address=$($candidate.Address) trust=not_in_known_hosts"
        continue
    }

    $fingerprintVerified = $false
    foreach ($knownKeyLine in $knownKeyLines) {
        $tempKey = Join-Path $env:TEMP ('bbpi4-known-host-' + [Guid]::NewGuid().ToString('N'))
        try {
            [IO.File]::WriteAllLines($tempKey, @([string]$knownKeyLine), [Text.Encoding]::ASCII)
            $fingerprint = Invoke-NativeCaptured -FilePath $keygen -Arguments @('-lf',$tempKey,'-E','sha256')
            $match = [regex]::Match(($fingerprint.Output -join ' '), 'SHA256:[A-Za-z0-9+/=]+')
            if ($match.Success -and $match.Value -eq $ExpectedHostKeyFingerprint) {
                $fingerprintVerified = $true
                break
            }
        }
        finally {
            Remove-Item -LiteralPath $tempKey -Force -ErrorAction SilentlyContinue
        }
    }
    if (-not $fingerprintVerified) {
        Write-Host "AURUM_PI4_DRIVER_ROUTE route=$($candidate.Route) address=$($candidate.Address) trust=fingerprint_mismatch"
        continue
    }

    $identity = Invoke-NativeCaptured -FilePath $ssh -Arguments ($sshBaseCommon + @(
        "$PiUser@$($candidate.Address)",
        "tr -d '\000' </proc/device-tree/model 2>/dev/null || true"
    ))
    $model = ($identity.Output -join ' ').Trim()
    $isPi4 = $identity.ExitCode -eq 0 -and $model -match 'Raspberry Pi 4'
    Write-Host "AURUM_PI4_DRIVER_ROUTE route=$($candidate.Route) address=$($candidate.Address) trust=verified model_pi4=$isPi4"
    if ($isPi4) {
        $selected = $candidate
        break
    }
}

if ($null -eq $selected) {
    throw 'No approved strict-SSH route verified as the Raspberry Pi 4.'
}
Write-Host "AURUM_PI4_DRIVER_ROUTE_SELECTED route=$($selected.Route) address=$($selected.Address) trust=verified"

$repoRoot = Split-Path -Parent $PSScriptRoot
$generator = Join-Path $repoRoot 'Projects\Codelation\pi4_driver_synthesizer.py'
$trial = Join-Path $repoRoot 'Projects\Codelation\run_pi4_single_driver_trial.sh'
if (-not (Test-Path -LiteralPath $generator -PathType Leaf)) { throw "Missing synthesizer: $generator" }
if (-not (Test-Path -LiteralPath $trial -PathType Leaf)) { throw "Missing trial script: $trial" }

$target = "$PiUser@$($selected.Address)"
$remoteRoot = "/tmp/aurum-pi4-single-driver-$RunTag"
$sshBase = $sshBaseCommon

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
