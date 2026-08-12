#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$RepositoryRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $RepositoryRoot = Split-Path -Parent $PSScriptRoot
}
$repository = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$modulePath = Join-Path $repository "installer\codex-bridge\BoxBrainCodexBridge.psm1"
$dispatcherSource = Join-Path $repository "installer\codex-bridge\dispatch-readonly-repository-status.ps1"
Import-Module $modulePath -Force

$script:Passed = 0
$script:Failed = 0
$script:Failures = [Collections.Generic.List[string]]::new()

function Assert-BridgeTest {
    param([Parameter(Mandatory)][bool]$Condition, [Parameter(Mandatory)][string]$Message)
    if (-not $Condition) { throw $Message }
}

function Invoke-BridgeTest {
    param([Parameter(Mandatory)][string]$Name, [Parameter(Mandatory)][scriptblock]$Body)
    try {
        & $Body
        $script:Passed++
        Write-Host "PASS $Name"
    }
    catch {
        $script:Failed++
        $script:Failures.Add("${Name}: $($_.Exception.Message)")
        Write-Host "FAIL $Name"
    }
}

function New-TestTaskText {
    param(
        [string]$Id = "BB-990",
        [string]$Status = "PENDING",
        [string]$Title = "Report repository status",
        [string]$TaskType = "READ_ONLY_REPOSITORY_STATUS",
        [string]$Executor = "readonly-repository-status",
        [string]$Extra = ""
    )
    return @"
[TASK $Id]
STATUS: $Status
TITLE: $Title
TASK_TYPE: $TaskType
EXECUTOR: $Executor
$Extra
END TASK
"@
}

$testRoot = Join-Path ([IO.Path]::GetTempPath()) ("BoxBrainCodexBridgeTests-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $testRoot | Out-Null

try {
    $validText = New-TestTaskText
    $validTask = (ConvertFrom-BridgeQueueText -Text $validText -Source "test").Tasks["BB-990"]

    Invoke-BridgeTest "duplicate-work prevention" {
        $state = New-BridgeState
        $state["tasks"]["BB-990"] = @{
            status = "COMPLETE"
            task_hash = $validTask.Hash
            result_hash = ("a" * 64)
            dispatcher_hash = ("b" * 64)
        }
        Assert-BridgeTest (Test-BridgeTaskVerifiedComplete -Task $validTask -State $state -DispatcherHash ("b" * 64)) "Verified duplicate was not skipped."
        $changedTask = (ConvertFrom-BridgeQueueText -Text (New-TestTaskText -Title "Changed status report") -Source "test").Tasks["BB-990"]
        Assert-BridgeTest (-not (Test-BridgeTaskVerifiedComplete -Task $changedTask -State $state -DispatcherHash ("b" * 64))) "Changed work was incorrectly treated as a duplicate."
    }

    Invoke-BridgeTest "malformed queue entries" {
        $malformed = @"
[TASK ../../escape]
STATUS: PENDING
TITLE: Invalid ID
END TASK
[TASK BB-991]
STATUS: MADE_UP
TITLE: Invalid status
END TASK
[TASK BB-992]
STATUS: PENDING
TITLE: Missing terminator
"@
        $parsed = ConvertFrom-BridgeQueueText -Text $malformed -Source "malformed"
        Assert-BridgeTest ($parsed.Tasks.Count -eq 0) "Malformed tasks were accepted."
        Assert-BridgeTest ($parsed.Errors.Count -eq 3) "Malformed task errors were not bounded and reported."
    }

    Invoke-BridgeTest "unknown task rejection" {
        $unknownTask = (ConvertFrom-BridgeQueueText -Text (New-TestTaskText -Executor "not-approved") -Source "test").Tasks["BB-990"]
        $trust = @{ schema_version = 1; dispatchers = @{} }
        $decision = Test-BridgeDispatcherTrust -Task $unknownTask -Trust $trust -InstallRoot $testRoot
        Assert-BridgeTest (-not $decision.Trusted -and $decision.Reason -eq "unknown_executor") "Unknown executor was not rejected."
    }

    Invoke-BridgeTest "allowlist enforcement" {
        $installRoot = Join-Path $testRoot "allowlist"
        $binRoot = Join-Path $installRoot "bin"
        New-Item -ItemType Directory -Path $binRoot -Force | Out-Null
        $installedScript = Join-Path $binRoot "dispatch-readonly-repository-status.ps1"
        Copy-Item -LiteralPath $dispatcherSource -Destination $installedScript
        $hash = Get-BridgeFileSha256 $installedScript
        $trust = @{
            schema_version = 1
            dispatchers = @{
                "readonly-repository-status" = @{
                    task_types = @("READ_ONLY_REPOSITORY_STATUS")
                    installed_script = "bin\dispatch-readonly-repository-status.ps1"
                    sha256 = $hash
                    impact = "read_only"
                }
            }
        }
        $approved = Test-BridgeDispatcherTrust -Task $validTask -Trust $trust -InstallRoot $installRoot
        Assert-BridgeTest $approved.Trusted "Locally hash-pinned dispatcher was not accepted."

        $wrongType = (ConvertFrom-BridgeQueueText -Text (New-TestTaskText -TaskType "UNAPPROVED_TYPE") -Source "test").Tasks["BB-990"]
        $typeDecision = Test-BridgeDispatcherTrust -Task $wrongType -Trust $trust -InstallRoot $installRoot
        Assert-BridgeTest (-not $typeDecision.Trusted -and $typeDecision.Reason -eq "task_type_not_allowlisted") "Unapproved task type was accepted."

        Add-Content -LiteralPath $installedScript -Value "# local change"
        $hashDecision = Test-BridgeDispatcherTrust -Task $validTask -Trust $trust -InstallRoot $installRoot
        Assert-BridgeTest (-not $hashDecision.Trusted -and $hashDecision.Reason -eq "dispatcher_hash_mismatch") "Changed executable silently retained authority."

        $unsafeTask = (ConvertFrom-BridgeQueueText -Text (New-TestTaskText -Extra "COMMAND: Write-Output unsafe") -Source "test").Tasks["BB-990"]
        Assert-BridgeTest (-not (Test-BridgeTaskSafety $unsafeTask).Safe) "Arbitrary command text passed safety validation."
    }

    Invoke-BridgeTest "single-instance lock behavior" {
        $lockPath = Join-Path $testRoot "lock\bridge.lock"
        $first = Enter-BridgeLock -Path $lockPath -StaleAfterSeconds 900
        try {
            $held = $false
            try { Enter-BridgeLock -Path $lockPath -StaleAfterSeconds 900 | Out-Null } catch { $held = $_.Exception.Message -eq "BRIDGE_LOCK_HELD" }
            Assert-BridgeTest $held "A second watcher acquired the active lock."
        }
        finally { Exit-BridgeLock $first }
        Assert-BridgeTest (-not (Test-Path -LiteralPath $lockPath)) "Owned lock was not released."
    }

    Invoke-BridgeTest "stale-lock recovery" {
        $lockDirectory = Join-Path $testRoot "stale-lock"
        $lockPath = Join-Path $lockDirectory "bridge.lock"
        New-Item -ItemType Directory -Path $lockDirectory -Force | Out-Null
        $stale = @{ pid = 2147483647; started_at = [DateTimeOffset]::UtcNow.AddDays(-1).ToString("o") } | ConvertTo-Json -Compress
        [IO.File]::WriteAllText($lockPath, $stale)
        $recovered = Enter-BridgeLock -Path $lockPath -StaleAfterSeconds 30
        try {
            Assert-BridgeTest ((Get-ChildItem -LiteralPath $lockDirectory -Filter "bridge.lock.stale-*" | Measure-Object).Count -eq 1) "Stale lock was not preserved as recovery evidence."
        }
        finally { Exit-BridgeLock $recovered }
    }

    Invoke-BridgeTest "Git fetch failure and recovery" {
        $git = (Get-Command git.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
        $remoteUrlOutput = @(& $git -C $repository remote get-url origin)
        $remoteUrl = [string]($remoteUrlOutput | Select-Object -First 1)
        $fetchConfig = @{
            repository_root = $repository
            remote_name = "origin"
            remote_url = $remoteUrl
            remote_ref = "refs/heads/__boxbrain_bridge_missing_test_ref__"
            remote_tracking_ref = "refs/remotes/origin/__boxbrain_bridge_missing_test_ref__"
        }
        $failed = $false
        try { Invoke-BridgeFetch -Config $fetchConfig | Out-Null } catch { $failed = $true }
        Assert-BridgeTest $failed "Missing remote ref did not produce a controlled fetch failure."
        $fetchConfig.remote_ref = "refs/heads/main"
        $fetchConfig.remote_tracking_ref = "refs/remotes/origin/main"
        Assert-BridgeTest (Invoke-BridgeFetch -Config $fetchConfig) "Fetch did not recover when the approved ref became valid."
        Assert-BridgeTest ((Get-BridgeBackoffSeconds -FailureCount 4 -BaseSeconds 10 -MaximumSeconds 60) -eq 60) "Exponential backoff cap is incorrect."
    }

    Invoke-BridgeTest "conflicting local and Git states" {
        $gitParsed = ConvertFrom-BridgeQueueText -Text (New-TestTaskText -Title "Git version") -Source "git"
        $localParsed = ConvertFrom-BridgeQueueText -Text (New-TestTaskText -Title "Local version") -Source "local"
        $merged = Merge-BridgeTaskSources -GitTasks $gitParsed.Tasks -LocalTasks $localParsed.Tasks -State (New-BridgeState)
        Assert-BridgeTest $merged["BB-990"].Conflict "Material Git/local conflict was silently resolved."

        $older = New-TestTaskText -Title "Older"
        $older = $older -replace "END TASK", "CHECKPOINT_AT: 2026-01-01T00:00:00Z`r`nCHECKPOINT: old`r`nEND TASK"
        $newer = New-TestTaskText -Title "Newer"
        $newer = $newer -replace "END TASK", "CHECKPOINT_AT: 2026-01-02T00:00:00Z`r`nCHECKPOINT: new`r`nEND TASK"
        $timestampMerge = Merge-BridgeTaskSources `
            -GitTasks (ConvertFrom-BridgeQueueText $older "git").Tasks `
            -LocalTasks (ConvertFrom-BridgeQueueText $newer "local").Tasks `
            -State (New-BridgeState)
        Assert-BridgeTest (-not $timestampMerge["BB-990"].Conflict -and $timestampMerge["BB-990"].Title -eq "Newer") "Latest verified checkpoint was not selected."
    }

    Invoke-BridgeTest "completed-task verification" {
        $dispatcherHash = "c" * 64
        $resultHash = "d" * 64
        $result = @{ summary = "Read-only repository status recorded." }
        $completionText = Add-BridgeCompletionBlock -Text "" -Task $validTask -Result $result `
            -ResultHash $resultHash -DispatcherHash $dispatcherHash
        $completion = ConvertFrom-BridgeQueueText -Text $completionText -Source "complete"
        Assert-BridgeTest (Test-BridgeCompletionRecord -Task $validTask -CompletionTasks $completion.Tasks -DispatcherHash $dispatcherHash) "Valid completion record was not trusted."
        $tampered = $completionText -replace $validTask.Hash, ("e" * 64)
        $tamperedCompletion = ConvertFrom-BridgeQueueText -Text $tampered -Source "complete"
        Assert-BridgeTest (-not (Test-BridgeCompletionRecord -Task $validTask -CompletionTasks $tamperedCompletion.Tasks -DispatcherHash $dispatcherHash)) "Mismatched task completion was accepted."
    }

    Invoke-BridgeTest "verified checkpoint resume" {
        $resultDirectory = Join-Path $testRoot "results"
        New-Item -ItemType Directory -Path $resultDirectory -Force | Out-Null
        $resultPath = Join-Path $resultDirectory "BB-990-result.json"
        $resultObject = @{ schema_version = 1; task_id = "BB-990"; verified = $true; summary = "Read-only status complete." }
        [IO.File]::WriteAllText($resultPath, (($resultObject | ConvertTo-Json -Compress) + [Environment]::NewLine))
        $raw = [IO.File]::ReadAllText($resultPath)
        $state = New-BridgeState
        $state.tasks["BB-990"] = @{
            status = "RESULT_READY"; task_hash = $validTask.Hash; dispatcher_hash = ("f" * 64)
            result_hash = Get-BridgeSha256String $raw; result_path = $resultPath
        }
        $checkpoint = Get-BridgeResultCheckpoint -Task $validTask -State $state -DispatcherHash ("f" * 64) -ResultDirectory $resultDirectory
        Assert-BridgeTest ($null -ne $checkpoint -and $checkpoint.Result.verified) "Valid saved result could not resume."
        $state.tasks["BB-990"].result_hash = "0" * 64
        Assert-BridgeTest ($null -eq (Get-BridgeResultCheckpoint -Task $validTask -State $state -DispatcherHash ("f" * 64) -ResultDirectory $resultDirectory)) "Tampered saved result was resumed."
    }

    Invoke-BridgeTest "no credential leakage" {
        $logPath = Join-Path $testRoot "logs\bridge.jsonl"
        $secretOne = "ghp_1234567890abcdefghijklmnop"
        $secretTwo = "sk-1234567890abcdefghijklmnop"
        Write-BridgeLog -Path $logPath -Event "test" -Detail "token=$secretOne authorization=$secretTwo"
        $logText = [IO.File]::ReadAllText($logPath)
        Assert-BridgeTest (-not $logText.Contains($secretOne) -and -not $logText.Contains($secretTwo)) "A secret-like value reached structured logs."
        Assert-BridgeTest ($logText.Contains("REDACTED")) "Secret-like values were not visibly redacted."

        $checkpointText = Set-BridgeTaskCheckpointText -Text $validText -TaskId "BB-990" -Status RETRY `
            -Checkpoint "token=$secretOne retry later"
        Assert-BridgeTest (-not $checkpointText.Contains($secretOne)) "A secret-like value reached a queue checkpoint."
    }
}
finally {
    $resolvedTestRoot = [IO.Path]::GetFullPath($testRoot)
    $tempPrefix = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if ($resolvedTestRoot.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $resolvedTestRoot)) {
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }
}

Write-Host ""
Write-Host "Bridge tests: $($script:Passed) passed, $($script:Failed) failed"
if ($script:Failed -gt 0) {
    $script:Failures | ForEach-Object { Write-Host "  $_" }
    exit 1
}
