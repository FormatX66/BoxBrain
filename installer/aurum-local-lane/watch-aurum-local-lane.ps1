#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$ConfigPath,
    [ValidateSet("Watch", "Poll")]
    [string]$Mode = "Watch"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Read-JsonFile {
    param([Parameter(Mandatory)][string]$Path, [int]$MaximumBytes = 32768)
    $item = Get-Item -LiteralPath $Path -ErrorAction Stop
    if ($item.Length -gt $MaximumBytes) { throw "JSON file exceeds bounded size." }
    return (Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -ErrorAction Stop)
}

function Write-JsonAtomic {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)]$Value)
    $directory = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
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

function Sync-Repository {
    $repo = [string]$script:Config.repository_root
    $remote = Invoke-GitBounded @("-C", $repo, "remote", "get-url", "origin")
    $url = [string]($remote.Output | Select-Object -First 1)
    if ($remote.ExitCode -ne 0 -or $url -notmatch '(?i)github\.com[:/]FormatX66/BoxBrain(?:\.git)?$') {
        throw "Aurum lane repository remote is not the approved BoxBrain repository."
    }
    $status = Invoke-GitBounded @("-C", $repo, "status", "--porcelain", "--untracked-files=no")
    if ($status.ExitCode -ne 0 -or $status.Output.Count -gt 0) {
        throw "Aurum lane repository has unrelated local changes."
    }
    $fetch = Invoke-GitBounded @("-C", $repo, "fetch", "--no-tags", "origin", "+refs/heads/main:refs/remotes/origin/main")
    if ($fetch.ExitCode -ne 0) { throw "Aurum lane Git fetch failed." }
    $checkout = Invoke-GitBounded @("-C", $repo, "checkout", "main")
    if ($checkout.ExitCode -ne 0) { throw "Aurum lane could not select main." }
    $merge = Invoke-GitBounded @("-C", $repo, "merge", "--ff-only", "refs/remotes/origin/main")
    if ($merge.ExitCode -ne 0) { throw "Aurum lane could not fast-forward main." }
}

function Read-Task {
    $path = Join-Path ([string]$script:Config.repository_root) ".codex\local-lane\AURUM_TASK.json"
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
    $task = Read-JsonFile -Path $path -MaximumBytes 8192
    $names = @($task.PSObject.Properties.Name | Sort-Object)
    $expected = @("action", "address", "request_id", "requested_at", "schema_version", "target")
    if (($names -join '|') -ne (($expected | Sort-Object) -join '|')) { throw "Aurum lane task fields are not exact." }
    if ([int]$task.schema_version -ne 1) { throw "Aurum lane task schema is unsupported." }
    if ([string]$task.request_id -notmatch '^[A-Za-z0-9._-]{1,64}$') { throw "Aurum lane request ID is invalid." }
    if ([string]$task.action -notin @("deploy", "verify")) { throw "Aurum lane action is not allowlisted." }
    if ([string]$task.target -ne "BBPI4") { throw "Aurum lane target is not allowlisted." }
    if ([string]$task.address -ne "192.168.0.194") { throw "Aurum lane address is not allowlisted." }
    [DateTimeOffset]$when = [DateTimeOffset]::MinValue
    if (-not [DateTimeOffset]::TryParse([string]$task.requested_at, [ref]$when)) { throw "Aurum lane request timestamp is invalid." }
    return $task
}

function Read-State {
    $path = [string]$script:Config.state_path
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        return [ordered]@{ schema_version = 1; last_request_id = $null; last_completed_at = $null; publish_pending = $false; pending_result = $null }
    }
    $state = Read-JsonFile -Path $path -MaximumBytes 32768
    if ([int]$state.schema_version -ne 1) { throw "Aurum lane state schema is unsupported." }
    return [ordered]@{
        schema_version = 1
        last_request_id = [string]$state.last_request_id
        last_completed_at = [string]$state.last_completed_at
        publish_pending = [bool]$state.publish_pending
        pending_result = $state.pending_result
    }
}

function Save-State {
    param([Parameter(Mandatory)]$State)
    Write-JsonAtomic -Path ([string]$script:Config.state_path) -Value $State
}

function Invoke-PiEvidence {
    $key = [string]$script:Config.key_path
    $addresses = @("10.42.194.1", "10.12.194.1", "192.168.0.194")
    $options = @("-i", $key, "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=4")
    $remote = "cat /opt/boxbrain/codelation/verification/AURUM_LIVE_VERIFY.txt"
    $required = @(
        "identity=BBPI4/Aurum",
        "AURUM_LIVE_VERIFIED",
        "AURUM_PEER_SELF_TEST_OK",
        "matching_systemd_units=0",
        "matching_user_cron=0",
        "matching_root_cron=0"
    )

    foreach ($address in $addresses) {
        $target = "kali@$address"
        $old = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $lines = @(& $script:Ssh @options $target $remote 2>&1)
            $code = $LASTEXITCODE
        }
        finally { $ErrorActionPreference = $old }
        if ($code -ne 0) { continue }

        $text = ($lines -join "`n")
        if ($text.Length -gt 16384) { throw "BBPI4 verification evidence exceeded the bounded size." }
        $valid = $true
        foreach ($marker in $required) {
            if (-not $text.Contains($marker)) {
                $valid = $false
                break
            }
        }
        if ($valid) {
            return [pscustomobject]@{ Address = $address; Text = $text }
        }
    }
    throw "BBPI4 verification evidence is unavailable on approved AP, USB-C, and LAN routes."
}

function Invoke-Deploy {
    $repo = [string]$script:Config.repository_root
    $deployer = Join-Path $repo "installer\deploy-aurum-live-to-pi.ps1"
    if (-not (Test-Path -LiteralPath $deployer -PathType Leaf)) { throw "Approved Aurum deployer is missing." }
    $actualDeployer = (Get-FileHash -LiteralPath $deployer -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualDeployer -ne [string]$script:Config.approved_deployer_sha256) {
        throw "Aurum deployer changed after local approval; reinstall the lane to review it."
    }
    $actualTree = Get-CodelationTreeHash -Root $repo
    if ($actualTree -ne [string]$script:Config.approved_codelation_tree_sha256) {
        throw "Codelation source changed after local approval; reinstall the lane to review it."
    }
    $old = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = @(& $script:PowerShell -NoProfile -ExecutionPolicy Bypass -File $deployer -KeyPath ([string]$script:Config.key_path) 2>&1)
        $code = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $old }
    if ($code -ne 0) {
        $tail = @($output | Select-Object -Last 8 | ForEach-Object { ([string]$_ -replace '[\r\n]+', ' ').Trim() }) -join " | "
        if ($tail.Length -gt 1200) { $tail = $tail.Substring(0, 1200) }
        throw "Aurum deployer failed: $tail"
    }
    return @($output | Select-Object -Last 12 | ForEach-Object { ([string]$_ -replace '[\r\n]+', ' ').Trim() })
}

function Publish-Result {
    param([Parameter(Mandatory)]$Result)
    $repo = [string]$script:Config.repository_root
    $relative = ".codex/local-lane/AURUM_RESULT.json"
    $path = Join-Path $repo ($relative -replace '/', '\')
    Write-JsonAtomic -Path $path -Value $Result
    $changed = Invoke-GitBounded @("-C", $repo, "status", "--porcelain", "--", $relative)
    if ($changed.ExitCode -ne 0) { throw "Could not inspect Aurum lane result state." }
    if ($changed.Output.Count -gt 0) {
        $add = Invoke-GitBounded @("-C", $repo, "add", "--", $relative)
        if ($add.ExitCode -ne 0) { throw "Could not stage Aurum lane result." }
        $commit = Invoke-GitBounded @("-C", $repo, "commit", "-m", "Record Aurum local lane result $([string]$Result.request_id)")
        if ($commit.ExitCode -ne 0) { throw "Could not commit Aurum lane result." }
    }
    $push = Invoke-GitBounded @("-C", $repo, "push", "origin", "HEAD:refs/heads/main")
    if ($push.ExitCode -eq 0) { return }
    $fetch = Invoke-GitBounded @("-C", $repo, "fetch", "--no-tags", "origin", "+refs/heads/main:refs/remotes/origin/main")
    if ($fetch.ExitCode -ne 0) { throw "Could not refresh before bounded result retry." }
    $rebase = Invoke-GitBounded @("-C", $repo, "rebase", "refs/remotes/origin/main")
    if ($rebase.ExitCode -ne 0) { throw "Could not rebase bounded Aurum lane result." }
    $push = Invoke-GitBounded @("-C", $repo, "push", "origin", "HEAD:refs/heads/main")
    if ($push.ExitCode -ne 0) { throw "Could not publish Aurum lane result." }
}

function New-ResultHash {
    param([Parameter(Mandatory)][string]$Value)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value)))).Replace("-", "").ToLowerInvariant()
    }
    finally { $sha.Dispose() }
}

function Complete-PendingPublish {
    param([Parameter(Mandatory)]$State)
    if (-not [bool]$State.publish_pending -or $null -eq $State.pending_result) { return $State }
    Publish-Result -Result $State.pending_result
    $State.publish_pending = $false
    $State.pending_result = $null
    Save-State -State $State
    return $State
}

function Invoke-Cycle {
    $state = Read-State
    if ([bool]$state.publish_pending) {
        $state = Complete-PendingPublish -State $state
    }

    Sync-Repository
    $task = Read-Task
    if ($null -eq $task) { return }
    if ([string]$state.last_request_id -eq [string]$task.request_id) { return }

    $started = [DateTimeOffset]::UtcNow
    $deployTail = @()
    $result = $null
    try {
        if ([string]$task.action -eq "deploy") { $deployTail = Invoke-Deploy }
        $evidence = Invoke-PiEvidence
        $result = [ordered]@{
            schema_version = 1
            request_id = [string]$task.request_id
            action = [string]$task.action
            target = "BBPI4"
            address = [string]$evidence.Address
            verified = $true
            status = "AURUM_LOCAL_LANE_OK"
            evidence_sha256 = New-ResultHash -Value ([string]$evidence.Text)
            evidence = @(([string]$evidence.Text) -split "`n" | Where-Object { $_ -match '^(identity|python|architecture|before|peer|after|mind|seed|seed_migration|matching_|rollback=)' })
            deploy_tail = $deployTail
            started_at = $started.ToString("o")
            completed_at = [DateTimeOffset]::UtcNow.ToString("o")
        }
    }
    catch {
        $message = ([string]$_.Exception.Message -replace '[\r\n]+', ' ').Trim()
        if ($message.Length -gt 1600) { $message = $message.Substring(0, 1600) }
        $result = [ordered]@{
            schema_version = 1
            request_id = [string]$task.request_id
            action = [string]$task.action
            target = "BBPI4"
            address = "192.168.0.194"
            verified = $false
            status = "AURUM_LOCAL_LANE_FAILED"
            error = $message
            started_at = $started.ToString("o")
            completed_at = [DateTimeOffset]::UtcNow.ToString("o")
        }
    }

    $state = [ordered]@{
        schema_version = 1
        last_request_id = [string]$task.request_id
        last_completed_at = [DateTimeOffset]::UtcNow.ToString("o")
        publish_pending = $true
        pending_result = $result
    }
    Save-State -State $state
    Complete-PendingPublish -State $state | Out-Null
}

$script:Config = Read-JsonFile -Path $ConfigPath -MaximumBytes 16384
if ([int]$script:Config.schema_version -ne 1) { throw "Aurum lane configuration schema is unsupported." }
$actualWatcher = (Get-FileHash -LiteralPath $MyInvocation.MyCommand.Path -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualWatcher -ne [string]$script:Config.approved_watcher_sha256) { throw "Installed Aurum lane watcher hash mismatch." }
$script:Git = (Get-Command git.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$script:Ssh = (Get-Command ssh.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$script:PowerShell = (Get-Command powershell.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source

if ($Mode -eq "Poll") {
    Invoke-Cycle
    exit 0
}

while ($true) {
    try { Invoke-Cycle } catch { }
    Start-Sleep -Seconds ([int]$script:Config.poll_seconds)
}
