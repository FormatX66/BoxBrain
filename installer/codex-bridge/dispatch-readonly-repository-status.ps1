#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^BB-\d{3}$')]
    [string]$TaskId,

    [Parameter(Mandatory)]
    [string]$RepositoryRoot,

    [Parameter(Mandatory)]
    [string]$OutputPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repository = (Resolve-Path -LiteralPath $RepositoryRoot).Path
if (-not (Test-Path -LiteralPath (Join-Path $repository ".git"))) {
    $gitDirectory = & git.exe -C $repository rev-parse --git-dir 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($gitDirectory)) {
        throw "The approved repository root is not a Git worktree."
    }
}

$headOutput = @(& git.exe -C $repository rev-parse HEAD 2>$null)
$headExitCode = $LASTEXITCODE
$head = [string]($headOutput | Select-Object -First 1)
if ($headExitCode -ne 0 -or $head -notmatch '^[a-f0-9]{40}$') {
    throw "Could not read the repository commit."
}
$branchOutput = @(& git.exe -C $repository branch --show-current 2>$null)
$branchExitCode = $LASTEXITCODE
$branch = [string]($branchOutput | Select-Object -First 1)
if ($branchExitCode -ne 0) { throw "Could not read the repository branch." }
$trackedCount = @(& git.exe -C $repository ls-files).Count
if ($LASTEXITCODE -ne 0) { throw "Could not count tracked files." }
$dirtyCount = @(& git.exe -C $repository status --porcelain).Count
if ($LASTEXITCODE -ne 0) { throw "Could not inspect the worktree." }

$result = [ordered]@{
    schema_version = 1
    task_id = $TaskId
    verified = $true
    action = "read_only_repository_status"
    summary = "Read-only repository status verified at commit $($head.Substring(0, 12)); tracked_files=$trackedCount; dirty_entries=$dirtyCount."
    evidence = [ordered]@{
        commit = $head
        branch = $branch
        tracked_file_count = $trackedCount
        dirty_entry_count = $dirtyCount
    }
    side_effects = @()
    completed_at = [DateTimeOffset]::UtcNow.ToString("o")
}

$outputDirectory = Split-Path -Parent $OutputPath
if (-not (Test-Path -LiteralPath $outputDirectory -PathType Container)) {
    throw "The approved result directory is missing."
}
$resolvedOutputDirectory = (Resolve-Path -LiteralPath $outputDirectory).Path.TrimEnd('\') + '\'
$fullOutput = [IO.Path]::GetFullPath($OutputPath)
if (-not $fullOutput.StartsWith($resolvedOutputDirectory, [StringComparison]::OrdinalIgnoreCase)) {
    throw "The result path escapes the approved result directory."
}
[IO.File]::WriteAllText(
    $fullOutput,
    (($result | ConvertTo-Json -Depth 6) + [Environment]::NewLine),
    [Text.UTF8Encoding]::new($false)
)

Write-Output "BRIDGE_READ_ONLY_RESULT task_id=$TaskId"
