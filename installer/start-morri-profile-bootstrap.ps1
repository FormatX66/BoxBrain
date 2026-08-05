#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$KvmBaseUrl = "http://127.0.0.1:8790",
    [string]$CredentialPath = (
        Join-Path $env:LOCALAPPDATA "BoxBrain\credentials\morri-temporary.clixml"
    ),
    [switch]$NoApprove,
    [switch]$SendPasswordOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-KvmInput {
    param(
        [Parameter(Mandatory)][hashtable]$Payload,
        [Parameter(Mandatory)][hashtable]$Headers
    )

    $result = Invoke-RestMethod `
        -Method Post `
        -Uri "$KvmBaseUrl/api/v1/hid-kvm/input" `
        -Headers $Headers `
        -ContentType "application/json" `
        -Body ($Payload | ConvertTo-Json -Compress)
    if (-not $result.ok) {
        throw "KVM input was not acknowledged."
    }
    return $result
}

function Send-KvmChord {
    param(
        [Parameter(Mandatory)][string[]]$Codes,
        [Parameter(Mandatory)][hashtable]$Headers
    )

    foreach ($code in $Codes) {
        Invoke-KvmInput -Headers $Headers -Payload @{
            action = "key"
            code = $code
            down = $true
        } | Out-Null
    }
    Invoke-KvmInput -Headers $Headers -Payload @{ action = "release" } |
        Out-Null
}

function Send-KvmText {
    param(
        [Parameter(Mandatory)][string]$Text,
        [Parameter(Mandatory)][hashtable]$Headers
    )

    $acknowledged = 0
    foreach ($character in $Text.ToCharArray()) {
        $result = Invoke-KvmInput -Headers $Headers -Payload @{
            action = "character"
            character = [string]$character
        }
        if (-not $result.acknowledged) {
            throw "KVM character $acknowledged was not acknowledged."
        }
        $acknowledged += 1
        Start-Sleep -Milliseconds 40
    }
    Invoke-KvmInput -Headers $Headers -Payload @{
        action = "key"
        code = "Enter"
        down = $true
    } | Out-Null
    Invoke-KvmInput -Headers $Headers -Payload @{ action = "release" } |
        Out-Null
    return $acknowledged
}

if (-not (Test-Path -LiteralPath $CredentialPath -PathType Leaf)) {
    $alphabet = (
        "ABCDEFGHJKLMNPQRSTUVWXYZ" +
        "abcdefghijkmnopqrstuvwxyz" +
        "23456789"
    )
    $random = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        do {
            $bytes = [byte[]]::new(18)
            $random.GetBytes($bytes)
            $password = -join ($bytes | ForEach-Object {
                $alphabet[$_ % $alphabet.Length]
            })
        } until (
            $password -match "[A-Z]" -and
            $password -match "[a-z]" -and
            $password -match "[0-9]"
        )
    }
    finally {
        $random.Dispose()
    }
    $directory = Split-Path -Parent $CredentialPath
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $securePassword = ConvertTo-SecureString $password -AsPlainText -Force
    [PSCredential]::new("Morri", $securePassword) |
        Export-Clixml -LiteralPath $CredentialPath
    $password = $null
}

$page = (Invoke-WebRequest -UseBasicParsing -Uri "$KvmBaseUrl/kvm").Content
if ($page -notmatch 'const csrf = ("[^"]+")') {
    throw "The KVM CSRF token is unavailable."
}
$headers = @{ "X-BoxBrain-CSRF" = ($Matches[1] | ConvertFrom-Json) }
$credential = Import-Clixml -LiteralPath $CredentialPath
$temporaryPassword = $credential.GetNetworkCredential().Password

if ($SendPasswordOnly) {
    $count = Send-KvmText -Text $temporaryPassword -Headers $headers
    Write-Output "Submitted $count acknowledged secure-prompt characters."
    return
}

$runCommand = (
    'powershell -NoProfile -Command "iwr ' +
    'http://10.12.194.1:8788/install-morri-profile.ps1 ' +
    '-OutFile $env:TEMP\m.ps1;' +
    'Start-Process powershell.exe -Verb RunAs -ArgumentList ' +
    '(''-ExecutionPolicy Bypass -File ''+$env:TEMP+' +
    '''\m.ps1'')"'
)

Invoke-KvmInput -Headers $headers -Payload @{ action = "release" } |
    Out-Null
Send-KvmChord -Headers $headers -Codes @("MetaLeft", "KeyR")
Start-Sleep -Seconds 2
$acknowledged = Send-KvmText -Text $runCommand -Headers $headers

Start-Sleep -Seconds 5
if ($NoApprove) {
    Write-Output (
        "Submitted $acknowledged acknowledged profile-bootstrap " +
        "characters; UAC approval is pending."
    )
    return
}
Send-KvmChord -Headers $headers -Codes @("ArrowLeft")
Invoke-KvmInput -Headers $headers -Payload @{
    action = "key"
    code = "Enter"
    down = $true
} | Out-Null
Invoke-KvmInput -Headers $headers -Payload @{ action = "release" } |
    Out-Null

Write-Output (
    "Submitted $acknowledged acknowledged profile-bootstrap characters " +
    "and approved UAC."
)
