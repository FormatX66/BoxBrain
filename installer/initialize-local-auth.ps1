#Requires -Version 5.1
[CmdletBinding()]
param(
    [switch]$Rotate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$dataDirectory = Join-Path $repositoryRoot "controller\data"
$tokenPath = Join-Path $dataDirectory "boxbrain-api-token.local"

function Protect-TokenFile {
    param([Parameter(Mandatory)][string]$Path)

    try {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        $acl = Get-Acl -LiteralPath $Path
        $acl.SetAccessRuleProtection($true, $false)
        $rule = New-Object Security.AccessControl.FileSystemAccessRule(
            $identity,
            "FullControl",
            "Allow"
        )
        $acl.SetAccessRule($rule)
        Set-Acl -LiteralPath $Path -AclObject $acl
    }
    catch {
        Write-Warning "Token exists, but its file permissions could not be narrowed: $($_.Exception.Message)"
    }
}

if ((Test-Path -LiteralPath $tokenPath) -and -not $Rotate) {
    Protect-TokenFile -Path $tokenPath
    Write-Host "[ready] Local API token already exists."
    Write-Host "        $tokenPath"
    exit 0
}

[IO.Directory]::CreateDirectory($dataDirectory) | Out-Null
$bytes = New-Object byte[] 32
$generator = [Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $generator.GetBytes($bytes)
}
finally {
    $generator.Dispose()
}
$token = [Convert]::ToBase64String($bytes)
[IO.File]::WriteAllText($tokenPath, $token, (New-Object Text.UTF8Encoding($false)))

Protect-TokenFile -Path $tokenPath

Write-Host "[created] Local API token. Its value was not printed."
Write-Host "          $tokenPath"
Write-Host "          The file is ignored by Git."