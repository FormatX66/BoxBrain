#Requires -Version 5.1
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$RepositoryRoot,
    [string]$RemoteName = "origin",
    [string]$RemoteBranch = "main",
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "BoxBrain\CodexBridge"),
    [ValidateRange(15, 3600)][int]$PollSeconds = 60,
    [switch]$ApproveDispatcherManifest,
    [switch]$StartNow
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$taskName = "BoxBrain Git Local Codex Bridge"
if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $RepositoryRoot = Split-Path -Parent $PSScriptRoot
}
$sourceRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$git = (Get-Command git.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$remoteOutput = @(& $git -C $sourceRoot remote get-url $RemoteName 2>$null)
$remoteExitCode = $LASTEXITCODE
$remoteUrl = [string]($remoteOutput | Select-Object -First 1)
if ($remoteExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($remoteUrl)) {
    throw "The configured Git remote is unavailable."
}
if ($remoteUrl -notmatch '(?i)github\.com[:/]FormatX66/BoxBrain(?:\.git)?$') {
    throw "Only the configured FormatX66/BoxBrain remote can be installed."
}
if ($RemoteName -notmatch '^[A-Za-z0-9._-]+$') { throw "The remote name is invalid." }
if ($RemoteBranch -notmatch '^[A-Za-z0-9._/-]+$' -or $RemoteBranch -match '\.\.|\\') {
    throw "The remote branch is invalid."
}
if (-not $ApproveDispatcherManifest) {
    throw "Local dispatcher review is required. Re-run with -ApproveDispatcherManifest after reviewing installer/codex-bridge/dispatchers.json and its scripts."
}

$resolvedInstallRoot = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
$expectedParent = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "BoxBrain")).TrimEnd('\') + '\'
if (-not ($resolvedInstallRoot + '\').StartsWith($expectedParent, [StringComparison]::OrdinalIgnoreCase)) {
    throw "The install root must remain under the current user's LocalAppData BoxBrain directory."
}

$binRoot = Join-Path $resolvedInstallRoot "bin"
$runtimeRepo = Join-Path $resolvedInstallRoot "repository"
$logsRoot = Join-Path $resolvedInstallRoot "logs"
$resultsRoot = Join-Path $resolvedInstallRoot "results"
$stateRoot = Join-Path $resolvedInstallRoot "state"
$configPath = Join-Path $resolvedInstallRoot "config.json"
$trustPath = Join-Path $resolvedInstallRoot "trusted-dispatchers.json"
$manifestPath = Join-Path $sourceRoot "installer\codex-bridge\dispatchers.json"
$sourceModule = Join-Path $sourceRoot "installer\codex-bridge\BoxBrainCodexBridge.psm1"
$sourceWatcher = Join-Path $sourceRoot "installer\codex-bridge\watch-git-local-codex-bridge.ps1"
foreach ($path in @($manifestPath, $sourceModule, $sourceWatcher)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "A required reviewed bridge file is missing." }
}

if ($PSCmdlet.ShouldProcess($resolvedInstallRoot, "Install locally reviewed BoxBrain Git bridge")) {
    foreach ($directory in @($resolvedInstallRoot, $binRoot, $logsRoot, $resultsRoot, $stateRoot)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }

    $existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existingTask) {
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    }

    if (-not (Test-Path -LiteralPath $runtimeRepo -PathType Container)) {
        & $git clone --no-tags --single-branch --branch $RemoteBranch $remoteUrl $runtimeRepo 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not create the isolated bridge repository." }
    }
    else {
        $actualUrlOutput = @(& $git -C $runtimeRepo remote get-url $RemoteName 2>$null)
        $actualUrlExitCode = $LASTEXITCODE
        $actualUrl = [string]($actualUrlOutput | Select-Object -First 1)
        if ($actualUrlExitCode -ne 0) { throw "The existing bridge repository remote is unavailable." }
        if ($actualUrl -ne $remoteUrl) { throw "The existing bridge repository uses a different remote URL." }
        $dirty = @(& $git -C $runtimeRepo status --porcelain)
        if ($dirty.Count -gt 0) { throw "The isolated bridge repository contains local changes; inspect them before reinstalling." }
        & $git -C $runtimeRepo fetch --no-tags $RemoteName "+refs/heads/${RemoteBranch}:refs/remotes/${RemoteName}/${RemoteBranch}" 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not refresh the isolated bridge repository." }
        & $git -C $runtimeRepo checkout $RemoteBranch 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not select the configured bridge branch." }
        & $git -C $runtimeRepo merge --ff-only "refs/remotes/${RemoteName}/${RemoteBranch}" 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "The bridge repository could not fast-forward cleanly." }
    }

    Copy-Item -LiteralPath $sourceModule -Destination (Join-Path $binRoot "BoxBrainCodexBridge.psm1") -Force
    Copy-Item -LiteralPath $sourceWatcher -Destination (Join-Path $binRoot "watch-git-local-codex-bridge.ps1") -Force

    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json -ErrorAction Stop
    if ($manifest.schema_version -ne 1) { throw "The reviewed dispatcher manifest version is unsupported." }
    $trusted = @{}
    foreach ($entry in @($manifest.dispatchers)) {
        $id = [string]$entry.id
        if ($id -notmatch '^[a-z0-9][a-z0-9-]{2,63}$') { throw "A dispatcher ID is invalid." }
        if ([string]$entry.impact -ne "read_only") { throw "Only read-only dispatchers can be installed by this bridge version." }
        $relativeSource = ([string]$entry.script -replace '/', '\')
        if ($relativeSource -match '\.\.' -or [IO.Path]::IsPathRooted($relativeSource)) { throw "A dispatcher path is unsafe." }
        $sourceScript = [IO.Path]::GetFullPath((Join-Path $sourceRoot $relativeSource))
        $sourcePrefix = $sourceRoot.TrimEnd('\') + '\'
        if (-not $sourceScript.StartsWith($sourcePrefix, [StringComparison]::OrdinalIgnoreCase)) { throw "A dispatcher path escapes the repository." }
        if (-not (Test-Path -LiteralPath $sourceScript -PathType Leaf)) { throw "A reviewed dispatcher script is missing." }
        $installedName = "dispatch-$id.ps1"
        $installedPath = Join-Path $binRoot $installedName
        Copy-Item -LiteralPath $sourceScript -Destination $installedPath -Force
        $types = @($entry.task_types | ForEach-Object { ([string]$_).ToUpperInvariant() })
        foreach ($type in $types) {
            if ($type -notmatch '^[A-Z][A-Z0-9_]{2,63}$') { throw "A dispatcher task type is invalid." }
        }
        $trusted[$id] = [ordered]@{
            task_types = $types
            installed_script = "bin\$installedName"
            sha256 = (Get-FileHash -LiteralPath $installedPath -Algorithm SHA256).Hash.ToLowerInvariant()
            impact = "read_only"
            approved_at = [DateTimeOffset]::UtcNow.ToString("o")
            approved_by = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        }
    }
    $trust = [ordered]@{
        schema_version = 1
        source_commit = (& $git -C $sourceRoot rev-parse HEAD).Trim()
        dispatchers = $trusted
    }
    [IO.File]::WriteAllText(
        $trustPath,
        (($trust | ConvertTo-Json -Depth 8) + [Environment]::NewLine),
        [Text.UTF8Encoding]::new($false)
    )

    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $codexNonInteractiveAvailable = $false
    try {
        $codexCommand = Get-Command codex.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1
        & $codexCommand.Source --version 2>&1 | Out-Null
        $codexNonInteractiveAvailable = $LASTEXITCODE -eq 0
    }
    catch { $codexNonInteractiveAvailable = $false }
    $desktop = [Environment]::GetFolderPath("Desktop")
    $config = [ordered]@{
        schema_version = 1
        installed_for = $identity
        install_root = $resolvedInstallRoot
        repository_root = $runtimeRepo
        remote_name = $RemoteName
        remote_url = $remoteUrl
        remote_ref = "refs/heads/$RemoteBranch"
        remote_tracking_ref = "refs/remotes/$RemoteName/$RemoteBranch"
        queue_path = ".codex\queue\QUEUE.md"
        complete_path = ".codex\queue\COMPLETE.md"
        desktop_queue_path = Join-Path $desktop "Codex Cue.txt"
        desktop_complete_path = Join-Path $desktop "Cue Complete.txt"
        pending_notification_path = Join-Path $desktop "BoxBrain Pending Codex Work.txt"
        state_path = Join-Path $stateRoot "bridge-state.json"
        health_path = Join-Path $stateRoot "health.json"
        log_path = Join-Path $logsRoot "bridge.jsonl"
        lock_path = Join-Path $stateRoot "bridge.lock"
        trust_path = $trustPath
        result_directory = $resultsRoot
        poll_seconds = $PollSeconds
        stale_lock_seconds = [Math]::Max(300, $PollSeconds * 5)
        maximum_tasks_per_cycle = 3
        codex_noninteractive_available = $codexNonInteractiveAvailable
    }
    [IO.File]::WriteAllText(
        $configPath,
        (($config | ConvertTo-Json -Depth 6) + [Environment]::NewLine),
        [Text.UTF8Encoding]::new($false)
    )

    if (-not (& $git -C $runtimeRepo config user.name)) {
        & $git -C $runtimeRepo config user.name "BoxBrain Queue Watcher"
    }
    if (-not (& $git -C $runtimeRepo config user.email)) {
        & $git -C $runtimeRepo config user.email "56238984+FormatX66@users.noreply.github.com"
    }

    $powerShell = (Get-Command powershell.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    $watcher = Join-Path $binRoot "watch-git-local-codex-bridge.ps1"
    $arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -ConfigPath "{1}" -Mode Watch' -f $watcher, $configPath
    $action = New-ScheduledTaskAction -Execute $powerShell -Argument $arguments -WorkingDirectory $binRoot
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
    $principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -MultipleInstances IgnoreNew -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 2) -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings -Description "Safely reconcile the BoxBrain Git queue with locally pinned dispatchers." -Force | Out-Null

    if ($StartNow) {
        Start-ScheduledTask -TaskName $taskName
    }
}

[pscustomobject]@{
    task_name = $taskName
    installed_for = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    install_root = $resolvedInstallRoot
    remote = $remoteUrl
    branch = $RemoteBranch
    poll_seconds = $PollSeconds
    started = [bool]$StartNow
}
