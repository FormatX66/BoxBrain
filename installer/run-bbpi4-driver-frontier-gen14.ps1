#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$OutputDirectory = 'evidence',
    [string]$RunTag = $env:GITHUB_RUN_ID
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$basePath = Join-Path $PSScriptRoot 'run-bbpi4-driver-frontier.ps1'
$extensionPath = Join-Path $PSScriptRoot 'aurum-pi4-driver-gen14-extension.ps1'
if (-not (Test-Path -LiteralPath $basePath -PathType Leaf)) {
    throw "Missing base Aurum Pi4 driver frontier runner: $basePath"
}
if (-not (Test-Path -LiteralPath $extensionPath -PathType Leaf)) {
    throw "Missing Aurum Pi4 driver generation extension: $extensionPath"
}

$original = [IO.File]::ReadAllText($basePath)
$patched = $original
$newline = if ($original.Contains("`r`n")) { "`r`n" } else { "`n" }

$limitOld = 'elseif ($generation -eq $validated -and $next -eq ($validated + 1) -and $next -le 10) {'
$limitNew = 'elseif ($generation -eq $validated -and $next -eq ($validated + 1) -and $next -le 14) {'
if (-not $patched.Contains($limitOld)) {
    throw 'Could not extend the Aurum Pi4 autonomous next-generation limit to generation 14.'
}
$patched = $patched.Replace($limitOld, $limitNew)

$guardOld = 'if ($trialGeneration -lt 1 -or $trialGeneration -gt 10) {'
$guardNew = 'if ($trialGeneration -lt 1 -or $trialGeneration -gt 14) {'
if (-not $patched.Contains($guardOld)) {
    throw 'Could not extend the Aurum Pi4 supported-generation guard to generation 14.'
}
$patched = $patched.Replace($guardOld, $guardNew)

$marker = 'try {' + $newline + '    [IO.File]::WriteAllText($trialPath, $controlledTrial, [Text.UTF8Encoding]::new($false))'
$injected = ". '$extensionPath'" + $newline + $newline + $marker
if (-not $patched.Contains($marker)) {
    throw 'Could not locate the Aurum Pi4 generator-extension insertion point.'
}
$patched = $patched.Replace($marker, $injected)

try {
    [IO.File]::WriteAllText($basePath, $patched, [Text.UTF8Encoding]::new($false))
    & $basePath -OutputDirectory $OutputDirectory -RunTag $RunTag
}
finally {
    [IO.File]::WriteAllText($basePath, $original, [Text.UTF8Encoding]::new($false))
}
