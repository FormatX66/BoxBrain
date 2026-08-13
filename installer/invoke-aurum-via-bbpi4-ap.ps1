#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProfileName,
    [string]$InterfaceName,
    [string]$ApAddress = "10.42.194.1",
    [string]$PiUser = "kali",
    [string]$KeyPath = (Join-Path $HOME ".ssh\boxbrain_pi_ed25519"),
    [string]$ExpectedHostKeyFingerprint = "SHA256:hFesq9DxC+gOdl8rT6a4RDptEsNp6yn2FhwYv/lXC1o",
    [ValidateRange(5, 120)]
    [int]$ConnectTimeoutSeconds = 30,
    [ValidateRange(1, 8)]
    [int]$MaxProfileAttempts = 6,
    [switch]$KeepConnected,
    [switch]$SkipDialogue
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-NativeCaptured {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$Arguments
    )

    $oldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = @(& $FilePath @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldPreference
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = $output
    }
}

function Get-WlanInterfaceRecords {
    param([Parameter(Mandatory)][string]$NetshPath)

    $result = Invoke-NativeCaptured -FilePath $NetshPath -Arguments @("wlan", "show", "interfaces")
    if ($result.ExitCode -ne 0) {
        throw "Windows WLAN interface inventory failed."
    }

    $records = [Collections.Generic.List[object]]::new()
    $current = $null
    foreach ($line in $result.Output) {
        $text = [string]$line
        $match = [regex]::Match($text, '^\s*Name\s*:\s*(.+?)\s*$')
        if ($match.Success) {
            if ($null -ne $current) { $records.Add([pscustomobject]$current) }
            $current = [ordered]@{
                Name = $match.Groups[1].Value.Trim()
                State = ""
                Profile = ""
                Ssid = ""
            }
            continue
        }
        if ($null -eq $current) { continue }
        $match = [regex]::Match($text, '^\s*State\s*:\s*(.+?)\s*$')
        if ($match.Success) { $current.State = $match.Groups[1].Value.Trim(); continue }
        $match = [regex]::Match($text, '^\s*Profile\s*:\s*(.+?)\s*$')
        if ($match.Success) { $current.Profile = $match.Groups[1].Value.Trim(); continue }
        $match = [regex]::Match($text, '^\s*SSID\s*:\s*(.+?)\s*$')
        if ($match.Success) { $current.Ssid = $match.Groups[1].Value.Trim(); continue }
    }
    if ($null -ne $current) { $records.Add([pscustomobject]$current) }
    return @($records)
}

function Select-WlanInterface {
    param(
        [Parameter(Mandatory)][string]$NetshPath,
        [string]$RequestedName
    )

    $records = @(Get-WlanInterfaceRecords -NetshPath $NetshPath)
    if (-not [string]::IsNullOrWhiteSpace($RequestedName)) {
        $selected = @($records | Where-Object { $_.Name -eq $RequestedName } | Select-Object -First 1)
        if ($selected.Count -eq 0) {
            throw "The requested Windows WLAN interface was not found: $RequestedName"
        }
        return $selected[0]
    }
    if ($records.Count -gt 0) { return $records[0] }

    $adapter = Get-NetAdapter -ErrorAction SilentlyContinue |
        Where-Object { $_.InterfaceDescription -match '(?i)(wireless|wi-?fi|802\.11)' } |
        Sort-Object ifIndex |
        Select-Object -First 1
    if ($null -eq $adapter) { throw "No Windows WLAN interface was found." }
    return [pscustomobject]@{
        Name = [string]$adapter.Name
        State = [string]$adapter.Status
        Profile = ""
        Ssid = ""
    }
}

function Get-SavedWlanProfiles {
    param(
        [Parameter(Mandatory)][string]$NetshPath,
        [Parameter(Mandatory)][string]$WlanInterfaceName
    )

    $result = Invoke-NativeCaptured -FilePath $NetshPath -Arguments @(
        "wlan", "show", "profiles", "interface=$WlanInterfaceName"
    )
    if ($result.ExitCode -ne 0) { throw "Windows saved WLAN profile inventory failed." }

    $profiles = [Collections.Generic.List[string]]::new()
    foreach ($line in $result.Output) {
        $match = [regex]::Match(
            [string]$line,
            '^\s*(?:All User Profile|Current User Profile)\s*:\s*(.+?)\s*$'
        )
        if ($match.Success) {
            $value = $match.Groups[1].Value.Trim()
            if (-not [string]::IsNullOrWhiteSpace($value) -and -not $profiles.Contains($value)) {
                $profiles.Add($value)
            }
        }
    }
    return @($profiles)
}

function Get-WlanProfileSsid {
    param(
        [Parameter(Mandatory)][string]$NetshPath,
        [Parameter(Mandatory)][string]$WlanInterfaceName,
        [Parameter(Mandatory)][string]$SavedProfileName
    )

    $result = Invoke-NativeCaptured -FilePath $NetshPath -Arguments @(
        "wlan", "show", "profile", "name=$SavedProfileName", "interface=$WlanInterfaceName"
    )
    if ($result.ExitCode -ne 0) { return "" }
    foreach ($line in $result.Output) {
        $match = [regex]::Match([string]$line, '^\s*SSID name\s*:\s*"?(.+?)"?\s*$')
        if ($match.Success) { return $match.Groups[1].Value.Trim('"').Trim() }
    }
    return ""
}

function Get-VisibleWlanSsids {
    param(
        [Parameter(Mandatory)][string]$NetshPath,
        [Parameter(Mandatory)][string]$WlanInterfaceName
    )

    $result = Invoke-NativeCaptured -FilePath $NetshPath -Arguments @(
        "wlan", "show", "networks", "mode=bssid", "interface=$WlanInterfaceName"
    )
    if ($result.ExitCode -ne 0) { return @() }
    $values = [Collections.Generic.List[string]]::new()
    foreach ($line in $result.Output) {
        $match = [regex]::Match([string]$line, '^\s*SSID\s+\d+\s*:\s*(.+?)\s*$')
        if ($match.Success) {
            $value = $match.Groups[1].Value.Trim()
            if (-not [string]::IsNullOrWhiteSpace($value) -and -not $values.Contains($value)) {
                $values.Add($value)
            }
        }
    }
    return @($values)
}

function Wait-WlanProfile {
    param(
        [Parameter(Mandatory)][string]$NetshPath,
        [Parameter(Mandatory)][string]$WlanInterfaceName,
        [Parameter(Mandatory)][string]$ExpectedProfile,
        [Parameter(Mandatory)][int]$TimeoutSeconds
    )

    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $records = @(Get-WlanInterfaceRecords -NetshPath $NetshPath)
        $record = @($records | Where-Object { $_.Name -eq $WlanInterfaceName } | Select-Object -First 1)
        if ($record.Count -gt 0 -and $record[0].Profile -eq $ExpectedProfile) { return $true }
        Start-Sleep -Seconds 1
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    return $false
}

function Connect-WlanProfile {
    param(
        [Parameter(Mandatory)][string]$NetshPath,
        [Parameter(Mandatory)][string]$WlanInterfaceName,
        [Parameter(Mandatory)][string]$SavedProfileName,
        [Parameter(Mandatory)][int]$TimeoutSeconds
    )

    $result = Invoke-NativeCaptured -FilePath $NetshPath -Arguments @(
        "wlan", "connect", "name=$SavedProfileName", "interface=$WlanInterfaceName"
    )
    if ($result.ExitCode -ne 0) { return $false }
    return Wait-WlanProfile -NetshPath $NetshPath -WlanInterfaceName $WlanInterfaceName `
        -ExpectedProfile $SavedProfileName -TimeoutSeconds $TimeoutSeconds
}

function Test-BBPI4Ssh {
    param(
        [Parameter(Mandatory)][string]$SshPath,
        [Parameter(Mandatory)][string]$Address,
        [Parameter(Mandatory)][string]$UserName,
        [Parameter(Mandatory)][string]$IdentityPath
    )

    $arguments = @(
        "-i", $IdentityPath,
        "-o", "BatchMode=yes",
        "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "ConnectTimeout=4",
        "$UserName@$Address",
        "test -d /opt/boxbrain/codelation || test -d /opt/aurum"
    )
    $result = Invoke-NativeCaptured -FilePath $SshPath -Arguments $arguments
    return $result.ExitCode -eq 0
}

function Confirm-BBPI4HostKey {
    param(
        [Parameter(Mandatory)][string]$Address,
        [Parameter(Mandatory)][string]$ExpectedFingerprint
    )

    $keyscan = (Get-Command ssh-keyscan.exe -CommandType Application -ErrorAction Stop).Source
    $keygen = (Get-Command ssh-keygen.exe -CommandType Application -ErrorAction Stop).Source
    $scan = Invoke-NativeCaptured -FilePath $keyscan -Arguments @("-T", "4", "-t", "ed25519", $Address)
    $lines = @($scan.Output | Where-Object {
        -not [string]::IsNullOrWhiteSpace([string]$_) -and -not ([string]$_).StartsWith("#")
    })
    if ($scan.ExitCode -ne 0 -or $lines.Count -eq 0) {
        throw "BBPI4 did not publish an ED25519 host key on the AP route."
    }

    $temporary = Join-Path ([IO.Path]::GetTempPath()) ("bbpi4-hostkey-" + [Guid]::NewGuid().ToString("N"))
    try {
        [IO.File]::WriteAllLines($temporary, @([string]$lines[0]), [Text.Encoding]::ASCII)
        $fingerprint = Invoke-NativeCaptured -FilePath $keygen -Arguments @("-lf", $temporary, "-E", "sha256")
        $text = ($fingerprint.Output -join " ")
        $match = [regex]::Match($text, 'SHA256:[A-Za-z0-9+/=]+')
        if (-not $match.Success -or $match.Value -ne $ExpectedFingerprint) {
            throw "BBPI4 AP SSH host-key fingerprint did not match the approved fingerprint."
        }

        $sshDirectory = Join-Path $HOME ".ssh"
        if (-not (Test-Path -LiteralPath $sshDirectory -PathType Container)) {
            New-Item -ItemType Directory -Path $sshDirectory -Force | Out-Null
        }
        $knownHosts = Join-Path $sshDirectory "known_hosts"
        if (Test-Path -LiteralPath $knownHosts -PathType Leaf) {
            Invoke-NativeCaptured -FilePath $keygen -Arguments @("-R", $Address, "-f", $knownHosts) | Out-Null
        }
        [IO.File]::AppendAllLines($knownHosts, @([string]$lines[0]), [Text.Encoding]::ASCII)
    }
    finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
}

if ($ApAddress -ne "10.42.194.1") {
    throw "The BBPI4 AP route is fixed to 10.42.194.1."
}
if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
    throw "The dedicated BoxBrain SSH identity was not found at $KeyPath."
}

$netsh = (Get-Command netsh.exe -CommandType Application -ErrorAction Stop).Source
$ssh = (Get-Command ssh.exe -CommandType Application -ErrorAction Stop).Source
$selectedInterface = Select-WlanInterface -NetshPath $netsh -RequestedName $InterfaceName
$initialProfile = [string]$selectedInterface.Profile
$savedProfiles = @(Get-SavedWlanProfiles -NetshPath $netsh -WlanInterfaceName $selectedInterface.Name)
$visibleSsids = @(Get-VisibleWlanSsids -NetshPath $netsh -WlanInterfaceName $selectedInterface.Name)

if (-not [string]::IsNullOrWhiteSpace($ProfileName) -and $savedProfiles -notcontains $ProfileName) {
    throw "The requested BBPI4 AP WLAN profile is not saved on this Windows computer: $ProfileName"
}

$profileRecords = @()
foreach ($savedProfile in $savedProfiles) {
    $ssid = Get-WlanProfileSsid -NetshPath $netsh -WlanInterfaceName $selectedInterface.Name `
        -SavedProfileName $savedProfile
    $nameMatch = ("$savedProfile $ssid" -match '(?i)(boxbrain|bbpi4|aurum|kali|raspberry|(^|[-_ ])pi($|[-_ ]))')
    $visible = -not [string]::IsNullOrWhiteSpace($ssid) -and $visibleSsids -contains $ssid
    $score = 0
    if (-not [string]::IsNullOrWhiteSpace($ProfileName) -and $savedProfile -eq $ProfileName) { $score = 1000 }
    elseif ($nameMatch -and $visible) { $score = 300 }
    elseif ($nameMatch) { $score = 200 }
    elseif ($visible -and $savedProfile -ne $initialProfile) { $score = 100 }
    elseif ($savedProfile -eq $initialProfile) { $score = 10 }
    $profileRecords += [pscustomobject]@{
        Profile = $savedProfile
        Ssid = $ssid
        Score = $score
    }
}

$candidates = @(
    $profileRecords |
        Where-Object { $_.Score -gt 0 } |
        Sort-Object @{ Expression = "Score"; Descending = $true }, @{ Expression = "Profile"; Descending = $false } |
        Select-Object -First $MaxProfileAttempts
)
if ($candidates.Count -eq 0) {
    $visibleSaved = @($profileRecords | Where-Object { $visibleSsids -contains $_.Ssid } | ForEach-Object { $_.Profile })
    $detail = if ($visibleSaved.Count -gt 0) { $visibleSaved -join ", " } else { "none" }
    throw "No bounded saved Windows WLAN profile matched the BBPI4 AP. Visible saved candidates: $detail"
}

$connectedProfile = $null
$connectedByScript = $false
try {
    foreach ($candidate in $candidates) {
        if ($candidate.Profile -ne $initialProfile) {
            if (-not (Connect-WlanProfile -NetshPath $netsh -WlanInterfaceName $selectedInterface.Name `
                -SavedProfileName $candidate.Profile -TimeoutSeconds $ConnectTimeoutSeconds)) {
                continue
            }
            $connectedByScript = $true
        }

        if (-not (Test-BBPI4Ssh -SshPath $ssh -Address $ApAddress -UserName $PiUser -IdentityPath $KeyPath)) {
            Confirm-BBPI4HostKey -Address $ApAddress -ExpectedFingerprint $ExpectedHostKeyFingerprint
        }
        if (Test-BBPI4Ssh -SshPath $ssh -Address $ApAddress -UserName $PiUser -IdentityPath $KeyPath) {
            $connectedProfile = $candidate.Profile
            break
        }
    }

    if ([string]::IsNullOrWhiteSpace($connectedProfile)) {
        throw "A saved Windows WLAN profile connected, but none verified BBPI4 over SSH at 10.42.194.1."
    }

    Write-Output "AURUM_AP_ROUTE_CONFIRMED computer=$env:COMPUTERNAME interface=$($selectedInterface.Name) profile=$connectedProfile address=$ApAddress"

    $repositoryRoot = Split-Path -Parent $PSScriptRoot
    $reconciler = Join-Path $PSScriptRoot "reconcile-existing-aurum-gold-seed-on-pi.ps1"
    & $reconciler -PiAddresses @($ApAddress) -PiUser $PiUser -KeyPath $KeyPath

    if (-not $SkipDialogue.IsPresent) {
        if ([string]::IsNullOrWhiteSpace($env:OPENAI_API_KEY)) {
            Write-Output "AURUM_DIALOGUE_READY - OPENAI_API_KEY is not present in this process, so no live model session was started."
        }
        else {
            $question = "Do you prefer he, she, or they pronouns? You may also say that you have no preference or choose another form if that fits you better."
            $ask = Join-Path $PSScriptRoot "ask-aurum-on-pi.ps1"
            & $ask -Prompt $question -PiAddresses @($ApAddress) -PiUser $PiUser -KeyPath $KeyPath
        }
    }
}
finally {
    if (-not $KeepConnected.IsPresent) {
        if (-not [string]::IsNullOrWhiteSpace($initialProfile) -and $initialProfile -ne $connectedProfile) {
            if (Connect-WlanProfile -NetshPath $netsh -WlanInterfaceName $selectedInterface.Name `
                -SavedProfileName $initialProfile -TimeoutSeconds $ConnectTimeoutSeconds) {
                Write-Output "AURUM_AP_ROUTE_RESTORED profile=$initialProfile"
            }
            else {
                Write-Warning "The previous Windows WLAN profile could not be restored automatically: $initialProfile"
            }
        }
        elseif ([string]::IsNullOrWhiteSpace($initialProfile) -and $connectedByScript) {
            Invoke-NativeCaptured -FilePath $netsh -Arguments @(
                "wlan", "disconnect", "interface=$($selectedInterface.Name)"
            ) | Out-Null
            Write-Output "AURUM_AP_ROUTE_DISCONNECTED"
        }
    }
}
