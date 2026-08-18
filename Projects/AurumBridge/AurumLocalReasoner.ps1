param(
    [Parameter(Mandatory = $true)]
    [string]$JobPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-Result {
    param([object]$Value)
    $dir = Split-Path -Parent $OutputPath
    if ($dir) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $Value | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}

function Get-OllamaRuntime {
    try {
        $tags = Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 4
        $models = @($tags.models | ForEach-Object { [string]$_.name } | Where-Object { $_ })
        if ($models.Count -gt 0) {
            return [ordered]@{ available = $true; runtime = 'ollama'; endpoint = 'http://127.0.0.1:11434'; models = $models }
        }
    }
    catch { }
    return [ordered]@{ available = $false; runtime = 'ollama'; endpoint = 'http://127.0.0.1:11434'; models = @() }
}

function Get-LmStudioRuntime {
    try {
        $catalog = Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:1234/v1/models' -TimeoutSec 4
        $models = @($catalog.data | ForEach-Object { [string]$_.id } | Where-Object { $_ })
        if ($models.Count -gt 0) {
            return [ordered]@{ available = $true; runtime = 'lm-studio'; endpoint = 'http://127.0.0.1:1234'; models = $models }
        }
    }
    catch { }
    return [ordered]@{ available = $false; runtime = 'lm-studio'; endpoint = 'http://127.0.0.1:1234'; models = @() }
}

function Select-Model {
    param([string[]]$Models, [string]$Hint)
    if ($Hint) {
        foreach ($m in $Models) {
            if ($m -eq $Hint) { return $m }
        }
        throw "requested model is not locally available: $Hint"
    }
    return [string]$Models[0]
}

$started = Get-Date
$result = [ordered]@{
    schema = 'aurum-local-reason-result-v1'
    job_id = $null
    status = 'error'
    answer = $null
    provenance = [ordered]@{
        processor_identity = 'AurumLocalReasoner'
        host = $env:COMPUTERNAME
        processor_location = 'physical-windows-pc'
        provider = 'local'
        runtime = $null
        model = $null
        external_provider_usage_consumed = $false
        external_provider_usage_units = 0
        prompt_tokens = $null
        completion_tokens = $null
        total_tokens = $null
        input_chars = 0
        output_chars = 0
        elapsed_ms = 0
        observed_at = $null
    }
    runtime_inventory = @()
    error = $null
}

try {
    $job = Get-Content -LiteralPath $JobPath -Raw | ConvertFrom-Json
    if ([string]$job.schema -ne 'aurum-local-reason-job-v1') { throw 'invalid job schema' }
    $id = [string]$job.id
    if ($id -notmatch '^[A-Za-z0-9._-]{1,80}$') { throw 'invalid job id' }
    $prompt = [string]$job.prompt
    if ([string]::IsNullOrWhiteSpace($prompt) -or $prompt.Length -gt 12000) { throw 'prompt must contain 1..12000 characters' }
    $modelHint = if ($job.PSObject.Properties.Name -contains 'model_hint') { [string]$job.model_hint } else { '' }

    $result.job_id = $id
    $result.provenance.input_chars = $prompt.Length

    $runtimes = @((Get-OllamaRuntime), (Get-LmStudioRuntime))
    $result.runtime_inventory = @($runtimes | ForEach-Object {
        [ordered]@{ runtime = $_.runtime; available = [bool]$_.available; models = @($_.models) }
    })
    $runtime = $runtimes | Where-Object { $_.available } | Select-Object -First 1

    if (-not $runtime) {
        $result.status = 'unavailable'
        $result.error = [ordered]@{ type = 'local_reasoning_runtime_unavailable'; message = 'No local Ollama or LM Studio model endpoint is currently available on loopback.' }
    }
    elseif ($runtime.runtime -eq 'ollama') {
        $model = Select-Model -Models @($runtime.models) -Hint $modelHint
        $body = [ordered]@{
            model = $model
            prompt = $prompt
            stream = $false
            options = [ordered]@{ num_predict = 1024; temperature = 0.2 }
        } | ConvertTo-Json -Depth 8
        $response = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:11434/api/generate' -ContentType 'application/json' -Body $body -TimeoutSec 180
        $answer = [string]$response.response
        $result.status = 'ok'
        $result.answer = $answer
        $result.provenance.runtime = 'ollama'
        $result.provenance.model = $model
        if ($null -ne $response.prompt_eval_count) { $result.provenance.prompt_tokens = [int64]$response.prompt_eval_count }
        if ($null -ne $response.eval_count) { $result.provenance.completion_tokens = [int64]$response.eval_count }
        if ($null -ne $response.prompt_eval_count -and $null -ne $response.eval_count) {
            $result.provenance.total_tokens = [int64]$response.prompt_eval_count + [int64]$response.eval_count
        }
        $result.provenance.output_chars = $answer.Length
    }
    elseif ($runtime.runtime -eq 'lm-studio') {
        $model = Select-Model -Models @($runtime.models) -Hint $modelHint
        $body = [ordered]@{
            model = $model
            messages = @([ordered]@{ role = 'user'; content = $prompt })
            temperature = 0.2
            max_tokens = 1024
            stream = $false
        } | ConvertTo-Json -Depth 8
        $response = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:1234/v1/chat/completions' -ContentType 'application/json' -Body $body -TimeoutSec 180
        $answer = [string]$response.choices[0].message.content
        $result.status = 'ok'
        $result.answer = $answer
        $result.provenance.runtime = 'lm-studio'
        $result.provenance.model = $model
        if ($null -ne $response.usage) {
            $result.provenance.prompt_tokens = [int64]$response.usage.prompt_tokens
            $result.provenance.completion_tokens = [int64]$response.usage.completion_tokens
            $result.provenance.total_tokens = [int64]$response.usage.total_tokens
        }
        $result.provenance.output_chars = $answer.Length
    }
    else { throw 'unsupported local runtime' }
}
catch {
    $result.status = 'error'
    $result.error = [ordered]@{ type = $_.Exception.GetType().FullName; message = $_.Exception.Message }
}
finally {
    $elapsed = (Get-Date) - $started
    $result.provenance.elapsed_ms = [int64]$elapsed.TotalMilliseconds
    $result.provenance.observed_at = (Get-Date).ToUniversalTime().ToString('o')
    Write-Result -Value $result
    Write-Host "AURUM_LOCAL_REASON status=$($result.status) job=$($result.job_id) runtime=$($result.provenance.runtime) model=$($result.provenance.model) external_usage=$($result.provenance.external_provider_usage_consumed)"
}

if ($result.status -eq 'error') { exit 1 }
exit 0
