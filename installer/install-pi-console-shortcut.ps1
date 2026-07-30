#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$LauncherPath,
    [string]$Destination = [Environment]::GetFolderPath("Desktop"),
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($LauncherPath)) {
    $LauncherPath = Join-Path $PSScriptRoot "open-pi-console.ps1"
}
$resolvedLauncher = (Resolve-Path -LiteralPath $LauncherPath).Path
if (-not (Test-Path -LiteralPath $Destination -PathType Container)) {
    throw "Shortcut destination does not exist: $Destination"
}

$shortcutPath = Join-Path $Destination "BoxBrain Pi Screen.lnk"
if ((Test-Path -LiteralPath $shortcutPath) -and -not $Force) {
    throw "Shortcut already exists. Use -Force only to replace this exact shortcut."
}

$powerShellPath = Join-Path $PSHOME "powershell.exe"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $powerShellPath
$shortcut.Arguments = (
    '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $resolvedLauncher
)
$shortcut.WorkingDirectory = Split-Path -Parent $resolvedLauncher
$shortcut.Description = "Open the BoxBrain Raspberry Pi console through SSH"
$shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,18"
$shortcut.Save()

Write-Output $shortcutPath
