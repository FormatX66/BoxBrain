#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$PiAddress = "10.12.194.1",
    [ValidatePattern("^[a-z_][a-z0-9_-]{0,31}$")]
    [string]$PiUser = "kali",
    [string]$KeyPath = (Join-Path $HOME ".ssh\boxbrain_pi_ed25519"),
    [switch]$SkipShortcut
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($PiAddress -ne "10.12.194.1") {
    throw "The first Aurum GUI deployment is bound to the approved USB route 10.12.194.1."
}
if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
    throw "The dedicated BBPI4 SSH key was not found at $KeyPath."
}

$ssh = (Get-Command ssh.exe -CommandType Application -ErrorAction Stop).Source
$scp = (Get-Command scp.exe -CommandType Application -ErrorAction Stop).Source
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$sources = @(
    (Join-Path $repositoryRoot "Projects\Codelation\seed\aurum_gui.py"),
    (Join-Path $repositoryRoot "Projects\Codelation\seed\aurum_gui_context.py"),
    (Join-Path $repositoryRoot "Projects\Codelation\seed\aurum_context.py"),
    (Join-Path $repositoryRoot "Projects\Codelation\field\context_exchange.py"),
    (Join-Path $PSScriptRoot "aurum-gui.sh"),
    (Join-Path $PSScriptRoot "install-aurum-gui-on-pi.sh"),
    (Join-Path $PSScriptRoot "start-aurum-gui-on-pi.sh"),
    (Join-Path $PSScriptRoot "stop-aurum-gui-on-pi.sh")
)
foreach ($source in $sources) {
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required Aurum GUI source is missing: $source"
    }
}

$temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$localStage = [IO.Path]::GetFullPath((
    Join-Path $temporaryRoot "aurum-gui-transfer-$([Guid]::NewGuid().ToString('N'))"
))
if (-not $localStage.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "The local Aurum GUI staging path escaped the Windows temporary directory."
}
New-Item -ItemType Directory -Path $localStage | Out-Null
$transferSources = @()
foreach ($source in $sources) {
    $destination = Join-Path $localStage (Split-Path -Leaf $source)
    if ([IO.Path]::GetExtension($source) -eq ".sh") {
        $content = [IO.File]::ReadAllText($source).Replace("`r`n", "`n")
        [IO.File]::WriteAllText($destination, $content, [Text.UTF8Encoding]::new($false))
    }
    else {
        Copy-Item -LiteralPath $source -Destination $destination
    }
    $transferSources += $destination
}

$target = "$PiUser@$PiAddress"
$remoteRoot = "/tmp/aurum-gui-$([Guid]::NewGuid().ToString('N'))"
$options = @(
    "-i", $KeyPath,
    "-o", "BatchMode=yes",
    "-o", "IdentitiesOnly=yes",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "ConnectTimeout=8"
)

try {
    & $ssh @options $target "umask 077; mkdir -- '$remoteRoot'"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the bounded Aurum GUI staging directory."
    }
    & $scp @options @transferSources "${target}:$remoteRoot/"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not transfer the Aurum GUI candidate."
    }
    & $ssh @options $target "sudo -n sh '$remoteRoot/install-aurum-gui-on-pi.sh' '$remoteRoot'"
    if ($LASTEXITCODE -ne 0) {
        throw "The Aurum GUI installer failed. No package installation was attempted."
    }

    $localHash = $null
    foreach ($moduleSource in @($sources | Where-Object { [IO.Path]::GetExtension($_) -eq ".py" })) {
        $moduleName = Split-Path -Leaf $moduleSource
        $moduleHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $moduleSource).Hash.ToLowerInvariant()
        $remoteHash = (& $ssh @options $target "sha256sum '/opt/boxbrain/codelation/seed/$moduleName' | awk '{print `$1}'").Trim()
        if ($LASTEXITCODE -ne 0 -or $remoteHash -ne $moduleHash) {
            throw "The installed Aurum GUI runtime hash did not match the reviewed candidate: $moduleName"
        }
        if ($moduleName -eq "aurum_gui.py") { $localHash = $moduleHash }
    }
}
finally {
    & $ssh @options $target "rm -f -- '$remoteRoot/aurum_gui.py' '$remoteRoot/aurum_gui_context.py' '$remoteRoot/aurum_context.py' '$remoteRoot/context_exchange.py' '$remoteRoot/aurum-gui.sh' '$remoteRoot/install-aurum-gui-on-pi.sh' '$remoteRoot/start-aurum-gui-on-pi.sh' '$remoteRoot/stop-aurum-gui-on-pi.sh'; rmdir -- '$remoteRoot' 2>/dev/null || true" 2>$null
    $resolvedStage = [IO.Path]::GetFullPath($localStage)
    if ($resolvedStage.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $resolvedStage -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if (-not $SkipShortcut) {
    & (Join-Path $PSScriptRoot "install-aurum-gui-shortcut.ps1")
}

Write-Output "AURUM_GUI_SETUP_OK route=$PiAddress module_sha256=$localHash persistent_service=false"
