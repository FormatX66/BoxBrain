[CmdletBinding()]
param(
    [string]$StatusUrl = 'http://hopper.local:8768/status',
    [string]$EnvFile = (Join-Path (Split-Path -Parent $PSScriptRoot) '.env.local'),
    [string]$OutputPath = (Join-Path (Split-Path -Parent $PSScriptRoot) 'Projects/AurumPC/credentials/hopper-openai-api.sealed.json')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$line = Get-Content -LiteralPath $EnvFile | Where-Object { $_ -match '^OPENAI_API_KEY=' } | Select-Object -First 1
if (-not $line) {
    throw 'OPENAI_API_KEY is not available in the selected local environment file.'
}
$apiKey = $line.Substring($line.IndexOf('=') + 1).Trim().Trim('"').Trim("'")
$keyBytes = [System.Text.Encoding]::UTF8.GetBytes($apiKey)
if (-not $apiKey.StartsWith('sk-') -or $keyBytes.Length -lt 20 -or $keyBytes.Length -gt 400 -or $apiKey -match '\s') {
    throw 'The local OpenAI credential does not meet the sealed-envelope contract.'
}

$status = Invoke-RestMethod -Method Get -Uri $StatusUrl -TimeoutSec 8
$receiver = $status.credential.receiver
if (
    $status.machine -ne 'Hopper' -or
    $receiver.machine -ne 'hopper' -or
    $receiver.purpose -ne 'openai-api' -or
    $receiver.algorithm -ne 'rsa-oaep-sha256' -or
    $receiver.recipient_sha256 -notmatch '^[a-f0-9]{64}$'
) {
    throw 'The target did not return a valid Hopper credential receiver proof.'
}

$publicBytes = [Convert]::FromBase64String([string]$receiver.public_key_b64)
$publicDigest = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($publicBytes)).ToLowerInvariant()
if ($publicDigest -ne $receiver.recipient_sha256) {
    throw 'The Hopper receiver fingerprint does not match its public key.'
}
$pem = [System.Text.Encoding]::ASCII.GetString($publicBytes)
$derText = (($pem -split "`r?`n") | Where-Object { $_ -and -not $_.StartsWith('-----') }) -join ''
$der = [Convert]::FromBase64String($derText)
$rsa = [Security.Cryptography.RSA]::Create()
try {
    $bytesRead = 0
    $rsa.ImportSubjectPublicKeyInfo($der, [ref]$bytesRead)
    if ($bytesRead -ne $der.Length) {
        throw 'Hopper receiver public key contained trailing data.'
    }
    $ciphertext = $rsa.Encrypt($keyBytes, [Security.Cryptography.RSAEncryptionPadding]::OaepSHA256)
}
finally {
    $rsa.Dispose()
    [Array]::Clear($keyBytes, 0, $keyBytes.Length)
    Remove-Variable apiKey -ErrorAction SilentlyContinue
}

$ciphertextDigest = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($ciphertext)).ToLowerInvariant()
$envelope = [ordered]@{
    schema = 'aurum.credential-envelope.v1'
    machine = 'hopper'
    purpose = 'openai-api'
    algorithm = 'rsa-oaep-sha256'
    recipient_sha256 = [string]$receiver.recipient_sha256
    ciphertext_b64 = [Convert]::ToBase64String($ciphertext)
    ciphertext_sha256 = $ciphertextDigest
    created_at = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
}
$parent = Split-Path -Parent $OutputPath
[IO.Directory]::CreateDirectory($parent) | Out-Null
[IO.File]::WriteAllText($OutputPath, (($envelope | ConvertTo-Json -Depth 4) + "`n"), [Text.UTF8Encoding]::new($false))
[Array]::Clear($ciphertext, 0, $ciphertext.Length)

[pscustomobject]@{
    status = 'sealed'
    machine = 'hopper'
    recipient_sha256 = $receiver.recipient_sha256
    ciphertext_sha256 = $ciphertextDigest
    output = (Resolve-Path -LiteralPath $OutputPath).Path
    plaintext_in_git = $false
    browser_credential = $false
}
