$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$Build = Join-Path $Root 'build'
$Dll = Get-ChildItem -Path $Build -Recurse -Filter TypeTrixTsf.dll | Select-Object -First 1

if (-not $Dll) {
    throw 'TypeTrixTsf.dll not found. Run scripts/build.ps1 first.'
}

& "$env:SystemRoot\System32\regsvr32.exe" /s $Dll.FullName
if ($LASTEXITCODE -ne 0) {
    throw "regsvr32 failed with exit code $LASTEXITCODE"
}

Write-Host 'TypeTrix TSF profile registered for this user.'
Write-Host 'v0 is observation-only: it does not consume keys, retain raw characters, or make corrections.'
Write-Host 'Enable/select the TypeTrix input profile from Windows input/language settings for development testing.'
