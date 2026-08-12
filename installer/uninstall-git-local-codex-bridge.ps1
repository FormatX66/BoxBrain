#Requires -Version 5.1
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "BoxBrain\CodexBridge"),
    [switch]$RemoveLocalState
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$taskName = "BoxBrain Git Local Codex Bridge"
$resolvedRoot = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
$expected = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "BoxBrain\CodexBridge")).TrimEnd('\')
if ($resolvedRoot -ne $expected) { throw "Refusing to uninstall from an unexpected path." }

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    if ($PSCmdlet.ShouldProcess($taskName, "Stop and unregister scheduled task")) {
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }
}

foreach ($path in @(
    (Join-Path $resolvedRoot "bin"),
    (Join-Path $resolvedRoot "config.json"),
    (Join-Path $resolvedRoot "trusted-dispatchers.json")
)) {
    if ((Test-Path -LiteralPath $path) -and $PSCmdlet.ShouldProcess($path, "Remove installed bridge runtime")) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
}

if ($RemoveLocalState) {
    foreach ($path in @(
        (Join-Path $resolvedRoot "repository"),
        (Join-Path $resolvedRoot "logs"),
        (Join-Path $resolvedRoot "results"),
        (Join-Path $resolvedRoot "state"),
        (Join-Path $resolvedRoot "backups")
    )) {
        if ((Test-Path -LiteralPath $path) -and $PSCmdlet.ShouldProcess($path, "Remove bridge local state")) {
            Remove-Item -LiteralPath $path -Recurse -Force
        }
    }
}

[pscustomobject]@{
    task_removed = -not [bool](Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue)
    state_preserved = -not [bool]$RemoveLocalState
    install_root = $resolvedRoot
}
