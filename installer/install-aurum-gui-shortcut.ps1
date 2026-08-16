#Requires -Version 5.1
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Aurum on BBPI4.lnk"
$openScript = Join-Path $PSScriptRoot "open-aurum-gui.ps1"
$powerShellPath = Join-Path $PSHOME "powershell.exe"
if (-not (Test-Path -LiteralPath $openScript -PathType Leaf)) {
    throw "The Aurum GUI launcher is missing: $openScript"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $powerShellPath
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$openScript`""
$shortcut.WorkingDirectory = Split-Path -Parent $PSScriptRoot
$shortcut.Description = "Open Aurum's bounded GUI on the directly attached BBPI4"
$shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,18"
$shortcut.Save()

Write-Output "AURUM_GUI_SHORTCUT_OK path=$shortcutPath"
