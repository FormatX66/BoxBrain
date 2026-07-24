[CmdletBinding()]
param()

$requirements = @(
    @{ Name = "Git"; Command = "git"; VersionArguments = @("--version") },
    @{ Name = "Python"; Command = "python"; VersionArguments = @("--version") },
    @{ Name = "Flutter"; Command = "flutter"; VersionArguments = @("--version") }
)

$missing = @()

foreach ($requirement in $requirements) {
    $command = Get-Command $requirement.Command -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        Write-Host "[missing] $($requirement.Name)"
        $missing += $requirement.Name
        continue
    }

    $version = & $requirement.Command @($requirement.VersionArguments) 2>&1 |
        Select-Object -First 1
    Write-Host "[found]   $($requirement.Name): $version"
}

if ($missing.Count -gt 0) {
    Write-Host ""
    Write-Host "Missing prerequisites: $($missing -join ', ')"
    Write-Host "No changes were made."
    exit 1
}

Write-Host ""
Write-Host "All base prerequisites are available. No changes were made."

