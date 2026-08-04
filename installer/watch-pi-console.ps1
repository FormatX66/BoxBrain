#Requires -Version 5.1
[CmdletBinding()]
param(
    [string[]]$PiAddresses = @(
        "10.12.194.1",
        "192.168.0.194",
        "10.42.194.1"
    ),
    [ValidatePattern("^[a-z_][a-z0-9_-]{0,31}$")]
    [string]$PiUser = "kali",
    [string]$KeyPath = (Join-Path $HOME ".ssh\boxbrain_pi_ed25519"),
    [ValidateRange(2, 300)]
    [int]$PollSeconds = 5,
    [ValidateRange(15, 900)]
    [int]$RetrySeconds = 60,
    [switch]$CheckOnce,
    [switch]$NoOpen
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-PrivateOrLinkLocalAddress {
    param([Parameter(Mandatory)][string]$Address)

    $parsed = $null
    if (-not [Net.IPAddress]::TryParse($Address, [ref]$parsed)) {
        return $false
    }
    $bytes = $parsed.GetAddressBytes()
    if ($bytes.Length -ne 4) {
        return $false
    }
    return (
        $bytes[0] -eq 10 -or
        ($bytes[0] -eq 172 -and $bytes[1] -ge 16 -and $bytes[1] -le 31) -or
        ($bytes[0] -eq 192 -and $bytes[1] -eq 168) -or
        ($bytes[0] -eq 169 -and $bytes[1] -eq 254)
    )
}

function Test-PiSshPort {
    param([Parameter(Mandatory)][string]$Address)

    $client = [Net.Sockets.TcpClient]::new()
    try {
        return $client.ConnectAsync($Address, 22).Wait(600)
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

$launcherPath = Join-Path $PSScriptRoot "open-pi-console.ps1"
if (-not (Test-Path -LiteralPath $launcherPath -PathType Leaf)) {
    throw "The Pi console launcher is missing: $launcherPath"
}
if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
    throw "The BoxBrain SSH key was not found at $KeyPath."
}

$candidateAddresses = @(
    $PiAddresses |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
        Select-Object -Unique
)
if ($candidateAddresses.Count -eq 0) {
    throw "At least one Pi address is required."
}
foreach ($address in $candidateAddresses) {
    if (-not (Test-PrivateOrLinkLocalAddress -Address $address)) {
        throw "Every Pi address must be a private or link-local IPv4 address."
    }
}

$mutex = [Threading.Mutex]::new($false, "Local\BoxBrainPiConsoleAutoOpen")
$ownsMutex = $false
try {
    $ownsMutex = $mutex.WaitOne(0, $false)
    if (-not $ownsMutex) {
        Write-Output "BOXBRAIN_CONSOLE_WATCHER_ALREADY_RUNNING"
        return
    }

    $activeAddress = $null
    $lastAttemptAddress = $null
    $lastAttemptAt = [DateTime]::MinValue
    do {
        $selectedAddress = $null
        foreach ($address in $candidateAddresses) {
            if (Test-PiSshPort -Address $address) {
                $selectedAddress = $address
                break
            }
        }

        if ($null -eq $selectedAddress) {
            $activeAddress = $null
            $lastAttemptAddress = $null
            Write-Verbose "No BoxBrain Pi SSH endpoint is reachable."
        }
        elseif ($selectedAddress -ne $activeAddress) {
            $retryDue = (
                $selectedAddress -ne $lastAttemptAddress -or
                ([DateTime]::UtcNow - $lastAttemptAt).TotalSeconds -ge $RetrySeconds
            )
            if ($retryDue) {
                $lastAttemptAddress = $selectedAddress
                $lastAttemptAt = [DateTime]::UtcNow
                try {
                    $arguments = @{
                        PiAddress = $selectedAddress
                        PiUser = $PiUser
                        KeyPath = $KeyPath
                    }
                    if ($NoOpen) {
                        $arguments.NoOpen = $true
                    }
                    $url = & $launcherPath @arguments
                    $activeAddress = $selectedAddress
                    Write-Output (
                        "BOXBRAIN_CONSOLE_OPEN address={0} url={1}" -f
                        $selectedAddress, $url
                    )
                }
                catch {
                    Write-Warning (
                        "BoxBrain Pi was reachable at {0}, but its console " +
                        "could not be opened: {1}" -f
                        $selectedAddress, $_.Exception.Message
                    )
                }
            }
        }

        if (-not $CheckOnce) {
            Start-Sleep -Seconds $PollSeconds
        }
    } while (-not $CheckOnce)
}
finally {
    if ($ownsMutex) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
