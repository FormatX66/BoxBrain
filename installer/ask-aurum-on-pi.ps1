#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Prompt,

    [string]$Model = "gpt-5-mini",
    [string[]]$PiAddresses = @("10.42.194.1", "10.12.194.1", "192.168.0.194"),
    [string]$PiUser = "kali",
    [string]$KeyPath = (Join-Path $HOME ".ssh\boxbrain_pi_ed25519"),
    [switch]$SkipBootstrapSelfBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
    throw "The dedicated BoxBrain SSH identity was not found at $KeyPath."
}
if ([string]::IsNullOrWhiteSpace($env:OPENAI_API_KEY)) {
    throw "OPENAI_API_KEY is not set in this Windows session. The key is required only in memory and is not written to the Pi."
}

$ssh = Get-Command ssh.exe -ErrorAction Stop
$options = @(
    "-i", $KeyPath,
    "-o", "BatchMode=yes",
    "-o", "IdentitiesOnly=yes",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "ConnectTimeout=4"
)

$selected = $null
foreach ($address in $PiAddresses) {
    & $ssh.Source @options "$PiUser@$address" "test -f /opt/boxbrain/codelation/seed/aurum_dialogue.py" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $selected = $address
        break
    }
}
if ($null -eq $selected) {
    throw "BBPI4 with the Aurum dialogue surface was not reachable over the AP, USB-C, or LAN SSH routes."
}

$payload = [ordered]@{
    api_key = $env:OPENAI_API_KEY
    prompt = $Prompt
    model = $Model
    self_build_if_bootstrap = -not $SkipBootstrapSelfBuild.IsPresent
} | ConvertTo-Json -Compress

$target = "$PiUser@$selected"
$remote = "cd /opt/boxbrain/codelation && python3 seed/aurum_dialogue.py --root /opt/boxbrain/codelation session"
$payload | & $ssh.Source @options $target $remote
if ($LASTEXITCODE -ne 0) {
    throw "Aurum dialogue session failed. The bootstrap mind is preserved unless a validated self-build completed."
}
