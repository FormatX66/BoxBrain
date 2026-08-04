#Requires -Version 5.1
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$WatcherPath,
    [string]$Destination = [Environment]::GetFolderPath("Startup"),
    [switch]$Force,
    [switch]$StartNow,
    [switch]$Remove
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($WatcherPath)) {
    $WatcherPath = Join-Path $PSScriptRoot "watch-pi-console.ps1"
}
$resolvedWatcher = (Resolve-Path -LiteralPath $WatcherPath).Path
if (-not (Test-Path -LiteralPath $Destination -PathType Container)) {
    throw "Shortcut destination does not exist: $Destination"
}

$shortcutPath = Join-Path $Destination "BoxBrain Pi Screen Auto-Open.lnk"
if ($Remove) {
    if (
        (Test-Path -LiteralPath $shortcutPath -PathType Leaf) -and
        $PSCmdlet.ShouldProcess($shortcutPath, "Remove BoxBrain auto-open shortcut")
    ) {
        Remove-Item -LiteralPath $shortcutPath -Force
    }
    Write-Output $shortcutPath
    return
}

$powerShellPath = Join-Path $PSHOME "powershell.exe"
$arguments = (
    '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f
    $resolvedWatcher
)
$needsWrite = $true
if (Test-Path -LiteralPath $shortcutPath -PathType Leaf) {
    $shell = New-Object -ComObject WScript.Shell
    $existing = $shell.CreateShortcut($shortcutPath)
    $isCurrent = (
        $existing.TargetPath -eq $powerShellPath -and
        $existing.Arguments -eq $arguments
    )
    if ($isCurrent) {
        $needsWrite = $false
    }
    elseif (-not $Force) {
        throw "A different startup shortcut already exists. Use -Force to replace only this exact path."
    }
}

if (
    $needsWrite -and
    $PSCmdlet.ShouldProcess($shortcutPath, "Install BoxBrain auto-open shortcut")
) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $powerShellPath
    $shortcut.Arguments = $arguments
    $shortcut.WorkingDirectory = Split-Path -Parent $resolvedWatcher
    $shortcut.Description = "Open the BoxBrain Pi screen when its SSH link appears"
    $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,18"
    $shortcut.WindowStyle = 7
    $shortcut.Save()
}

if ($StartNow -and $PSCmdlet.ShouldProcess($resolvedWatcher, "Start BoxBrain console watcher")) {
    Start-Process `
        -FilePath $powerShellPath `
        -ArgumentList $arguments `
        -WindowStyle Hidden
}

Write-Output $shortcutPath
