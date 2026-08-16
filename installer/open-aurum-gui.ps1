#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$PiAddress = "10.12.194.1",
    [ValidatePattern("^[a-z_][a-z0-9_-]{0,31}$")]
    [string]$PiUser = "kali",
    [string]$KeyPath = (Join-Path $HOME ".ssh\boxbrain_pi_ed25519"),
    [string]$OpenAiEnvFile = "",
    [ValidateRange(1024, 65525)]
    [int]$PreferredLocalPort = 8765,
    [switch]$NoOpen
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-LocalTcpPort {
    param([Parameter(Mandatory)][int]$Port)
    $client = [Net.Sockets.TcpClient]::new()
    try {
        return $client.ConnectAsync("127.0.0.1", $Port).Wait(250)
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Get-OptionalOpenAiApiKey {
    param([string]$EnvFile)

    $candidate = [Environment]::GetEnvironmentVariable("OPENAI_API_KEY", "Process")
    if ([string]::IsNullOrWhiteSpace($candidate) -and (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
        $entries = @()
        foreach ($line in [IO.File]::ReadAllLines((Resolve-Path -LiteralPath $EnvFile).Path)) {
            if ($line -match '^\s*OPENAI_API_KEY\s*=\s*(?<Value>.*?)\s*$') {
                $entries += $Matches['Value']
            }
        }
        if ($entries.Count -gt 1) {
            throw "The local key file contains more than one OPENAI_API_KEY entry."
        }
        if ($entries.Count -eq 1) {
            $candidate = [string]$entries[0]
            if (
                ($candidate.StartsWith('"') -and $candidate.EndsWith('"')) -or
                ($candidate.StartsWith("'") -and $candidate.EndsWith("'"))
            ) {
                $candidate = $candidate.Substring(1, $candidate.Length - 2)
            }
        }
    }
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        return $null
    }
    if ($candidate -notmatch '^sk-\S{16,508}$' -or $candidate.Length -gt 512) {
        throw "The local OpenAI API key does not match the bounded key format."
    }
    return $candidate
}

if ($PiAddress -ne "10.12.194.1") {
    throw "The first Aurum GUI launch is bound to the approved USB route 10.12.194.1."
}
if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
    throw "The dedicated BBPI4 SSH key was not found at $KeyPath."
}
if ([string]::IsNullOrWhiteSpace($OpenAiEnvFile)) {
    $OpenAiEnvFile = Join-Path (Split-Path -Parent $PSScriptRoot) ".env.local"
}

$ssh = (Get-Command ssh.exe -CommandType Application -ErrorAction Stop).Source
$target = "$PiUser@$PiAddress"
$options = @(
    "-i", $KeyPath,
    "-o", "BatchMode=yes",
    "-o", "IdentitiesOnly=yes",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "ConnectTimeout=8"
)

$ready = (& $ssh @options $target "sudo -n /usr/local/bin/aurum-gui-start").Trim()
if ($LASTEXITCODE -ne 0 -or $ready -notmatch "(?m)^AURUM_GUI_READY address=127\.0\.0\.1 port=8765 transient=true$") {
    throw "The Pi-local Aurum GUI did not start with its expected safety boundary.`n$ready"
}

$localPort = $null
$startTunnel = $false
foreach ($offset in 0..9) {
    $candidate = $PreferredLocalPort + $offset
    $listener = Get-NetTCPConnection `
        -LocalAddress "127.0.0.1" `
        -LocalPort $candidate `
        -State Listen `
        -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $listener) {
        $localPort = $candidate
        $startTunnel = $true
        break
    }
    $process = Get-CimInstance Win32_Process `
        -Filter "ProcessId = $($listener.OwningProcess)" `
        -ErrorAction SilentlyContinue
    $expectedForward = "127.0.0.1:${candidate}:127.0.0.1:8765"
    if (
        $null -ne $process -and
        $process.Name -eq "ssh.exe" -and
        $process.CommandLine -like "*$expectedForward*" -and
        $process.CommandLine -like "*$target*"
    ) {
        $localPort = $candidate
        break
    }
}
if ($null -eq $localPort) {
    throw "No private local port is available for the Aurum GUI tunnel."
}

if ($startTunnel) {
    $escapedKeyPath = $KeyPath.Replace('"', '\"')
    $arguments = (
        '-N -L 127.0.0.1:{0}:127.0.0.1:8765 ' +
        '-i "{1}" -o BatchMode=yes -o IdentitiesOnly=yes ' +
        '-o StrictHostKeyChecking=yes -o ExitOnForwardFailure=yes ' +
        '-o ServerAliveInterval=30 -o ServerAliveCountMax=3 {2}'
    ) -f $localPort, $escapedKeyPath, $target
    $tunnel = Start-Process `
        -FilePath $ssh `
        -ArgumentList $arguments `
        -WindowStyle Hidden `
        -PassThru

    $tunnelReady = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 200
        if ($tunnel.HasExited) {
            break
        }
        if (Test-LocalTcpPort -Port $localPort) {
            $tunnelReady = $true
            break
        }
    }
    if (-not $tunnelReady) {
        if (-not $tunnel.HasExited) {
            Stop-Process -Id $tunnel.Id
        }
        throw "The private Aurum GUI SSH tunnel could not be opened."
    }
}

$url = "http://127.0.0.1:$localPort/"
$status = Invoke-RestMethod -Uri "${url}api/status" -TimeoutSec 5
if (
    $status.schema -ne "aurum.gui.v3" -or
    $status.console.identity -ne "BBPI4/Aurum" -or
    $status.transport.loopback_only -ne $true -or
    $status.authority.host_actuation -ne $false
) {
    throw "The Aurum GUI status proof was not valid."
}

$apiKeyLoaded = $false
$apiKeyStaged = $false
$apiKey = Get-OptionalOpenAiApiKey -EnvFile $OpenAiEnvFile
if ($null -ne $apiKey) {
    $page = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 5
    if ($page.Content -notmatch '<meta name="aurum-csrf" content="(?<Token>[A-Za-z0-9_-]{32,})">') {
        throw "The Aurum GUI did not expose its bounded request proof."
    }
    $headers = @{
        Origin = "http://127.0.0.1:$localPort"
        'X-Aurum-CSRF' = $Matches['Token']
    }
    $body = [ordered]@{action = 'stage'; api_key = $apiKey} | ConvertTo-Json -Compress
    try {
        $bootstrap = Invoke-RestMethod `
            -Method Post `
            -Uri "${url}api/key-bootstrap" `
            -Headers $headers `
            -ContentType 'application/json' `
            -Body $body `
            -TimeoutSec 5
    }
    catch {
        throw "The memory-only Aurum key bootstrap was not accepted."
    }
    finally {
        $body = $null
        $apiKey = $null
    }
    if (
        $bootstrap.staged -ne $true -or
        $bootstrap.memory_only -ne $true -or
        $bootstrap.api_key_persisted -ne $false -or
        $bootstrap.host_actuation -ne $false
    ) {
        throw "The Aurum key bootstrap safety proof was invalid."
    }
    $apiKeyStaged = $true
}

if (-not $NoOpen) {
    Start-Process $url
}
if ($apiKeyStaged) {
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 200
        $current = Invoke-RestMethod -Uri "${url}api/status" -TimeoutSec 5
        if ($current.key_bootstrap.pending -eq $false) {
            $apiKeyLoaded = $true
            break
        }
    }
}
Write-Output "AURUM_GUI_OPEN_OK url=$url mind_version=$($status.console.mind_version) host_actuation=false api_key_staged=$($apiKeyStaged.ToString().ToLowerInvariant()) api_key_loaded=$($apiKeyLoaded.ToString().ToLowerInvariant())"
