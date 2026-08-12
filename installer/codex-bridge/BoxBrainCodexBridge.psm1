Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:AllowedStatuses = @(
    "PENDING",
    "IN_PROGRESS",
    "RETRY",
    "BLOCKED",
    "DEFERRED_USAGE",
    "COMPLETE",
    "SUPERSEDED",
    "REJECTED"
)

function Invoke-BridgeGitNative {
    param(
        [Parameter(Mandatory)][string]$GitPath,
        [Parameter(Mandatory)][string[]]$Arguments
    )

    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = @(& $GitPath @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $previousPreference }
    return [pscustomobject]@{ ExitCode = $exitCode; Output = $output }
}

function ConvertTo-BridgeHashtable {
    param([Parameter(Mandatory)]$InputObject)

    if ($InputObject -is [Collections.IDictionary]) {
        $result = @{}
        foreach ($key in $InputObject.Keys) {
            $result[[string]$key] = ConvertTo-BridgeHashtable $InputObject[$key]
        }
        return $result
    }
    if ($InputObject -is [Management.Automation.PSCustomObject]) {
        $result = @{}
        foreach ($property in $InputObject.PSObject.Properties) {
            $result[$property.Name] = ConvertTo-BridgeHashtable $property.Value
        }
        return $result
    }
    if ($InputObject -is [Collections.IEnumerable] -and $InputObject -isnot [string]) {
        return @($InputObject | ForEach-Object { ConvertTo-BridgeHashtable $_ })
    }
    return $InputObject
}

function Get-BridgeSha256String {
    param([Parameter(Mandatory)][string]$Value)

    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($Value)
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Get-BridgeFileSha256 {
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Trusted file is missing."
    }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Protect-BridgeText {
    param(
        [AllowEmptyString()][string]$Value,
        [ValidateRange(32, 2048)][int]$MaximumLength = 512
    )

    if ($null -eq $Value) { return "" }
    $safe = $Value
    $safe = [regex]::Replace(
        $safe,
        "(?i)(password|passphrase|token|secret|private[_ -]?key|cookie|authorization)\s*[:=]\s*[^\s,;]+",
        '$1=[REDACTED]'
    )
    $safe = [regex]::Replace($safe, "(?i)gh[pousr]_[A-Za-z0-9_]{12,}", "[REDACTED_GITHUB_TOKEN]")
    $safe = [regex]::Replace($safe, "(?i)sk-[A-Za-z0-9_-]{12,}", "[REDACTED_API_KEY]")
    $safe = [regex]::Replace(
        $safe,
        "(?s)-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
        "[REDACTED_PRIVATE_KEY]"
    )
    $safe = ($safe -replace "[\r\n\t]+", " " -replace "\s{2,}", " ").Trim()
    if ($safe.Length -gt $MaximumLength) {
        $safe = $safe.Substring(0, $MaximumLength) + "..."
    }
    return $safe
}

function Write-BridgeJsonFile {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)]$Value
    )

    $directory = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    $temporary = "$Path.tmp-$PID-$([Guid]::NewGuid().ToString('N'))"
    $json = $Value | ConvertTo-Json -Depth 12
    [IO.File]::WriteAllText($temporary, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Write-BridgeLog {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Event,
        [ValidateSet("debug", "info", "warning", "error")][string]$Level = "info",
        [string]$TaskId,
        [string]$Status,
        [string]$Detail
    )

    $directory = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    $record = [ordered]@{
        schema_version = 1
        timestamp = [DateTimeOffset]::UtcNow.ToString("o")
        level = $Level
        event = Protect-BridgeText $Event 96
    }
    if ($TaskId) { $record.task_id = Protect-BridgeText $TaskId 32 }
    if ($Status) { $record.status = Protect-BridgeText $Status 48 }
    if ($Detail) { $record.detail = Protect-BridgeText $Detail 512 }
    $line = $record | ConvertTo-Json -Compress -Depth 4
    [IO.File]::AppendAllText($Path, $line + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

function Read-BridgeTextBounded {
    param(
        [Parameter(Mandatory)][string]$Path,
        [ValidateRange(1024, 1048576)][int]$MaximumBytes = 131072
    )

    $item = Get-Item -LiteralPath $Path -ErrorAction Stop
    if ($item.Length -gt $MaximumBytes) {
        throw "Queue source exceeds the configured byte limit."
    }
    return [IO.File]::ReadAllText($item.FullName)
}

function ConvertFrom-BridgeQueueText {
    param(
        [AllowEmptyString()][string]$Text,
        [string]$Source = "unknown",
        [ValidateRange(1024, 131072)][int]$MaximumTaskBytes = 16384
    )

    $tasks = @{}
    $errors = [Collections.Generic.List[object]]::new()
    $lines = @($Text -split "\r?\n")
    $index = 0
    while ($index -lt $lines.Count) {
        $start = [regex]::Match($lines[$index], '^\+?\[TASK\s+([^\]]+)\]\s*$')
        if (-not $start.Success) {
            $index++
            continue
        }

        $rawId = $start.Groups[1].Value.Trim().ToUpperInvariant()
        $blockLines = [Collections.Generic.List[string]]::new()
        $blockLines.Add($lines[$index])
        $endFound = $false
        $cursor = $index + 1
        while ($cursor -lt $lines.Count) {
            if ($lines[$cursor] -match '^\+?\[TASK\s+') { break }
            $blockLines.Add($lines[$cursor])
            if ($lines[$cursor] -match '^END TASK\s*$') {
                $endFound = $true
                $cursor++
                break
            }
            $cursor++
        }
        $index = $cursor
        $rawBlock = ($blockLines -join "`n").Trim()

        if ($rawId -notmatch '^BB-\d{3}$') {
            $errors.Add([pscustomobject]@{ source = $Source; task_id = $rawId; reason = "invalid_task_id" })
            continue
        }
        if (-not $endFound) {
            $errors.Add([pscustomobject]@{ source = $Source; task_id = $rawId; reason = "missing_end_task" })
            continue
        }
        if ([Text.Encoding]::UTF8.GetByteCount($rawBlock) -gt $MaximumTaskBytes) {
            $errors.Add([pscustomobject]@{ source = $Source; task_id = $rawId; reason = "task_too_large" })
            continue
        }
        if ($tasks.ContainsKey($rawId)) {
            $errors.Add([pscustomobject]@{ source = $Source; task_id = $rawId; reason = "duplicate_task_id" })
            $tasks.Remove($rawId)
            continue
        }

        $fields = @{}
        foreach ($line in $blockLines) {
            $field = [regex]::Match($line, '^([A-Z][A-Z0-9_]*)\s*:\s*(.*)$')
            if ($field.Success) {
                $fields[$field.Groups[1].Value] = $field.Groups[2].Value.Trim()
            }
        }
        $status = if ($fields.ContainsKey("STATUS")) { $fields["STATUS"].ToUpperInvariant() } else { "" }
        $title = if ($fields.ContainsKey("TITLE")) { $fields["TITLE"] } else { "" }
        if (-not $status -or $script:AllowedStatuses -notcontains $status) {
            $errors.Add([pscustomobject]@{ source = $Source; task_id = $rawId; reason = "invalid_status" })
            continue
        }
        if ([string]::IsNullOrWhiteSpace($title) -or $title.Length -gt 200) {
            $errors.Add([pscustomobject]@{ source = $Source; task_id = $rawId; reason = "invalid_title" })
            continue
        }

        $checkpointAt = $null
        if ($fields.ContainsKey("CHECKPOINT_AT")) {
            $parsedDate = [DateTimeOffset]::MinValue
            if ([DateTimeOffset]::TryParse($fields["CHECKPOINT_AT"], [ref]$parsedDate)) {
                $checkpointAt = $parsedDate
            }
        }
        $tasks[$rawId] = [pscustomobject]@{
            Id = $rawId
            Status = $status
            Title = $title
            TaskType = if ($fields.ContainsKey("TASK_TYPE")) { $fields["TASK_TYPE"].ToUpperInvariant() } else { "" }
            Executor = if ($fields.ContainsKey("EXECUTOR")) { $fields["EXECUTOR"].ToLowerInvariant() } else { "" }
            CheckpointAt = $checkpointAt
            Checkpoint = if ($fields.ContainsKey("CHECKPOINT")) { $fields["CHECKPOINT"] } else { "" }
            Fields = $fields
            Raw = $rawBlock
            Hash = Get-BridgeSha256String (($rawBlock -replace "\r\n", "`n").Trim())
            Source = $Source
            Conflict = $false
            ConflictReason = ""
        }
    }

    return [pscustomobject]@{
        Tasks = $tasks
        Errors = @($errors)
    }
}

function Test-BridgeTaskSafety {
    param([Parameter(Mandatory)]$Task)

    $reasons = [Collections.Generic.List[string]]::new()
    foreach ($forbiddenField in @("COMMAND", "SHELL", "SCRIPT", "ARGUMENTS", "ARGS")) {
        if ($Task.Fields.ContainsKey($forbiddenField)) {
            $reasons.Add("arbitrary_command_field")
            break
        }
    }
    if ($Task.Raw -match '(?i)(\.\.[\\/]|[A-Z]:\\|/(etc|root|boot|dev|proc|sys)/|~[\\/])') {
        $reasons.Add("path_traversal_or_external_path")
    }
    if ($Task.Raw -match '(?i)\b(password|passphrase|private key|ssh key|session token|access token|api key|cookie|credential export)\b') {
        $reasons.Add("credential_request")
    }
    if ($Task.Raw -match '(?i)\b(delete|erase|format|wipe|destroy|rm\s+-rf|remove-item|diskpart|shutdown|reboot)\b') {
        $reasons.Add("destructive_request")
    }
    return [pscustomobject]@{
        Safe = $reasons.Count -eq 0
        Reasons = @($reasons | Select-Object -Unique)
    }
}

function New-BridgeState {
    return [ordered]@{
        schema_version = 1
        fetch_failures = 0
        next_retry_at = $null
        last_fetch_at = $null
        last_success_at = $null
        last_error = $null
        tasks = @{}
    }
}

function Read-BridgeState {
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return New-BridgeState
    }
    try {
        $raw = Read-BridgeTextBounded -Path $Path -MaximumBytes 262144
        $state = ConvertTo-BridgeHashtable ($raw | ConvertFrom-Json -ErrorAction Stop)
        if (-not $state.ContainsKey("tasks") -or $state["tasks"] -isnot [Collections.IDictionary]) {
            throw "State tasks are invalid."
        }
        return $state
    }
    catch {
        $backup = "$Path.corrupt-$([DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssZ'))"
        Move-Item -LiteralPath $Path -Destination $backup
        return New-BridgeState
    }
}

function Save-BridgeState {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][Collections.IDictionary]$State
    )
    Write-BridgeJsonFile -Path $Path -Value $State
}

function Test-BridgeTaskVerifiedComplete {
    param(
        [Parameter(Mandatory)]$Task,
        [Parameter(Mandatory)][Collections.IDictionary]$State,
        [string]$DispatcherHash
    )

    if (-not $State["tasks"].ContainsKey($Task.Id)) { return $false }
    $record = $State["tasks"][$Task.Id]
    if ($record["status"] -ne "COMPLETE") { return $false }
    if ($record["task_hash"] -ne $Task.Hash) { return $false }
    if ([string]::IsNullOrWhiteSpace([string]$record["result_hash"])) { return $false }
    if ($DispatcherHash -and $record["dispatcher_hash"] -ne $DispatcherHash) { return $false }
    return $true
}

function Test-BridgeCompletionRecord {
    param(
        [Parameter(Mandatory)]$Task,
        [Parameter(Mandatory)][Collections.IDictionary]$CompletionTasks,
        [Parameter(Mandatory)][string]$DispatcherHash
    )

    if (-not $CompletionTasks.ContainsKey($Task.Id)) { return $false }
    $completion = $CompletionTasks[$Task.Id]
    if ($completion.Status -ne "COMPLETE") { return $false }
    if (-not $completion.Fields.ContainsKey("VERIFIED") -or $completion.Fields["VERIFIED"] -ne "true") { return $false }
    if (-not $completion.Fields.ContainsKey("TASK_HASH") -or $completion.Fields["TASK_HASH"] -ne $Task.Hash) { return $false }
    if (-not $completion.Fields.ContainsKey("RESULT_HASH") -or $completion.Fields["RESULT_HASH"] -notmatch '^[a-f0-9]{64}$') { return $false }
    if (-not $completion.Fields.ContainsKey("DISPATCHER_HASH") -or $completion.Fields["DISPATCHER_HASH"] -ne $DispatcherHash) { return $false }
    return $true
}

function Merge-BridgeTaskSources {
    param(
        [Parameter(Mandatory)][Collections.IDictionary]$GitTasks,
        [Parameter(Mandatory)][Collections.IDictionary]$LocalTasks,
        [Parameter(Mandatory)][Collections.IDictionary]$State
    )

    $merged = @{}
    $ids = @(@($GitTasks.Keys) + @($LocalTasks.Keys) | Sort-Object -Unique)
    foreach ($id in $ids) {
        $gitTask = if ($GitTasks.ContainsKey($id)) { $GitTasks[$id] } else { $null }
        $localTask = if ($LocalTasks.ContainsKey($id)) { $LocalTasks[$id] } else { $null }
        if ($null -eq $gitTask) { $merged[$id] = $localTask; continue }
        if ($null -eq $localTask) { $merged[$id] = $gitTask; continue }
        if ($gitTask.Hash -eq $localTask.Hash) { $merged[$id] = $gitTask; continue }

        $gitComplete = $gitTask.Status -eq "COMPLETE"
        $localComplete = $localTask.Status -eq "COMPLETE"
        if ($gitComplete -xor $localComplete) {
            $candidate = if ($gitComplete) { $gitTask } else { $localTask }
            if (Test-BridgeTaskVerifiedComplete -Task $candidate -State $State) {
                $merged[$id] = $candidate
                continue
            }
            $candidate = if ($gitComplete) { $localTask } else { $gitTask }
            $candidate.Conflict = $true
            $candidate.ConflictReason = "unverified_complete_conflict"
            $merged[$id] = $candidate
            continue
        }

        if ($gitTask.CheckpointAt -and $localTask.CheckpointAt) {
            if ($gitTask.CheckpointAt -gt $localTask.CheckpointAt) { $merged[$id] = $gitTask; continue }
            if ($localTask.CheckpointAt -gt $gitTask.CheckpointAt) { $merged[$id] = $localTask; continue }
        }
        $gitTask.Conflict = $true
        $gitTask.ConflictReason = "material_git_local_conflict"
        $merged[$id] = $gitTask
    }
    return $merged
}

function Enter-BridgeLock {
    param(
        [Parameter(Mandatory)][string]$Path,
        [ValidateRange(30, 86400)][int]$StaleAfterSeconds = 900
    )

    $directory = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    $now = [DateTimeOffset]::UtcNow
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        $stale = $true
        try {
            $data = Read-BridgeTextBounded -Path $Path -MaximumBytes 4096 | ConvertFrom-Json
            $started = [DateTimeOffset]::Parse([string]$data.started_at)
            $age = ($now - $started).TotalSeconds
            $process = Get-Process -Id ([int]$data.pid) -ErrorAction SilentlyContinue
            $stale = ($age -gt $StaleAfterSeconds) -or ($null -eq $process)
        }
        catch { $stale = $true }
        if (-not $stale) { throw "BRIDGE_LOCK_HELD" }
        $stalePath = "$Path.stale-$($now.ToString('yyyyMMddTHHmmssZ'))"
        Move-Item -LiteralPath $Path -Destination $stalePath -Force
    }

    $payload = [ordered]@{ pid = $PID; started_at = $now.ToString("o") } | ConvertTo-Json -Compress
    try {
        $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $writer = [IO.StreamWriter]::new($stream, [Text.UTF8Encoding]::new($false))
        try { $writer.Write($payload) } finally { $writer.Dispose() }
    }
    catch { throw "BRIDGE_LOCK_HELD" }
    return [pscustomobject]@{ Path = $Path; Pid = $PID }
}

function Exit-BridgeLock {
    param([Parameter(Mandatory)]$Lock)

    if (-not (Test-Path -LiteralPath $Lock.Path -PathType Leaf)) { return }
    try {
        $data = Read-BridgeTextBounded -Path $Lock.Path -MaximumBytes 4096 | ConvertFrom-Json
        if ([int]$data.pid -eq [int]$Lock.Pid) {
            Remove-Item -LiteralPath $Lock.Path -Force
        }
    }
    catch { }
}

function Test-BridgeRemoteConfiguration {
    param(
        [Parameter(Mandatory)][Collections.IDictionary]$Config,
        [string]$GitPath = "git.exe"
    )

    if ($Config["remote_name"] -notmatch '^[A-Za-z0-9._-]+$') { throw "Invalid configured remote name." }
    if ($Config["remote_ref"] -notmatch '^refs/heads/[A-Za-z0-9._/-]+$' -or $Config["remote_ref"] -match '\.\.|\\') {
        throw "Invalid configured remote ref."
    }
    $remote = Invoke-BridgeGitNative -GitPath $GitPath -Arguments @("-C", $Config["repository_root"], "remote", "get-url", $Config["remote_name"])
    $actual = $remote.Output | Select-Object -First 1
    if ($remote.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($actual)) { throw "Configured Git remote is unavailable." }
    if ($actual.Trim() -ne [string]$Config["remote_url"]) { throw "Configured Git remote URL does not match the locally approved URL." }
    if ($actual -notmatch '(?i)github\.com[:/]FormatX66/BoxBrain(?:\.git)?$') {
        throw "Only the configured FormatX66/BoxBrain remote is permitted."
    }
    return $true
}

function Invoke-BridgeFetch {
    param(
        [Parameter(Mandatory)][Collections.IDictionary]$Config,
        [string]$GitPath = "git.exe",
        [switch]$FastForward
    )

    Test-BridgeRemoteConfiguration -Config $Config -GitPath $GitPath | Out-Null
    $tracking = [string]$Config["remote_tracking_ref"]
    $fetch = Invoke-BridgeGitNative -GitPath $GitPath -Arguments @(
        "-C", $Config["repository_root"], "fetch", "--no-tags", "--prune", $Config["remote_name"],
        "+$($Config['remote_ref']):$tracking"
    )
    if ($fetch.ExitCode -ne 0) { throw "Git fetch failed." }
    if ($FastForward) {
        $status = Invoke-BridgeGitNative -GitPath $GitPath -Arguments @("-C", $Config["repository_root"], "status", "--porcelain", "--untracked-files=no")
        if ($status.ExitCode -ne 0 -or $status.Output.Count -gt 0) { throw "Bridge repository contains unrelated local changes." }
        $merge = Invoke-BridgeGitNative -GitPath $GitPath -Arguments @("-C", $Config["repository_root"], "merge", "--ff-only", $tracking)
        if ($merge.ExitCode -ne 0) { throw "Bridge branch could not fast-forward cleanly." }
    }
    return $true
}

function Get-BridgeBackoffSeconds {
    param(
        [ValidateRange(1, 30)][int]$FailureCount,
        [ValidateRange(1, 3600)][int]$BaseSeconds = 15,
        [ValidateRange(1, 86400)][int]$MaximumSeconds = 900
    )
    $value = [Math]::Min($MaximumSeconds, $BaseSeconds * [Math]::Pow(2, $FailureCount - 1))
    return [int]$value
}

function Read-BridgeTrust {
    param([Parameter(Mandatory)][string]$Path)

    $raw = Read-BridgeTextBounded -Path $Path -MaximumBytes 65536
    $trust = ConvertTo-BridgeHashtable ($raw | ConvertFrom-Json -ErrorAction Stop)
    if ($trust["schema_version"] -ne 1 -or $trust["dispatchers"] -isnot [Collections.IDictionary]) {
        throw "Local dispatcher trust registry is invalid."
    }
    return $trust
}

function Test-BridgeDispatcherTrust {
    param(
        [Parameter(Mandatory)]$Task,
        [Parameter(Mandatory)][Collections.IDictionary]$Trust,
        [Parameter(Mandatory)][string]$InstallRoot
    )

    if ([string]::IsNullOrWhiteSpace($Task.Executor) -or -not $Trust["dispatchers"].ContainsKey($Task.Executor)) {
        return [pscustomobject]@{ Trusted = $false; Reason = "unknown_executor"; Entry = $null; ScriptPath = $null; Hash = $null }
    }
    $entry = $Trust["dispatchers"][$Task.Executor]
    if (@($entry["task_types"]) -notcontains $Task.TaskType) {
        return [pscustomobject]@{ Trusted = $false; Reason = "task_type_not_allowlisted"; Entry = $entry; ScriptPath = $null; Hash = $null }
    }
    if ($entry["impact"] -ne "read_only") {
        return [pscustomobject]@{ Trusted = $false; Reason = "dispatcher_impact_not_permitted"; Entry = $entry; ScriptPath = $null; Hash = $null }
    }
    $root = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\') + '\'
    $scriptPath = [IO.Path]::GetFullPath((Join-Path $InstallRoot $entry["installed_script"]))
    if (-not $scriptPath.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
        return [pscustomobject]@{ Trusted = $false; Reason = "dispatcher_path_escape"; Entry = $entry; ScriptPath = $scriptPath; Hash = $null }
    }
    $actualHash = Get-BridgeFileSha256 -Path $scriptPath
    if ($actualHash -ne [string]$entry["sha256"]) {
        return [pscustomobject]@{ Trusted = $false; Reason = "dispatcher_hash_mismatch"; Entry = $entry; ScriptPath = $scriptPath; Hash = $actualHash }
    }
    return [pscustomobject]@{ Trusted = $true; Reason = "trusted"; Entry = $entry; ScriptPath = $scriptPath; Hash = $actualHash }
}

function Invoke-BridgeTrustedDispatcher {
    param(
        [Parameter(Mandatory)]$Task,
        [Parameter(Mandatory)]$TrustDecision,
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [Parameter(Mandatory)][string]$ResultDirectory
    )

    if (-not $TrustDecision.Trusted) { throw "Dispatcher is not locally trusted." }
    if ($Task.Id -notmatch '^BB-\d{3}$') { throw "Task ID is not safe for dispatch." }
    if (-not (Test-Path -LiteralPath $ResultDirectory -PathType Container)) {
        New-Item -ItemType Directory -Path $ResultDirectory -Force | Out-Null
    }
    $resultPath = Join-Path $ResultDirectory "$($Task.Id)-$([Guid]::NewGuid().ToString('N')).json"
    $powerShell = (Get-Command powershell.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    & $powerShell -NoProfile -ExecutionPolicy Bypass -File $TrustDecision.ScriptPath `
        -TaskId $Task.Id -RepositoryRoot $RepositoryRoot -OutputPath $resultPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Trusted dispatcher failed." }
    $resultRaw = Read-BridgeTextBounded -Path $resultPath -MaximumBytes 32768
    $result = ConvertTo-BridgeHashtable ($resultRaw | ConvertFrom-Json -ErrorAction Stop)
    if ($result["schema_version"] -ne 1 -or $result["task_id"] -ne $Task.Id -or $result["verified"] -ne $true) {
        throw "Trusted dispatcher returned an invalid result."
    }
    return [pscustomobject]@{
        Result = $result
        ResultPath = $resultPath
        Hash = Get-BridgeSha256String $resultRaw
    }
}

function Get-BridgeResultCheckpoint {
    param(
        [Parameter(Mandatory)]$Task,
        [Parameter(Mandatory)][Collections.IDictionary]$State,
        [Parameter(Mandatory)][string]$DispatcherHash,
        [Parameter(Mandatory)][string]$ResultDirectory
    )

    if (-not $State["tasks"].ContainsKey($Task.Id)) { return $null }
    $record = $State["tasks"][$Task.Id]
    if ($record["status"] -ne "RESULT_READY") { return $null }
    if ($record["task_hash"] -ne $Task.Hash -or $record["dispatcher_hash"] -ne $DispatcherHash) { return $null }
    $resultRoot = [IO.Path]::GetFullPath($ResultDirectory).TrimEnd('\') + '\'
    $resultPath = [IO.Path]::GetFullPath([string]$record["result_path"])
    if (-not $resultPath.StartsWith($resultRoot, [StringComparison]::OrdinalIgnoreCase)) { return $null }
    if (-not (Test-Path -LiteralPath $resultPath -PathType Leaf)) { return $null }
    $raw = Read-BridgeTextBounded -Path $resultPath -MaximumBytes 32768
    if ((Get-BridgeSha256String $raw) -ne [string]$record["result_hash"]) { return $null }
    $result = ConvertTo-BridgeHashtable ($raw | ConvertFrom-Json -ErrorAction Stop)
    if ($result["schema_version"] -ne 1 -or $result["task_id"] -ne $Task.Id -or $result["verified"] -ne $true) { return $null }
    return [pscustomobject]@{ Result = $result; ResultPath = $resultPath; Hash = [string]$record["result_hash"] }
}

function Remove-BridgeTaskBlock {
    param(
        [AllowEmptyString()][string]$Text,
        [Parameter(Mandatory)][string]$TaskId
    )
    if ($TaskId -notmatch '^BB-\d{3}$') { throw "Invalid task ID for queue update." }
    $escaped = [regex]::Escape($TaskId)
    $pattern = "(?ms)^\+?\[TASK\s+$escaped\]\s*\r?\n.*?^END TASK\s*\r?\n?"
    return ([regex]::Replace($Text, $pattern, "")).TrimEnd() + [Environment]::NewLine
}

function Add-BridgeCompletionBlock {
    param(
        [AllowEmptyString()][string]$Text,
        [Parameter(Mandatory)]$Task,
        [Parameter(Mandatory)][Collections.IDictionary]$Result,
        [Parameter(Mandatory)][string]$ResultHash,
        [Parameter(Mandatory)][string]$DispatcherHash
    )
    $existing = ConvertFrom-BridgeQueueText -Text $Text -Source "complete"
    if ($existing.Tasks.ContainsKey($Task.Id)) { return $Text }
    $summary = Protect-BridgeText ([string]$Result["summary"]) 300
    $completedAt = [DateTimeOffset]::UtcNow.ToString("o")
    $block = @"
[TASK $($Task.Id)]
STATUS: COMPLETE
TITLE: $(Protect-BridgeText $Task.Title 180)
TASK_TYPE: $($Task.TaskType)
EXECUTOR: $($Task.Executor)
COMPLETED_AT: $completedAt
VERIFIED: true
RESULT: $summary
TASK_HASH: $($Task.Hash)
RESULT_HASH: $ResultHash
DISPATCHER_HASH: $DispatcherHash
END TASK
"@
    return $Text.TrimEnd() + [Environment]::NewLine + [Environment]::NewLine + $block.Trim() + [Environment]::NewLine
}

function Set-BridgeTaskCheckpointText {
    param(
        [AllowEmptyString()][string]$Text,
        [Parameter(Mandatory)][string]$TaskId,
        [ValidateSet("IN_PROGRESS", "RETRY", "BLOCKED")][string]$Status,
        [Parameter(Mandatory)][string]$Checkpoint
    )

    if ($TaskId -notmatch '^BB-\d{3}$') { throw "Invalid task ID for checkpoint update." }
    $escaped = [regex]::Escape($TaskId)
    $pattern = "(?ms)^\+?\[TASK\s+$escaped\]\s*\r?\n.*?^END TASK\s*$"
    $match = [regex]::Match($Text, $pattern)
    if (-not $match.Success) { return $Text }
    $block = $match.Value
    $safeCheckpoint = Protect-BridgeText $Checkpoint 300
    $timestamp = [DateTimeOffset]::UtcNow.ToString("o")
    if ($block -match '(?m)^STATUS\s*:') { $block = [regex]::Replace($block, '(?m)^STATUS\s*:.*$', "STATUS: $Status", 1) }
    else { $block = $block -replace '(?m)^(TITLE\s*:.*)$', "`$1`r`nSTATUS: $Status" }
    if ($block -match '(?m)^CHECKPOINT\s*:') { $block = [regex]::Replace($block, '(?m)^CHECKPOINT\s*:.*$', "CHECKPOINT: $safeCheckpoint", 1) }
    else { $block = $block -replace '(?m)^END TASK\s*$', "CHECKPOINT: $safeCheckpoint`r`nEND TASK" }
    if ($block -match '(?m)^CHECKPOINT_AT\s*:') { $block = [regex]::Replace($block, '(?m)^CHECKPOINT_AT\s*:.*$', "CHECKPOINT_AT: $timestamp", 1) }
    else { $block = $block -replace '(?m)^END TASK\s*$', "CHECKPOINT_AT: $timestamp`r`nEND TASK" }
    return $Text.Substring(0, $match.Index) + $block + $Text.Substring($match.Index + $match.Length)
}

function Set-BridgeTaskCheckpointDocuments {
    param(
        [Parameter(Mandatory)]$Task,
        [ValidateSet("IN_PROGRESS", "RETRY", "BLOCKED")][string]$Status,
        [Parameter(Mandatory)][string]$Checkpoint,
        [Parameter(Mandatory)][Collections.IDictionary]$Config
    )

    $backupDirectory = Join-Path $Config["install_root"] "backups"
    $repoQueuePath = Join-Path $Config["repository_root"] $Config["queue_path"]
    $repoText = Read-BridgeTextBounded -Path $repoQueuePath
    Write-BridgeTextAtomic -Path $repoQueuePath -Text (Set-BridgeTaskCheckpointText $repoText $Task.Id $Status $Checkpoint) -BackupDirectory $backupDirectory
    $desktopPath = [string]$Config["desktop_queue_path"]
    if (-not [string]::IsNullOrWhiteSpace($desktopPath)) {
        $desktopText = if (Test-Path -LiteralPath $desktopPath -PathType Leaf) { Read-BridgeTextBounded -Path $desktopPath } else { $repoText }
        Write-BridgeTextAtomic -Path $desktopPath -Text (Set-BridgeTaskCheckpointText $desktopText $Task.Id $Status $Checkpoint) -BackupDirectory $backupDirectory
    }
}

function Write-BridgeTextAtomic {
    param(
        [Parameter(Mandatory)][string]$Path,
        [AllowEmptyString()][string]$Text,
        [string]$BackupDirectory
    )
    $directory = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    if ($BackupDirectory -and (Test-Path -LiteralPath $Path -PathType Leaf)) {
        if (-not (Test-Path -LiteralPath $BackupDirectory -PathType Container)) {
            New-Item -ItemType Directory -Path $BackupDirectory -Force | Out-Null
        }
        $backupName = "$(Split-Path -Leaf $Path).$([DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')).bak"
        Copy-Item -LiteralPath $Path -Destination (Join-Path $BackupDirectory $backupName)
    }
    $temporary = "$Path.tmp-$PID-$([Guid]::NewGuid().ToString('N'))"
    [IO.File]::WriteAllText($temporary, $Text, [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Complete-BridgeTaskDocuments {
    param(
        [Parameter(Mandatory)]$Task,
        [Parameter(Mandatory)][Collections.IDictionary]$Result,
        [Parameter(Mandatory)][string]$ResultHash,
        [Parameter(Mandatory)][string]$DispatcherHash,
        [Parameter(Mandatory)][Collections.IDictionary]$Config
    )

    $queuePath = Join-Path $Config["repository_root"] $Config["queue_path"]
    $completePath = Join-Path $Config["repository_root"] $Config["complete_path"]
    $backupDirectory = Join-Path $Config["install_root"] "backups"
    $queueText = Read-BridgeTextBounded -Path $queuePath
    $completeText = Read-BridgeTextBounded -Path $completePath
    Write-BridgeTextAtomic -Path $queuePath -Text (Remove-BridgeTaskBlock $queueText $Task.Id) -BackupDirectory $backupDirectory
    Write-BridgeTextAtomic -Path $completePath -Text (Add-BridgeCompletionBlock $completeText $Task $Result $ResultHash $DispatcherHash) -BackupDirectory $backupDirectory

    $desktopQueuePath = [string]$Config["desktop_queue_path"]
    if (-not [string]::IsNullOrWhiteSpace($desktopQueuePath)) {
        $desktopQueueText = if (Test-Path -LiteralPath $desktopQueuePath -PathType Leaf) {
            Read-BridgeTextBounded -Path $desktopQueuePath
        }
        else { $queueText }
        Write-BridgeTextAtomic -Path $desktopQueuePath -Text (Remove-BridgeTaskBlock $desktopQueueText $Task.Id) -BackupDirectory $backupDirectory
    }

    $desktopCompletePath = [string]$Config["desktop_complete_path"]
    if (-not [string]::IsNullOrWhiteSpace($desktopCompletePath)) {
        $desktopCompleteText = if (Test-Path -LiteralPath $desktopCompletePath -PathType Leaf) {
            Read-BridgeTextBounded -Path $desktopCompletePath
        }
        else { $completeText }
        Write-BridgeTextAtomic -Path $desktopCompletePath -Text (Add-BridgeCompletionBlock $desktopCompleteText $Task $Result $ResultHash $DispatcherHash) -BackupDirectory $backupDirectory
    }
}

function Publish-BridgeTaskCompletion {
    param(
        [Parameter(Mandatory)]$Task,
        [Parameter(Mandatory)][Collections.IDictionary]$Config,
        [string]$GitPath = "git.exe"
    )
    $repo = [string]$Config["repository_root"]
    $allowed = @(
        ([string]$Config["queue_path"] -replace '\\', '/'),
        ([string]$Config["complete_path"] -replace '\\', '/')
    )
    $status = Invoke-BridgeGitNative -GitPath $GitPath -Arguments @("-C", $repo, "status", "--porcelain")
    if ($status.ExitCode -ne 0) { throw "Could not inspect bounded queue changes." }
    $changed = @($status.Output | ForEach-Object { ([string]$_).Substring(3) -replace '\\', '/' })
    foreach ($path in $changed) {
        if ($allowed -notcontains $path) { throw "Bridge repository contains an unrelated change." }
    }
    if ($changed.Count -gt 0) {
        $add = Invoke-BridgeGitNative -GitPath $GitPath -Arguments @("-C", $repo, "add", "--", $Config["queue_path"], $Config["complete_path"])
        if ($add.ExitCode -ne 0) { throw "Could not stage bounded queue records." }
        $commit = Invoke-BridgeGitNative -GitPath $GitPath -Arguments @("-C", $repo, "commit", "-m", "Record $($Task.Id) bridge checkpoint")
        if ($commit.ExitCode -ne 0) { throw "Could not commit bounded queue record." }
    }
    $push = Invoke-BridgeGitNative -GitPath $GitPath -Arguments @("-C", $repo, "push", $Config["remote_name"], "HEAD:$($Config['remote_ref'])")
    if ($push.ExitCode -ne 0) { throw "Could not push bounded queue result." }
    return $true
}

function Write-BridgePendingNotification {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][Collections.IDictionary]$PendingTasks
    )
    $lines = [Collections.Generic.List[string]]::new()
    $lines.Add("BoxBrain pending PC-side Codex work")
    $lines.Add("Updated: $([DateTimeOffset]::Now.ToString('o'))")
    $lines.Add("")
    if ($PendingTasks.Count -eq 0) {
        $lines.Add("No pending reasoning or locally rejected tasks.")
    }
    else {
        foreach ($id in @($PendingTasks.Keys | Sort-Object)) {
            $item = $PendingTasks[$id]
            $lines.Add("$id - $(Protect-BridgeText $item.title 160)")
            $lines.Add("  Status: $(Protect-BridgeText $item.status 48)")
            $lines.Add("  Reason: $(Protect-BridgeText $item.reason 200)")
        }
    }
    Write-BridgeTextAtomic -Path $Path -Text (($lines -join [Environment]::NewLine) + [Environment]::NewLine)
}

Export-ModuleMember -Function @(
    "Add-BridgeCompletionBlock",
    "Complete-BridgeTaskDocuments",
    "ConvertFrom-BridgeQueueText",
    "Enter-BridgeLock",
    "Exit-BridgeLock",
    "Get-BridgeBackoffSeconds",
    "Get-BridgeFileSha256",
    "Get-BridgeResultCheckpoint",
    "Get-BridgeSha256String",
    "Invoke-BridgeFetch",
    "Invoke-BridgeTrustedDispatcher",
    "Merge-BridgeTaskSources",
    "New-BridgeState",
    "Protect-BridgeText",
    "Publish-BridgeTaskCompletion",
    "Read-BridgeState",
    "Read-BridgeTextBounded",
    "Read-BridgeTrust",
    "Remove-BridgeTaskBlock",
    "Save-BridgeState",
    "Set-BridgeTaskCheckpointDocuments",
    "Set-BridgeTaskCheckpointText",
    "Test-BridgeCompletionRecord",
    "Test-BridgeDispatcherTrust",
    "Test-BridgeRemoteConfiguration",
    "Test-BridgeTaskSafety",
    "Test-BridgeTaskVerifiedComplete",
    "Write-BridgeJsonFile",
    "Write-BridgeLog",
    "Write-BridgePendingNotification",
    "Write-BridgeTextAtomic"
)
