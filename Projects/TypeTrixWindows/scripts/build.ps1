$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$Build = Join-Path $Root 'build'

cmake -S $Root -B $Build -A x64
cmake --build $Build --config Release --parallel
ctest --test-dir $Build -C Release --output-on-failure

$Dll = Get-ChildItem -Path $Build -Recurse -Filter TypeTrixTsf.dll | Select-Object -First 1
if (-not $Dll) {
    throw 'TypeTrixTsf.dll was not produced.'
}

Write-Host "TypeTrix built: $($Dll.FullName)"
