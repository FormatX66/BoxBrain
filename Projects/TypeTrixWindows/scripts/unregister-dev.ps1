$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$Build = Join-Path $Root 'build'
$Dll = Get-ChildItem -Path $Build -Recurse -Filter TypeTrixTsf.dll | Select-Object -First 1

if (-not $Dll) {
    throw 'TypeTrixTsf.dll not found in the build directory.'
}

& "$env:SystemRoot\System32\regsvr32.exe" /s /u $Dll.FullName
if ($LASTEXITCODE -ne 0) {
    throw "regsvr32 unregister failed with exit code $LASTEXITCODE"
}

Write-Host 'TypeTrix TSF profile unregistered.'
