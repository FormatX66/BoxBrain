#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$Model = "gpt-5-mini",
    [ValidateLength(0, 2000)]
    [string]$Goal = "",
    [string[]]$PiAddresses = @("10.12.194.1", "10.42.194.1", "192.168.0.194"),
    [string]$PiUser = "kali",
    [string]$KeyPath = (Join-Path $HOME ".ssh\boxbrain_pi_ed25519")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
    throw "The dedicated BoxBrain SSH identity was not found at $KeyPath."
}
if ([string]::IsNullOrWhiteSpace($env:OPENAI_API_KEY)) {
    throw "OPENAI_API_KEY is not set in this Windows process. It is transmitted only through the encrypted SSH session and is not written into Aurum's mind or evidence."
}
if ([string]::IsNullOrWhiteSpace($Model)) {
    throw "The review model cannot be empty."
}

$ssh = (Get-Command ssh.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$options = @(
    "-i", $KeyPath,
    "-o", "BatchMode=yes",
    "-o", "IdentitiesOnly=yes",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "ConnectTimeout=4"
)

$selected = $null
foreach ($address in $PiAddresses) {
    $probe = "test -f /opt/boxbrain/codelation/seed/aurum_dialogue.py -a -f /opt/boxbrain/codelation/seed/aurum_self_review.py"
    & $ssh @options "$PiUser@$address" $probe 2>$null
    if ($LASTEXITCODE -eq 0) {
        $selected = $address
        break
    }
}
if ($null -eq $selected) {
    throw "BBPI4 with the iterative Aurum self-review supervisor was not reachable over the approved USB-C, AP, or LAN SSH routes."
}

$payload = [ordered]@{
    api_key = $env:OPENAI_API_KEY
    model = $Model
    goal = $Goal
} | ConvertTo-Json -Compress

$target = "$PiUser@$selected"
$remote = "cd /opt/boxbrain/codelation && python3 seed/aurum_self_review.py --root /opt/boxbrain/codelation review --payload-stdin"
$oldPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    $output = @($payload | & $ssh @options $target $remote 2>&1)
    $exitCode = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $oldPreference
}
if ($exitCode -ne 0) {
    $tail = @($output | Select-Object -Last 8 | ForEach-Object {
        ([string]$_ -replace '[\r\n]+', ' ').Trim()
    }) -join " | "
    if ($tail.Length -gt 1200) { $tail = $tail.Substring(0, 1200) }
    throw "Aurum self-review failed closed; the installed mind was preserved. $tail"
}

$output
Write-Output "AURUM_ITERATIVE_SELF_REVIEW_COMPLETE address=$selected"
