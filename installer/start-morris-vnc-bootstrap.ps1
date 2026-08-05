#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$KvmBaseUrl = "http://127.0.0.1:8790",
    [string]$CredentialDirectory = (
        Join-Path $env:LOCALAPPDATA "BoxBrain\credentials"
    ),
    [switch]$NoApprove,
    [switch]$SendCredentialsOnly
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

$page = (Invoke-WebRequest -UseBasicParsing -Uri "$KvmBaseUrl/kvm").Content
if ($page -notmatch 'const csrf = ("[^"]+")') {
    throw "The KVM CSRF token is unavailable."
}
$headers = @{ "X-BoxBrain-CSRF" = ($Matches[1] | ConvertFrom-Json) }

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

$vncCredential = Import-Clixml `
    -LiteralPath (Join-Path $CredentialDirectory "morris-vnc.clixml")
$controlCredential = Import-Clixml `
    -LiteralPath (Join-Path $CredentialDirectory "morris-vnc-control.clixml")
$vncPassword = $vncCredential.GetNetworkCredential().Password
$controlPassword = $controlCredential.GetNetworkCredential().Password

if ($SendCredentialsOnly) {
    $firstCount = Send-KvmText -Text $vncPassword -Headers $headers
    Start-Sleep -Seconds 2
    $secondCount = Send-KvmText -Text $controlPassword -Headers $headers
    Write-Output (
        "Submitted $($firstCount + $secondCount) acknowledged secure-prompt " +
        "characters."
    )
    return
}

$runCommand = (
    'powershell -NoProfile -Command "iwr ' +
    'http://10.12.194.1:8788/install-morris-vnc.ps1 ' +
    '-OutFile $env:TEMP\i.ps1;' +
    'Start-Process powershell.exe -Verb RunAs -ArgumentList ' +
    '(''-ExecutionPolicy Bypass -File ''+$env:TEMP+' +
    '''\i.ps1 -PromptForCredentials'')"'
)

Invoke-KvmInput -Headers $headers -Payload @{ action = "release" } |
    Out-Null
Send-KvmChord -Headers $headers -Codes @("MetaLeft", "KeyR")
Start-Sleep -Seconds 2

$acknowledged = Send-KvmText -Text $runCommand -Headers $headers

Start-Sleep -Seconds 5
if ($NoApprove) {
    Write-Output (
        "Submitted $acknowledged acknowledged Windows Installer " +
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
    "Submitted $acknowledged acknowledged Windows Installer characters " +
    "and approved UAC."
)
