#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$KvmBaseUrl = "http://127.0.0.1:8790",
    [string]$CredentialDirectory = (
        Join-Path $env:LOCALAPPDATA "BoxBrain\credentials"
    )
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

$vncCredential = Import-Clixml `
    -LiteralPath (Join-Path $CredentialDirectory "morris-vnc.clixml")
$controlCredential = Import-Clixml `
    -LiteralPath (Join-Path $CredentialDirectory "morris-vnc-control.clixml")
$vncPassword = $vncCredential.GetNetworkCredential().Password
$controlPassword = $controlCredential.GetNetworkCredential().Password
$msiArguments = (
    '/i C:\Users\bruce\AppData\Local\Temp\tightvnc.msi /qn /norestart ' +
    'ADDLOCAL=Server SERVER_REGISTER_AS_SERVICE=1 ' +
    'SERVER_ADD_FIREWALL_EXCEPTION=0 SERVER_ALLOW_SAS=1 ' +
    'SET_USEVNCAUTHENTICATION=1 VALUE_OF_USEVNCAUTHENTICATION=1 ' +
    'SET_PASSWORD=1 VALUE_OF_PASSWORD=' + $vncPassword + ' ' +
    'SET_USECONTROLAUTHENTICATION=1 ' +
    'VALUE_OF_USECONTROLAUTHENTICATION=1 ' +
    'SET_CONTROLPASSWORD=1 VALUE_OF_CONTROLPASSWORD=' + $controlPassword
)
$runCommand = (
    'powershell -NoProfile -Command "Start-Process msiexec.exe ' +
    '-Verb RunAs -ArgumentList ''' + $msiArguments + '''"'
)

Invoke-KvmInput -Headers $headers -Payload @{ action = "release" } |
    Out-Null
Send-KvmChord -Headers $headers -Codes @("MetaLeft", "KeyR")
Start-Sleep -Seconds 2

$acknowledged = 0
foreach ($character in $runCommand.ToCharArray()) {
    $result = Invoke-KvmInput -Headers $headers -Payload @{
        action = "character"
        character = [string]$character
    }
    if (-not $result.acknowledged) {
        throw "KVM character $acknowledged was not acknowledged."
    }
    $acknowledged += 1
}
Invoke-KvmInput -Headers $headers -Payload @{
    action = "key"
    code = "Enter"
    down = $true
} | Out-Null
Invoke-KvmInput -Headers $headers -Payload @{ action = "release" } |
    Out-Null

Start-Sleep -Seconds 5
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
