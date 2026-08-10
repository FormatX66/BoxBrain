#Requires -Version 5.1
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scripts = @(
    (Join-Path $PSScriptRoot "open-pi-console.ps1"),
    (Join-Path $PSScriptRoot "watch-pi-console.ps1"),
    (Join-Path $PSScriptRoot "setup-pi-console.ps1"),
    (Join-Path $PSScriptRoot "install-pi-console-shortcut.ps1"),
    (Join-Path $PSScriptRoot "install-pi-console-auto-open.ps1")
)
foreach ($script in $scripts) {
    $tokens = $null
    $errors = $null
    [Management.Automation.Language.Parser]::ParseFile(
        $script,
        [ref]$tokens,
        [ref]$errors
    ) | Out-Null
    if ($errors.Count -gt 0) {
        throw "PowerShell parse failed for $script`: $($errors[0].Message)"
    }
}

$temporaryDirectory = Join-Path (
    [IO.Path]::GetTempPath()
) "boxbrain-pi-console-test-$([Guid]::NewGuid().ToString('N'))"
$shortcutPath = Join-Path $temporaryDirectory "BoxBrain Pi Screen.lnk"
$autoOpenShortcutPath = Join-Path (
    $temporaryDirectory
) "BoxBrain Pi Screen Auto-Open.lnk"
New-Item -ItemType Directory -Path $temporaryDirectory | Out-Null
try {
    & (Join-Path $PSScriptRoot "install-pi-console-shortcut.ps1") `
        -Destination $temporaryDirectory | Out-Null
    if (-not (Test-Path -LiteralPath $shortcutPath -PathType Leaf)) {
        throw "The Pi console shortcut test did not create a shortcut."
    }

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    if ($shortcut.Arguments -notlike "*open-pi-console.ps1*") {
        throw "The Pi console shortcut does not reference the launcher."
    }

    & (Join-Path $PSScriptRoot "install-pi-console-auto-open.ps1") `
        -Destination $temporaryDirectory | Out-Null
    if (-not (Test-Path -LiteralPath $autoOpenShortcutPath -PathType Leaf)) {
        throw "The Pi console auto-open test did not create a shortcut."
    }

    $autoOpenShortcut = $shell.CreateShortcut($autoOpenShortcutPath)
    if ($autoOpenShortcut.Arguments -notlike "*watch-pi-console.ps1*") {
        throw "The Pi console auto-open shortcut does not reference the watcher."
    }
    if ($autoOpenShortcut.Arguments -notlike "*-WindowStyle Hidden*") {
        throw "The Pi console watcher is not configured to start hidden."
    }

    # Installing the same definition twice must be safe and idempotent.
    & (Join-Path $PSScriptRoot "install-pi-console-auto-open.ps1") `
        -Destination $temporaryDirectory | Out-Null
    & (Join-Path $PSScriptRoot "install-pi-console-auto-open.ps1") `
        -Destination $temporaryDirectory `
        -Remove `
        -Confirm:$false | Out-Null
    if (Test-Path -LiteralPath $autoOpenShortcutPath) {
        throw "The Pi console auto-open shortcut removal test failed."
    }
}
finally {
    if (Test-Path -LiteralPath $shortcutPath) {
        Remove-Item -LiteralPath $shortcutPath -Force
    }
    if (Test-Path -LiteralPath $temporaryDirectory) {
        Remove-Item -LiteralPath $temporaryDirectory -Force
    }
}

Write-Output "Pi console Windows script tests passed."
