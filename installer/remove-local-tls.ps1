#Requires -Version 5.1
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "High")]
param(
    [switch]$ConfirmRemoval
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $ConfirmRemoval) {
    throw "Removal is destructive. Re-run with -ConfirmRemoval (and optionally -WhatIf)."
}

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$tlsDirectory = [IO.Path]::GetFullPath(
    (Join-Path $repositoryRoot "controller\data\tls")
)
$expectedTlsDirectory = [IO.Path]::GetFullPath(
    (Join-Path $repositoryRoot "controller\data\tls")
)
$metadataPath = Join-Path $tlsDirectory "metadata.json"
if (-not (Test-Path -LiteralPath $metadataPath)) {
    Write-Host "[ready] No BoxBrain TLS metadata was found; nothing was removed."
    exit 0
}
if ($tlsDirectory -ne $expectedTlsDirectory) {
    throw "Refusing to remove an unexpected TLS directory: $tlsDirectory"
}

$metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
$thumbprints = @($metadata.root_thumbprint, $metadata.server_thumbprint)
foreach ($thumbprint in $thumbprints) {
    if ($thumbprint -notmatch '^[A-Fa-f0-9]{40,64}$') {
        throw "TLS metadata contains an invalid certificate thumbprint."
    }
}

$targets = @(
    "Cert:\CurrentUser\Root\$($metadata.root_thumbprint)",
    "Cert:\CurrentUser\My\$($metadata.server_thumbprint)",
    "Cert:\CurrentUser\My\$($metadata.root_thumbprint)"
)
foreach ($target in $targets) {
    if ((Test-Path -LiteralPath $target) -and $PSCmdlet.ShouldProcess($target, "Remove BoxBrain certificate")) {
        Remove-Item -LiteralPath $target -Force
    }
}
if ($PSCmdlet.ShouldProcess($tlsDirectory, "Remove BoxBrain TLS files and metadata")) {
    Remove-Item -LiteralPath $tlsDirectory -Recurse -Force
}

if ($WhatIfPreference) {
    Write-Host "[preview] No certificate trust or TLS files were changed."
}
else {
    Write-Host "BoxBrain Current User certificate trust and TLS files were removed."
    Write-Host "Regenerate them with setup-local-tls.ps1 before starting HTTPS again."
}
