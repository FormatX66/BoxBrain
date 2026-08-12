#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$RepositoryRoot,
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "BoxBrain\AurumLocalLane"),
    [ValidateRange(30, 3600)][int]$PollSeconds = 60,
    [switch]$ApproveAurumLane,
    [switch]$StartNow
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $ApproveAurumLane) {
    throw "Local approval is required. Re-run with -ApproveAurumLane after reviewing the bounded Aurum lane scripts."
}

if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $RepositoryRoot = Split-Path -Parent $PSScriptRoot
}
$sourceRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$git = (Get-Command git.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$powerShell = (Get-Command powershell.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$keyPath = Join-Path $HOME ".ssh\boxbrain_pi_ed25519"
if (-not (Test-Path -LiteralPath $keyPath -PathType Leaf)) {
    throw "The already-authorized BoxBrain Pi key is missing at $keyPath."
}

function Invoke-GitBounded {
    param([Parameter(Mandatory)][string[]]$Arguments)
    $old = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = @(& $git @Arguments 2>&1)
        $code = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $old }
    return [pscustomobject]@{ ExitCode = $code; Output = $output }
}

function Get-CodelationTreeHash {
    param([Parameter(Mandatory)][string]$Root)
    $tree = Join-Path $Root "Projects\Codelation"
    if (-not (Test-Path -LiteralPath $tree -PathType Container)) { throw "Codelation source is missing." }
    $prefix = $tree.TrimEnd('\') + '\'
    $lines = @(
        Get-ChildItem -LiteralPath $tree -File -Recurse | Sort-Object FullName | ForEach-Object {
            $relative = $_.FullName.Substring($prefix.Length).Replace('\','/')
            $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            "$relative|$hash"
        }
    )
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes(($lines -join "`n"))
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
    }
    finally { $sha.Dispose() }
}

$remote = Invoke-GitBounded @("-C", $sourceRoot, "remote", "get-url", "origin")
$remoteUrl = [string]($remote.Output | Select-Object -First 1)
if ($remote.ExitCode -ne 0 -or $remoteUrl -notmatch '(?i)github\.com[:/]FormatX66/BoxBrain(?:\.git)?$') {
    throw "Only FormatX66/BoxBrain may back the Aurum local lane."
}

$resolvedInstallRoot = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
$expectedParent = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "BoxBrain")).TrimEnd('\') + '\'
if (-not ($resolvedInstallRoot + '\').StartsWith($expectedParent, [StringComparison]::OrdinalIgnoreCase)) {
    throw "The Aurum lane install root must remain under LocalAppData\BoxBrain."
}

$binRoot = Join-Path $resolvedInstallRoot "bin"
$stateRoot = Join-Path $resolvedInstallRoot "state"
$runtimeRepo = Join-Path $resolvedInstallRoot "repository"
foreach ($directory in @($resolvedInstallRoot, $binRoot, $stateRoot)) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}

if (-not (Test-Path -LiteralPath $runtimeRepo -PathType Container)) {
    $clone = Invoke-GitBounded @("clone", "--no-tags", "--single-branch", "--branch", "main", $remoteUrl, $runtimeRepo)
    if ($clone.ExitCode -ne 0) { throw "Could not create the isolated Aurum lane repository." }
}
else {
    $status = Invoke-GitBounded @("-C", $runtimeRepo, "status", "--porcelain")
    if ($status.ExitCode -ne 0 -or $status.Output.Count -gt 0) { throw "The isolated Aurum lane repository has local changes." }
    $fetch = Invoke-GitBounded @("-C", $runtimeRepo, "fetch", "--no-tags", "origin", "+refs/heads/main:refs/remotes/origin/main")
    if ($fetch.ExitCode -ne 0) { throw "Could not refresh the isolated Aurum lane repository." }
    $checkout = Invoke-GitBounded @("-C", $runtimeRepo, "checkout", "main")
    if ($checkout.ExitCode -ne 0) { throw "Could not select main in the Aurum lane repository." }
    $merge = Invoke-GitBounded @("-C", $runtimeRepo, "merge", "--ff-only", "refs/remotes/origin/main")
    if ($merge.ExitCode -ne 0) { throw "The Aurum lane repository could not fast-forward cleanly." }
}

$sourceWatcher = Join-Path $sourceRoot "installer\aurum-local-lane\watch-aurum-local-lane.ps1"
if (-not (Test-Path -LiteralPath $sourceWatcher -PathType Leaf)) { throw "Aurum lane watcher is missing." }
$installedWatcher = Join-Path $binRoot "watch-aurum-local-lane.ps1"
Copy-Item -LiteralPath $sourceWatcher -Destination $installedWatcher -Force

$deployer = Join-Path $runtimeRepo "installer\deploy-aurum-live-to-pi.ps1"
if (-not (Test-Path -LiteralPath $deployer -PathType Leaf)) { throw "Aurum deployer is missing from main." }
$approvedCommit = [string]((Invoke-GitBounded @("-C", $runtimeRepo, "rev-parse", "HEAD")).Output | Select-Object -First 1)
$deployerHash = (Get-FileHash -LiteralPath $deployer -Algorithm SHA256).Hash.ToLowerInvariant()
$treeHash = Get-CodelationTreeHash -Root $runtimeRepo
$watcherHash = (Get-FileHash -LiteralPath $installedWatcher -Algorithm SHA256).Hash.ToLowerInvariant()

$configPath = Join-Path $resolvedInstallRoot "config.json"
$config = [ordered]@{
    schema_version = 1
    repository_root = $runtimeRepo
    state_path = (Join-Path $stateRoot "state.json")
    key_path = $keyPath
    poll_seconds = $PollSeconds
    approved_commit = $approvedCommit
    approved_deployer_sha256 = $deployerHash
    approved_codelation_tree_sha256 = $treeHash
    approved_watcher_sha256 = $watcherHash
    installed_at = [DateTimeOffset]::UtcNow.ToString("o")
}
[IO.File]::WriteAllText($configPath, (($config | ConvertTo-Json -Depth 6) + [Environment]::NewLine), [Text.UTF8Encoding]::new($false))

$taskName = "BoxBrain Aurum Local Lane"
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -ConfigPath "{1}" -Mode Watch' -f $installedWatcher, $configPath
$action = New-ScheduledTaskAction -Execute $powerShell -Argument $arguments -WorkingDirectory $binRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 2) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Bounded BoxBrain lane for BBPI4 Aurum deploy/verify only." -Force | Out-Null
if ($StartNow) { Start-ScheduledTask -TaskName $taskName }

[pscustomobject]@{
    task_name = $taskName
    installed = $true
    started = [bool]$StartNow
    target = "BBPI4"
    address = "192.168.0.194"
    approved_commit = $approvedCommit
    deployer_sha256 = $deployerHash
    codelation_tree_sha256 = $treeHash
    watcher_sha256 = $watcherHash
}
