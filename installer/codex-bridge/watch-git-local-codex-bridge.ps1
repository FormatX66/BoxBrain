#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$ConfigPath,

    [ValidateSet("Watch", "Once")]
    [string]$Mode = "Watch",

    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$modulePath = Join-Path $PSScriptRoot "BoxBrainCodexBridge.psm1"
Import-Module $modulePath -Force

function Read-BridgeRuntimeConfig {
    $raw = Read-BridgeTextBounded -Path $ConfigPath -MaximumBytes 65536
    $object = $raw | ConvertFrom-Json -ErrorAction Stop
    $config = @{}
    foreach ($property in $object.PSObject.Properties) {
        $config[$property.Name] = $property.Value
    }
    foreach ($required in @(
        "install_root", "repository_root", "remote_name", "remote_url",
        "remote_ref", "remote_tracking_ref", "queue_path", "complete_path",
        "desktop_queue_path", "desktop_complete_path", "pending_notification_path",
        "state_path", "health_path", "log_path", "lock_path", "trust_path",
        "result_directory", "poll_seconds", "stale_lock_seconds", "maximum_tasks_per_cycle",
        "codex_noninteractive_available"
    )) {
        if (-not $config.ContainsKey($required) -or $null -eq $config[$required]) {
            throw "Bridge configuration is missing a required field."
        }
    }
    return $config
}

function Write-BridgeHealth {
    param(
        [Parameter(Mandatory)]$Config,
        [Parameter(Mandatory)][string]$Status,
        [string]$Detail,
        [int]$PendingCount = 0
    )
    $health = [ordered]@{
        schema_version = 1
        status = $Status
        timestamp = [DateTimeOffset]::UtcNow.ToString("o")
        process_id = $PID
        mode = $Mode
        dry_run = [bool]$DryRun
        pending_count = $PendingCount
        codex_noninteractive_available = [bool]$Config["codex_noninteractive_available"]
        detail = Protect-BridgeText $Detail 300
    }
    Write-BridgeJsonFile -Path $Config["health_path"] -Value $health
}

function Get-BridgeTaskMapFromFile {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Source,
        [switch]$Optional
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        if ($Optional) { return [pscustomobject]@{ Tasks = @{}; Errors = @() } }
        throw "Required queue source is unavailable."
    }
    $text = Read-BridgeTextBounded -Path $Path
    return ConvertFrom-BridgeQueueText -Text $text -Source $Source
}

function Set-BridgeFetchFailure {
    param(
        [Parameter(Mandatory)]$Config,
        [Parameter(Mandatory)]$State,
        [Parameter(Mandatory)][string]$Message
    )
    $State["fetch_failures"] = [int]$State["fetch_failures"] + 1
    $delay = Get-BridgeBackoffSeconds -FailureCount $State["fetch_failures"]
    $State["next_retry_at"] = [DateTimeOffset]::UtcNow.AddSeconds($delay).ToString("o")
    $State["last_error"] = Protect-BridgeText $Message 240
    Save-BridgeState -Path $Config["state_path"] -State $State
    Write-BridgeLog -Path $Config["log_path"] -Level warning -Event "git_fetch_failed" `
        -Status "retry_scheduled" -Detail "Retry scheduled after $delay seconds."
    Write-BridgeHealth -Config $Config -Status "degraded" -Detail "Git fetch failed; bounded retry scheduled."
}

function Resume-BridgeReadyPublications {
    param(
        [Parameter(Mandatory)]$Config,
        [Parameter(Mandatory)]$State
    )

    $trust = Read-BridgeTrust -Path $Config["trust_path"]
    foreach ($taskId in @($State["tasks"].Keys | Sort-Object)) {
        $record = $State["tasks"][$taskId]
        if ($record["status"] -ne "RESULT_READY") { continue }
        foreach ($required in @("task_hash", "task_title", "task_type", "executor", "dispatcher_hash", "result_hash", "result_path")) {
            if (-not $record.ContainsKey($required) -or [string]::IsNullOrWhiteSpace([string]$record[$required])) {
                throw "A saved result checkpoint is incomplete."
            }
        }
        $task = [pscustomobject]@{
            Id = $taskId
            Status = "IN_PROGRESS"
            Title = [string]$record["task_title"]
            TaskType = [string]$record["task_type"]
            Executor = [string]$record["executor"]
            Hash = [string]$record["task_hash"]
            Fields = @{}
            Raw = ""
        }
        $trustDecision = Test-BridgeDispatcherTrust -Task $task -Trust $trust -InstallRoot $Config["install_root"]
        if (-not $trustDecision.Trusted -or $trustDecision.Hash -ne [string]$record["dispatcher_hash"]) {
            throw "The saved result no longer matches local dispatcher approval."
        }
        $dispatch = Get-BridgeResultCheckpoint -Task $task -State $State -DispatcherHash $trustDecision.Hash `
            -ResultDirectory $Config["result_directory"]
        if ($null -eq $dispatch) { throw "The saved result checkpoint could not be verified." }

        Complete-BridgeTaskDocuments -Task $task -Result $dispatch.Result -ResultHash $dispatch.Hash `
            -DispatcherHash $trustDecision.Hash -Config $Config
        Publish-BridgeTaskCompletion -Task $task -Config $Config | Out-Null
        $record["status"] = "COMPLETE"
        $record["completed_at"] = [DateTimeOffset]::UtcNow.ToString("o")
        $record["checkpoint"] = "Bounded result committed and pushed through the configured remote."
        $State["last_success_at"] = [DateTimeOffset]::UtcNow.ToString("o")
        $State["fetch_failures"] = 0
        $State["next_retry_at"] = $null
        $State["last_error"] = $null
        Save-BridgeState -Path $Config["state_path"] -State $State
        Write-BridgeLog -Path $Config["log_path"] -Event "result_publication_resumed" `
            -TaskId $taskId -Status "verified" -Detail "Saved dispatcher result published without repeating execution."
    }
}

function Invoke-BridgeCycle {
    $config = Read-BridgeRuntimeConfig
    $lock = $null
    try {
        $lock = Enter-BridgeLock -Path $config["lock_path"] -StaleAfterSeconds ([int]$config["stale_lock_seconds"])
    }
    catch {
        if ($_.Exception.Message -eq "BRIDGE_LOCK_HELD") { return }
        throw
    }

    try {
        $state = Read-BridgeState -Path $config["state_path"]
        if ($state["next_retry_at"]) {
            $retryAt = [DateTimeOffset]::Parse([string]$state["next_retry_at"])
            if ($retryAt -gt [DateTimeOffset]::UtcNow) {
                Write-BridgeHealth -Config $config -Status "backoff" -Detail "Waiting for the next bounded Git retry."
                return
            }
        }

        try {
            Resume-BridgeReadyPublications -Config $config -State $state
        }
        catch {
            Set-BridgeFetchFailure -Config $config -State $state -Message $_.Exception.Message
            return
        }

        try {
            Invoke-BridgeFetch -Config $config -FastForward | Out-Null
            $state["fetch_failures"] = 0
            $state["next_retry_at"] = $null
            $state["last_fetch_at"] = [DateTimeOffset]::UtcNow.ToString("o")
            $state["last_error"] = $null
            Save-BridgeState -Path $config["state_path"] -State $state
            Write-BridgeLog -Path $config["log_path"] -Event "git_fetch_succeeded" -Status "ok"
        }
        catch {
            Set-BridgeFetchFailure -Config $config -State $state -Message $_.Exception.Message
            return
        }

        $repoQueuePath = Join-Path $config["repository_root"] $config["queue_path"]
        $repoCompletePath = Join-Path $config["repository_root"] $config["complete_path"]
        if (-not (Test-Path -LiteralPath $config["desktop_queue_path"] -PathType Leaf)) {
            Write-BridgeTextAtomic -Path $config["desktop_queue_path"] -Text (Read-BridgeTextBounded $repoQueuePath)
        }
        if (-not (Test-Path -LiteralPath $config["desktop_complete_path"] -PathType Leaf)) {
            Write-BridgeTextAtomic -Path $config["desktop_complete_path"] -Text (Read-BridgeTextBounded $repoCompletePath)
        }

        $gitQueue = Get-BridgeTaskMapFromFile -Path $repoQueuePath -Source "git_queue"
        $localQueue = Get-BridgeTaskMapFromFile -Path $config["desktop_queue_path"] -Source "desktop_queue" -Optional
        $gitComplete = Get-BridgeTaskMapFromFile -Path $repoCompletePath -Source "git_complete"
        $localComplete = Get-BridgeTaskMapFromFile -Path $config["desktop_complete_path"] -Source "desktop_complete" -Optional
        foreach ($errorItem in @(@($gitQueue.Errors) + @($localQueue.Errors) + @($gitComplete.Errors) + @($localComplete.Errors))) {
            Write-BridgeLog -Path $config["log_path"] -Level warning -Event "malformed_queue_entry" `
                -TaskId $errorItem.task_id -Status "rejected" -Detail $errorItem.reason
        }

        $tasks = Merge-BridgeTaskSources -GitTasks $gitQueue.Tasks -LocalTasks $localQueue.Tasks -State $state
        $trust = Read-BridgeTrust -Path $config["trust_path"]
        $pending = @{}
        $processed = 0

        foreach ($taskId in @($tasks.Keys | Sort-Object)) {
            if ($processed -ge [int]$config["maximum_tasks_per_cycle"]) { break }
            $task = $tasks[$taskId]
            if (@("PENDING", "IN_PROGRESS", "RETRY") -notcontains $task.Status) { continue }

            if ($task.Conflict) {
                $pending[$taskId] = @{ title = $task.Title; status = "conflict"; reason = $task.ConflictReason }
                Write-BridgeLog -Path $config["log_path"] -Level warning -Event "task_conflict" `
                    -TaskId $taskId -Status "pending_review" -Detail $task.ConflictReason
                continue
            }
            if ([string]::IsNullOrWhiteSpace($task.Executor) -or [string]::IsNullOrWhiteSpace($task.TaskType)) {
                continue
            }
            if ($task.Executor -eq "codex" -or $task.TaskType -eq "REASONING") {
                $pending[$taskId] = @{
                    title = $task.Title
                    status = "pending_pc_codex"
                    reason = "No locally approved non-interactive Codex dispatcher is installed; task was surfaced without UI automation."
                }
                continue
            }

            $safety = Test-BridgeTaskSafety -Task $task
            if (-not $safety.Safe) {
                $reason = ($safety.Reasons -join ",")
                $pending[$taskId] = @{ title = $task.Title; status = "rejected"; reason = $reason }
                Write-BridgeLog -Path $config["log_path"] -Level warning -Event "task_rejected" `
                    -TaskId $taskId -Status "unsafe_input" -Detail $reason
                continue
            }

            $trustDecision = Test-BridgeDispatcherTrust -Task $task -Trust $trust -InstallRoot $config["install_root"]
            if (-not $trustDecision.Trusted) {
                $pending[$taskId] = @{ title = $task.Title; status = "rejected"; reason = $trustDecision.Reason }
                Write-BridgeLog -Path $config["log_path"] -Level warning -Event "task_rejected" `
                    -TaskId $taskId -Status "not_allowlisted" -Detail $trustDecision.Reason
                continue
            }
            if (Test-BridgeCompletionRecord -Task $task -CompletionTasks $gitComplete.Tasks -DispatcherHash $trustDecision.Hash) {
                Write-BridgeLog -Path $config["log_path"] -Event "completed_task_skipped" `
                    -TaskId $taskId -Status "verified_complete"
                continue
            }
            if (Test-BridgeTaskVerifiedComplete -Task $task -State $state -DispatcherHash $trustDecision.Hash) {
                Write-BridgeLog -Path $config["log_path"] -Event "duplicate_task_skipped" `
                    -TaskId $taskId -Status "verified_complete"
                continue
            }
            if ($DryRun) {
                Write-BridgeLog -Path $config["log_path"] -Event "task_dry_run" `
                    -TaskId $taskId -Status "would_dispatch" -Detail $task.Executor
                continue
            }

            try {
                Write-BridgeLog -Path $config["log_path"] -Event "task_dispatch_started" `
                    -TaskId $taskId -Status "running" -Detail $task.Executor
                $dispatch = Get-BridgeResultCheckpoint -Task $task -State $state -DispatcherHash $trustDecision.Hash `
                    -ResultDirectory $config["result_directory"]
                $resumedResult = $null -ne $dispatch
                if (-not $resumedResult) {
                    $dispatch = Invoke-BridgeTrustedDispatcher -Task $task -TrustDecision $trustDecision `
                        -RepositoryRoot $config["repository_root"] -ResultDirectory $config["result_directory"]
                }
                $priorCount = 0
                if ($state["tasks"].ContainsKey($taskId) -and $state["tasks"][$taskId].ContainsKey("execution_count")) {
                    $priorCount = [int]$state["tasks"][$taskId]["execution_count"]
                }
                $state["tasks"][$taskId] = [ordered]@{
                    status = "RESULT_READY"
                    task_hash = $task.Hash
                    dispatcher_hash = $trustDecision.Hash
                    result_hash = $dispatch.Hash
                    result_path = $dispatch.ResultPath
                    execution_count = if ($resumedResult) { $priorCount } else { $priorCount + 1 }
                    task_title = Protect-BridgeText $task.Title 180
                    task_type = $task.TaskType
                    executor = $task.Executor
                    checkpoint = "Trusted read-only dispatcher completed; queue publication pending."
                    checkpoint_at = [DateTimeOffset]::UtcNow.ToString("o")
                }
                Save-BridgeState -Path $config["state_path"] -State $state

                Complete-BridgeTaskDocuments -Task $task -Result $dispatch.Result -ResultHash $dispatch.Hash `
                    -DispatcherHash $trustDecision.Hash -Config $config
                Publish-BridgeTaskCompletion -Task $task -Config $config | Out-Null

                $state["tasks"][$taskId]["status"] = "COMPLETE"
                $state["tasks"][$taskId]["completed_at"] = [DateTimeOffset]::UtcNow.ToString("o")
                $state["tasks"][$taskId]["checkpoint"] = "Bounded result committed and pushed through the configured remote."
                $state["last_success_at"] = [DateTimeOffset]::UtcNow.ToString("o")
                Save-BridgeState -Path $config["state_path"] -State $state
                Write-BridgeLog -Path $config["log_path"] -Event "task_completed" `
                    -TaskId $taskId -Status "verified" -Detail "Bounded result published."
                $processed++
            }
            catch {
                $message = Protect-BridgeText $_.Exception.Message 240
                if (-not $state["tasks"].ContainsKey($taskId)) {
                    $state["tasks"][$taskId] = @{}
                }
                $hasSavedResult = $state["tasks"][$taskId].ContainsKey("result_path") -and `
                    -not [string]::IsNullOrWhiteSpace([string]$state["tasks"][$taskId]["result_path"])
                $state["tasks"][$taskId]["status"] = if ($hasSavedResult) { "RESULT_READY" } else { "RETRY" }
                $state["tasks"][$taskId]["task_hash"] = $task.Hash
                $state["tasks"][$taskId]["checkpoint"] = $message
                $state["tasks"][$taskId]["checkpoint_at"] = [DateTimeOffset]::UtcNow.ToString("o")
                Save-BridgeState -Path $config["state_path"] -State $state
                if (-not $hasSavedResult) {
                    try {
                        Set-BridgeTaskCheckpointDocuments -Task $task -Status RETRY -Checkpoint $message -Config $config
                        Publish-BridgeTaskCompletion -Task $task -Config $config | Out-Null
                    }
                    catch {
                        Write-BridgeLog -Path $config["log_path"] -Level warning -Event "checkpoint_publish_failed" `
                            -TaskId $taskId -Status "retry" -Detail $_.Exception.Message
                    }
                }
                Write-BridgeLog -Path $config["log_path"] -Level error -Event "task_failed" `
                    -TaskId $taskId -Status "retry" -Detail $message
            }
        }

        Write-BridgePendingNotification -Path $config["pending_notification_path"] -PendingTasks $pending
        Write-BridgeHealth -Config $config -Status "healthy" -Detail "Git queue checked with locally pinned dispatchers." -PendingCount $pending.Count
    }
    finally {
        if ($null -ne $lock) { Exit-BridgeLock -Lock $lock }
    }
}

do {
    try {
        Invoke-BridgeCycle
    }
    catch {
        try {
            $config = Read-BridgeRuntimeConfig
            Write-BridgeLog -Path $config["log_path"] -Level error -Event "watcher_cycle_failed" `
                -Status "degraded" -Detail $_.Exception.Message
            Write-BridgeHealth -Config $config -Status "degraded" -Detail $_.Exception.Message
        }
        catch { }
        if ($Mode -eq "Once") { throw }
    }
    if ($Mode -eq "Watch") {
        $config = Read-BridgeRuntimeConfig
        Start-Sleep -Seconds ([int]$config["poll_seconds"])
    }
} while ($Mode -eq "Watch")
