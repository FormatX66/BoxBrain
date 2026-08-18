Set-StrictMode -Version Latest

function Get-AurumUsageRoot {
    $candidates = @()
    if ($env:ProgramData) { $candidates += (Join-Path $env:ProgramData 'Aurum\UsageLoop') }
    if ($env:LOCALAPPDATA) { $candidates += (Join-Path $env:LOCALAPPDATA 'Aurum\UsageLoop') }

    foreach ($candidate in $candidates) {
        try {
            New-Item -ItemType Directory -Path $candidate -Force -ErrorAction Stop | Out-Null
            return $candidate
        }
        catch {
            continue
        }
    }
    throw 'AURUM_USAGE_LOOP_NO_WRITABLE_STATE_ROOT'
}

function ConvertTo-AurumSafeText {
    param(
        [AllowNull()][string]$Text,
        [int]$MaxLength = 500
    )
    if ($null -eq $Text) { return '' }
    $safe = [string]$Text
    $safe = [regex]::Replace($safe, '(?i)sk-[A-Za-z0-9_-]{8,}', '[REDACTED_OPENAI_KEY]')
    $safe = [regex]::Replace($safe, '(?i)Bearer\s+[A-Za-z0-9._~+/-]+=*', 'Bearer [REDACTED]')
    $safe = [regex]::Replace($safe, '(?i)(password|passwd|token|secret)\s*[:=]\s*[^\s,;]+', '$1=[REDACTED]')
    $safe = $safe -replace '[\r\n\t]+', ' '
    $safe = $safe.Trim()
    if ($safe.Length -gt $MaxLength) { return $safe.Substring(0, $MaxLength) }
    return $safe
}

function Get-AurumUsageStatePath {
    $root = Get-AurumUsageRoot
    return (Join-Path $root 'state.json')
}

function Get-AurumUsageState {
    $root = Get-AurumUsageRoot
    $statePath = Join-Path $root 'state.json'
    if (Test-Path -LiteralPath $statePath) {
        try { return (Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json) } catch { }
    }
    return [pscustomobject]@{
        schema = 'aurum-usage-loop-state-v1'
        model_access = 'unknown'
        local_only_continuation = $false
        report_pending = $false
        latest_incident_id = $null
        latest_incident_at = $null
        last_scan_at = $null
        state_root = $root
    }
}

function Save-AurumUsageState {
    param([Parameter(Mandatory = $true)]$State)
    $path = Get-AurumUsageStatePath
    $State | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $path -Encoding UTF8
}

function Get-AurumUsageIncidentId {
    param(
        [string]$Source,
        [string]$Kind,
        [string]$ObservedAt,
        [string]$Summary
    )
    $material = "$Source|$Kind|$ObservedAt|$Summary"
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($material)
        $hash = $sha.ComputeHash($bytes)
        return (($hash | ForEach-Object { $_.ToString('x2') }) -join '').Substring(0, 24)
    }
    finally {
        $sha.Dispose()
    }
}

function Register-AurumUsageIncident {
    param([Parameter(Mandatory = $true)]$Event)

    $allowedKinds = @('usage_limit', 'credit_exhausted', 'rate_limit', 'manual_observation')
    $allowedSources = @('chatgpt', 'codex', 'work', 'openai', 'bridge', 'unknown')

    $kind = ConvertTo-AurumSafeText ([string]$Event.kind) 80
    $source = ConvertTo-AurumSafeText ([string]$Event.source) 80
    if ($allowedKinds -notcontains $kind) { throw "AURUM_USAGE_LOOP_INVALID_KIND $kind" }
    if ($allowedSources -notcontains $source) { throw "AURUM_USAGE_LOOP_INVALID_SOURCE $source" }

    $observedAt = if ($Event.PSObject.Properties.Name -contains 'observed_at' -and [string]$Event.observed_at) {
        try { ([DateTimeOffset]::Parse([string]$Event.observed_at)).ToString('o') } catch { throw 'AURUM_USAGE_LOOP_INVALID_OBSERVED_AT' }
    }
    else {
        [DateTimeOffset]::Now.ToString('o')
    }

    $summary = ConvertTo-AurumSafeText ([string]$Event.summary) 500
    if (-not $summary) { $summary = 'usage availability incident observed' }
    $task = ''
    if ($Event.PSObject.Properties.Name -contains 'task') { $task = ConvertTo-AurumSafeText ([string]$Event.task) 500 }

    $evidenceRefs = @()
    if ($Event.PSObject.Properties.Name -contains 'evidence_refs' -and $null -ne $Event.evidence_refs) {
        foreach ($ref in @($Event.evidence_refs) | Select-Object -First 20) {
            $safeRef = ConvertTo-AurumSafeText ([string]$ref) 300
            if ($safeRef) { $evidenceRefs += $safeRef }
        }
    }

    $incidentId = if ($Event.PSObject.Properties.Name -contains 'incident_id' -and [string]$Event.incident_id -match '^[A-Za-z0-9._-]{1,80}$') {
        [string]$Event.incident_id
    }
    else {
        Get-AurumUsageIncidentId -Source $source -Kind $kind -ObservedAt $observedAt -Summary $summary
    }

    $root = Get-AurumUsageRoot
    $incidentsRoot = Join-Path $root 'incidents'
    New-Item -ItemType Directory -Path $incidentsRoot -Force | Out-Null
    $incidentPath = Join-Path $incidentsRoot "$incidentId.json"

    if (Test-Path -LiteralPath $incidentPath) {
        $existing = Get-Content -LiteralPath $incidentPath -Raw | ConvertFrom-Json
        return [ordered]@{
            deduplicated = $true
            incident = $existing
            state = (Get-AurumUsageState)
        }
    }

    $incident = [ordered]@{
        schema = 'aurum-usage-incident-v1'
        incident_id = $incidentId
        source = $source
        kind = $kind
        observed_at = $observedAt
        recorded_at = [DateTimeOffset]::Now.ToString('o')
        host = $env:COMPUTERNAME
        task = $task
        summary = $summary
        evidence_refs = $evidenceRefs
        authoritative_usage_quantity = $null
        authoritative_usage_quantity_source = 'OpenAI server telemetry required'
        mitigation_overhead = [ordered]@{
            usage_loop_build_required = $true
            note = 'Building and operating this loop is compensatory work caused by recurring usage/orchestration failures and should be tracked separately from productive Aurum work.'
        }
        continuation = [ordered]@{
            model_dependent_work = 'pause-or-defer'
            deterministic_local_work = 'continue'
            preserve_checkpoint = $true
            destructive_actions = 'remain-separately-authorized'
        }
        support_report = [ordered]@{
            pending = $true
            append_to_existing_case = $true
            do_not_invent_usage_totals = $true
            requested_review = @(
                'authoritative usage consumed around the incident',
                'duplicate or redundant orchestration',
                'recovery loops after a known failure',
                'corrective reruns',
                'mitigation usage spent building the usage loop itself'
            )
        }
    }

    $incident | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $incidentPath -Encoding UTF8
    ($incident | ConvertTo-Json -Depth 12 -Compress) | Add-Content -LiteralPath (Join-Path $root 'ledger.jsonl') -Encoding UTF8

    $continuationSignal = [ordered]@{
        schema = 'aurum-usage-continuation-signal-v1'
        incident_id = $incidentId
        emitted_at = [DateTimeOffset]::Now.ToString('o')
        model_access = 'limited'
        local_only_continuation = $true
        instructions = @(
            'continue deterministic local file/build/test/git/log work that does not need unavailable model usage',
            'checkpoint model-dependent work instead of replaying it',
            'deduplicate retries',
            'preserve evidence for telemetry correlation'
        )
    }
    $continuationSignal | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $root 'continuation-signal.json') -Encoding UTF8

    $state = [ordered]@{
        schema = 'aurum-usage-loop-state-v1'
        model_access = 'limited'
        local_only_continuation = $true
        report_pending = $true
        latest_incident_id = $incidentId
        latest_incident_at = $observedAt
        last_scan_at = (Get-AurumUsageState).last_scan_at
        state_root = $root
    }
    Save-AurumUsageState -State $state

    return [ordered]@{
        deduplicated = $false
        incident = $incident
        state = $state
    }
}

function Invoke-AurumUsageScan {
    param([int]$LookbackMinutes = 90)

    if ($LookbackMinutes -lt 5 -or $LookbackMinutes -gt 1440) { throw 'AURUM_USAGE_LOOP_INVALID_LOOKBACK' }
    $roots = @()
    if ($env:USERPROFILE) { $roots += (Join-Path $env:USERPROFILE '.codex') }
    if ($env:LOCALAPPDATA) { $roots += (Join-Path $env:LOCALAPPDATA 'OpenAI') }
    if ($env:APPDATA) { $roots += (Join-Path $env:APPDATA 'OpenAI') }

    $cutoff = (Get-Date).AddMinutes(-1 * $LookbackMinutes)
    $pattern = '(?i)\b(usage[ _-]?limit|insufficient[_ -]?quota|credits? exhausted|out of (usage|credits)|reached (your )?(usage|rate) limit|rate[_ -]?limit[_ -]?exceeded|too many requests)\b'
    $detections = @()

    foreach ($root in $roots | Select-Object -Unique) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        $files = @(Get-ChildItem -LiteralPath $root -File -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTime -ge $cutoff -and $_.Length -le 2MB -and $_.Extension -in @('.log', '.txt', '.json', '.jsonl') } |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 60)
        foreach ($file in $files) {
            try {
                $matches = @(Select-String -LiteralPath $file.FullName -Pattern $pattern -AllMatches -ErrorAction Stop | Select-Object -Last 5)
                foreach ($match in $matches) {
                    $detections += [ordered]@{
                        path = $file.FullName
                        modified_at = $file.LastWriteTime.ToString('o')
                        line_number = [int]$match.LineNumber
                        excerpt = ConvertTo-AurumSafeText ([string]$match.Line) 300
                    }
                }
            }
            catch { continue }
        }
    }

    $state = Get-AurumUsageState
    $state.last_scan_at = [DateTimeOffset]::Now.ToString('o')
    Save-AurumUsageState -State $state

    $registered = @()
    foreach ($detection in $detections | Select-Object -First 20) {
        $event = [pscustomobject]@{
            source = 'openai'
            kind = 'usage_limit'
            observed_at = $detection.modified_at
            summary = "Local OpenAI/Codex log matched a usage-limit signal: $($detection.excerpt)"
            task = 'automatic local usage-limit detection'
            evidence_refs = @("$($detection.path):$($detection.line_number)")
        }
        $registered += (Register-AurumUsageIncident -Event $event)
    }

    return [ordered]@{
        schema = 'aurum-usage-scan-result-v1'
        scanned_at = [DateTimeOffset]::Now.ToString('o')
        lookback_minutes = $LookbackMinutes
        roots = @($roots | Where-Object { Test-Path -LiteralPath $_ })
        detections = $detections
        registered = $registered
        state = (Get-AurumUsageState)
    }
}

function Get-AurumUsageLoopStatus {
    $root = Get-AurumUsageRoot
    $incidentsRoot = Join-Path $root 'incidents'
    $latest = @()
    if (Test-Path -LiteralPath $incidentsRoot) {
        $latest = @(Get-ChildItem -LiteralPath $incidentsRoot -File -Filter '*.json' -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTimeUtc -Descending |
            Select-Object -First 10 |
            ForEach-Object {
                try { Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json } catch { $null }
            } |
            Where-Object { $null -ne $_ })
    }
    return [ordered]@{
        schema = 'aurum-usage-loop-status-v1'
        root = $root
        state = (Get-AurumUsageState)
        latest_incidents = $latest
        continuation_signal_exists = (Test-Path -LiteralPath (Join-Path $root 'continuation-signal.json'))
    }
}
