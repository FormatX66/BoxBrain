[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$HopperAddress,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^SHA256:[A-Za-z0-9+/]{20,}$')]
    [string]$ExpectedHostFingerprint,

    [string]$IdentityFile = (Join-Path $env:USERPROFILE '.ssh\aurum_hopper_ed25519'),

    [string]$KnownHostsFile = (Join-Path $env:USERPROFILE '.ssh\aurum_hopper_known_hosts')
)

$ErrorActionPreference = 'Stop'
$sshKeygen = (Get-Command ssh-keygen.exe -ErrorAction Stop).Source
$sshKeyscan = (Get-Command ssh-keyscan.exe -ErrorAction Stop).Source
$identityDirectory = Split-Path -Parent $IdentityFile
New-Item -ItemType Directory -Force -Path $identityDirectory | Out-Null
$knownHostsDirectory = Split-Path -Parent $KnownHostsFile
New-Item -ItemType Directory -Force -Path $knownHostsDirectory | Out-Null

if (-not (Test-Path -LiteralPath $IdentityFile -PathType Leaf)) {
    & $sshKeygen -q -t ed25519 -a 64 -N '' -C 'aurum-hopper-remote' -f $IdentityFile
    if ($LASTEXITCODE -ne 0) { throw 'The dedicated Hopper identity could not be created.' }
}
$publicKeyFile = "$IdentityFile.pub"
if (-not (Test-Path -LiteralPath $publicKeyFile -PathType Leaf)) {
    throw 'The dedicated Hopper public key is missing.'
}

$scanFile = [System.IO.Path]::GetTempFileName()
try {
    $scan = & $sshKeyscan -T 5 -t ed25519 -- $HopperAddress 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $scan) { throw 'Hopper did not return an Ed25519 SSH host key.' }
    Set-Content -LiteralPath $scanFile -Value $scan -Encoding ascii
    $fingerprintLine = & $sshKeygen -E sha256 -lf $scanFile
    if ($LASTEXITCODE -ne 0 -or -not $fingerprintLine) { throw 'The Hopper SSH host key could not be fingerprinted.' }
    $actualFingerprint = @($fingerprintLine -split '\s+')[1]
    if (-not [string]::Equals($actualFingerprint, $ExpectedHostFingerprint, [StringComparison]::Ordinal)) {
        throw "Hopper host key mismatch. Expected $ExpectedHostFingerprint but observed $actualFingerprint."
    }
    if (Test-Path -LiteralPath $KnownHostsFile -PathType Leaf) {
        $existing = & $sshKeygen -F $HopperAddress -f $KnownHostsFile 2>$null
        if ($existing) {
            throw 'A Hopper host-key entry already exists. It was preserved; verify it before replacing trust.'
        }
    }
    Add-Content -LiteralPath $KnownHostsFile -Value $scan -Encoding ascii
}
finally {
    Remove-Item -LiteralPath $scanFile -Force -ErrorAction SilentlyContinue
}

$publicKey = (Get-Content -LiteralPath $publicKeyFile -Raw).Trim()
Set-Clipboard -Value $publicKey
Write-Output 'AURUM_HOPPER_REMOTE_SETUP status=ready public_key_copied=true'
Write-Output "Host key verified: $ExpectedHostFingerprint"
Write-Output 'Paste the copied public key into Hopper: Remote Control > Pair this controller.'
