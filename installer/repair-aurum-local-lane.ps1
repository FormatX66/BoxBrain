#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "BoxBrain\AurumLocalLane"),
    [switch]$StartNow
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Read-JsonFile {
    param([Parameter(Mandatory)][string]$Path, [int]$MaximumBytes = 65536)
    $item = Get-Item -LiteralPath $Path -ErrorAction Stop
    if ($item.Length -gt $MaximumBytes) { throw "JSON file exceeds bounded size." }
    return (Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -ErrorAction Stop)
}

function Write-JsonAtomic {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)]$Value)
    $temporary = "$Path.tmp-$PID-$([Guid]::NewGuid().ToString('N'))"
    [IO.File]::WriteAllText($temporary, (($Value | ConvertTo-Json -Depth 10) + [Environment]::NewLine), [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Invoke-GitBounded {
    param([Parameter(Mandatory)][string[]]$Arguments)
    $old = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = @(& $script:Git @Arguments 2>&1)
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

function Start-OrRepairScheduledLane {
    param(
        [Parameter(Mandatory)][string]$WatcherPath,
        [Parameter(Mandatory)][string]$ConfigPath,
        [Parameter(Mandatory)][string]$BinRoot
    )
    $taskName = "BoxBrain Aurum Local Lane"
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($null -eq $task) {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        $arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -ConfigPath "{1}" -Mode Watch' -f $WatcherPath, $ConfigPath
        $action = New-ScheduledTaskAction -Execute $script:PowerShell -Argument $arguments -WorkingDirectory $BinRoot
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
        $principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 2) -ExecutionTimeLimit ([TimeSpan]::Zero)
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Bounded BoxBrain lane for BBPI4 Aurum deploy/verify only." -Force | Out-Null
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
    }
    if ($StartNow.IsPresent -and $task.State -ne 'Running') {
        Start-ScheduledTask -TaskName $taskName
    }
    return [string]$task.State
}

$resolvedInstallRoot = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
$configPath = Join-Path $resolvedInstallRoot "config.json"
$binRoot = Join-Path $resolvedInstallRoot "bin"
$installedWatcher = Join-Path $binRoot "watch-aurum-local-lane.ps1"

if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    [pscustomobject]@{
        schema_version = 1
        repaired = $false
        started = $false
        decision = "existing-approval-missing"
        authorization_mutated = $false
        deployment_performed = $false
        bbpi4_touched = $false
    } | ConvertTo-Json -Depth 6
    exit 2
}

$config = Read-JsonFile -Path $configPath
if ([int]$config.schema_version -ne 1) { throw "Aurum lane configuration schema is unsupported." }
$repo = [IO.Path]::GetFullPath([string]$config.repository_root).TrimEnd('\')
$expectedRepoParent = $resolvedInstallRoot + '\'
if (-not (($repo + '\').StartsWith($expectedRepoParent, [StringComparison]::OrdinalIgnoreCase))) {
    throw "Existing Aurum lane repository escaped the approved install root."
}
if (-not (Test-Path -LiteralPath $repo -PathType Container)) { throw "Existing Aurum lane repository is unavailable." }
if (-not (Test-Path -LiteralPath $installedWatcher -PathType Leaf)) { throw "Existing approved Aurum lane watcher is unavailable." }

$script:Git = (Get-Command git.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$script:PowerShell = (Get-Command powershell.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source

$remote = Invoke-GitBounded @("-C", $repo, "remote", "get-url", "origin")
$remoteUrl = [string]($remote.Output | Select-Object -First 1)
if ($remote.ExitCode -ne 0 -or $remoteUrl -notmatch '(?i)github\.com[:/]FormatX66/BoxBrain(?:\.git)?$') {
    throw "Existing Aurum lane repository remote is not the approved BoxBrain repository."
}
$status = Invoke-GitBounded @("-C", $repo, "status", "--porcelain", "--untracked-files=no")
if ($status.ExitCode -ne 0 -or $status.Output.Count -gt 0) { throw "Existing Aurum lane repository has unrelated local changes." }
$fetch = Invoke-GitBounded @("-C", $repo, "fetch", "--no-tags", "origin", "+refs/heads/main:refs/remotes/origin/main")
if ($fetch.ExitCode -ne 0) { throw "Could not refresh existing Aurum lane repository." }
$checkout = Invoke-GitBounded @("-C", $repo, "checkout", "main")
if ($checkout.ExitCode -ne 0) { throw "Could not select main in existing Aurum lane repository." }
$merge = Invoke-GitBounded @("-C", $repo, "merge", "--ff-only", "refs/remotes/origin/main")
if ($merge.ExitCode -ne 0) { throw "Existing Aurum lane repository could not fast-forward cleanly." }

$deployer = Join-Path $repo "installer\deploy-aurum-live-to-pi.ps1"
if (-not (Test-Path -LiteralPath $deployer -PathType Leaf)) { throw "Approved Aurum deployer is missing." }
$actualDeployer = (Get-FileHash -LiteralPath $deployer -Algorithm SHA256).Hash.ToLowerInvariant()
$actualWatcher = (Get-FileHash -LiteralPath $installedWatcher -Algorithm SHA256).Hash.ToLowerInvariant()
$actualTree = Get-CodelationTreeHash -Root $repo
$approvedDeployer = ([string]$config.approved_deployer_sha256).ToLowerInvariant()
$approvedWatcher = ([string]$config.approved_watcher_sha256).ToLowerInvariant()
$approvedTree = ([string]$config.approved_codelation_tree_sha256).ToLowerInvariant()

$drift = @()
if ($actualDeployer -ne $approvedDeployer) { $drift += 'deployer_sha256' }
if ($actualWatcher -ne $approvedWatcher) { $drift += 'watcher_sha256' }
if ($actualTree -ne $approvedTree) { $drift += 'codelation_tree_sha256' }

$authorizationMutated = $false
$testsPassed = $false
$decision = 'already-approved'
$currentCommit = [string]((Invoke-GitBounded @("-C", $repo, "rev-parse", "HEAD")).Output | Select-Object -First 1)

if ($drift.Count -gt 0) {
    if (($drift.Count -ne 1) -or ($drift[0] -ne 'codelation_tree_sha256')) {
        [pscustomobject]@{
            schema_version = 1
            repaired = $false
            started = $false
            decision = "review-required"
            drift = $drift
            current_commit = $currentCommit
            tests_passed = $false
            authorization_mutated = $false
            deployment_performed = $false
            bbpi4_touched = $false
        } | ConvertTo-Json -Depth 6
        exit 3
    }

    $python = Get-Command python.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $python) { $python = Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1 }
    if ($null -eq $python) { throw "Python is unavailable for the required local Codelation test confirmation." }
    $pythonPath = $python.Source
    $pythonArgs = @()
    if ([IO.Path]::GetFileName($pythonPath).Equals('py.exe', [StringComparison]::OrdinalIgnoreCase)) { $pythonArgs += '-3' }
    $pythonArgs += @('-m','unittest','discover','-s','Projects/Codelation/tests','-v')
    $old = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        Push-Location $repo
        try {
            $testOutput = @(& $pythonPath @pythonArgs 2>&1)
            $testCode = $LASTEXITCODE
        }
        finally { Pop-Location }
    }
    finally { $ErrorActionPreference = $old }
    if ($testCode -ne 0) {
        $tail = (($testOutput | Select-Object -Last 20 | ForEach-Object { [string]$_ }) -join '; ')
        throw "Codelation tests did not pass; approval was not changed. $tail"
    }
    $testsPassed = $true

    # This is the only automatic authorization mutation allowed here: update the
    # Codelation tree hash after proving deployer and watcher approvals are still
    # unchanged and the exact current source passes its local deterministic tests.
    $config.approved_codelation_tree_sha256 = $actualTree
    $config.approved_commit = $currentCommit
    if ($config.PSObject.Properties.Name -contains 'refreshed_at') {
        $config.refreshed_at = [DateTimeOffset]::UtcNow.ToString('o')
    }
    else {
        $config | Add-Member -NotePropertyName refreshed_at -NotePropertyValue ([DateTimeOffset]::UtcNow.ToString('o'))
    }
    Write-JsonAtomic -Path $configPath -Value $config
    $authorizationMutated = $true
    $decision = 'codelation-only-refresh-applied'
}

$taskState = Start-OrRepairScheduledLane -WatcherPath $installedWatcher -ConfigPath $configPath -BinRoot $binRoot
$authorizationScope = if ($authorizationMutated) { 'codelation-tree-hash-only' } else { 'none' }
[pscustomobject]@{
    schema_version = 1
    repaired = $true
    started = [bool]$StartNow
    task_state_observed_before_start = $taskState
    decision = $decision
    drift = $drift
    current_commit = $currentCommit
    tests_passed = $testsPassed
    authorization_mutated = $authorizationMutated
    authorization_scope = $authorizationScope
    deployment_performed = $false
    bbpi4_touched = $false
} | ConvertTo-Json -Depth 6
