# Registers the observer only. Farmer remains a separate SYSTEM service.
$ErrorActionPreference = 'Stop'
$name = 'Future Branch Workload Monitor'
$script = Join-Path $PSScriptRoot 'monitor.py'
$python = (Get-Command python -ErrorAction Stop).Source
$listener = Get-NetTCPConnection -LocalPort 19467 -State Listen -ErrorAction SilentlyContinue
$owned = $null
if ($listener) {
    $ids = @($listener.OwningProcess | Sort-Object -Unique)
    if ($ids.Count -ne 1) { throw 'Ambiguous dashboard listener; preserved.' }
    $owned = Get-CimInstance Win32_Process -Filter "ProcessId = $($ids[0])"
    if ($owned.Name -notin @('python.exe','pythonw.exe') -or $owned.CommandLine -notmatch [regex]::Escape($script)) {
        throw 'Port belongs to another application; preserved.'
    }
    $python = $owned.ExecutablePath
}
$pythonw = Join-Path (Split-Path -Parent $python) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw -PathType Leaf)) { throw 'A windowless Python runtime is required for this observer task.' }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if ($existing) {
    if ($existing.Actions.Execute -ne $pythonw -or $existing.Actions.Arguments -ne ('"{0}" serve' -f $script)) {
        throw 'Existing task has a different action; preserved.'
    }
}
$action = New-ScheduledTaskAction -Execute $pythonw -Argument ('"{0}" serve' -f $script) -WorkingDirectory $PSScriptRoot
$logon = New-ScheduledTaskTrigger -AtLogOn -User $identity
# Failure-restart settings alone did not restart a force-ended observer on this
# host. The same task also gets a bounded one-minute liveness trigger. IgnoreNew
# prevents another instance while healthy; this never schedules explorer work.
$liveness = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -Hidden -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
# Register first: if permissions refuse this operation, the existing dashboard stays up.
Register-ScheduledTask -TaskName $name -Action $action -Trigger @($logon,$liveness) -Principal $principal -Settings $settings -Force | Out-Null
if ($owned -and $existing -and $existing.State -eq 'Running') {
    Write-Output 'Observer schedule updated in place; running collector preserved.'
    exit 0
}
if ($owned) { Stop-Process -Id $owned.ProcessId -ErrorAction Stop }
try {
    Start-ScheduledTask -TaskName $name
    $deadline = (Get-Date).AddSeconds(12)
    do {
        Start-Sleep -Milliseconds 250
        try { $status = Invoke-RestMethod 'http://127.0.0.1:19467/api/status' -TimeoutSec 1 } catch { $status = $null }
    } until ($status -or (Get-Date) -ge $deadline)
    if (-not $status -or $status.version -ne 'unified-workloads-v1') { throw 'Observer scheduled task did not become ready.' }
    $task = Get-ScheduledTask -TaskName $name
    if ($task.State -ne 'Running') { throw 'Observer scheduled task is not running.' }
    [ordered]@{task=$name;state=[string]$task.State;principal=$identity;startup='User logon and one-minute liveness trigger';restart_count=3;restart_delay_seconds=60;authority_granted=$false} | ConvertTo-Json
} catch {
    Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if (-not $existing) { Unregister-ScheduledTask -TaskName $name -Confirm:$false }
    & (Join-Path $PSScriptRoot 'start-monitor.ps1')
    throw
}
