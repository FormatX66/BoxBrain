#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$Destination = ([Environment]::GetFolderPath("Desktop"))
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$launcher = Join-Path $PSScriptRoot "open-morris-console.ps1"
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw "The Morris console launcher is missing: $launcher"
}
if (-not (Test-Path -LiteralPath $Destination -PathType Container)) {
    throw "Shortcut destination does not exist: $Destination"
}

$shortcutPath = Join-Path $Destination "Morris PC Remote.lnk"
if (Test-Path -LiteralPath $shortcutPath) {
    Write-Output "Existing Morris PC Remote shortcut preserved."
    return
}

$powershell = (Get-Command powershell.exe -ErrorAction Stop).Source
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $powershell
$shortcut.Arguments = (
    '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $launcher
)
$shortcut.WorkingDirectory = Split-Path -Parent $launcher
$shortcut.Description = "Open Morris PC through BoxBrain's private Pi tunnel"
$shortcut.Save()

Write-Output "Created $shortcutPath"
