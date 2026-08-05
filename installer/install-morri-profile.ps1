#Requires -Version 5.1
#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [ValidatePattern("^[A-Za-z][A-Za-z0-9._-]{0,19}$")]
    [string]$AccountName = "Morri",

    [ValidateLength(1, 48)]
    [string]$FullName = "Morri",

    [ValidateLength(1, 48)]
    [string]$Description = "Morris PC standard user"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$statusPath = "HKLM:\SOFTWARE\BoxBrain"
$createdHere = $false

function Set-MorriProfileStatus {
    param(
        [Parameter(Mandatory)][string]$Status,
        [string]$Detail = ""
    )

    New-Item -Path $statusPath -Force | Out-Null
    New-ItemProperty -Path $statusPath -Name "MorriProfileStatus" `
        -Value $Status -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $statusPath -Name "MorriProfileDetail" `
        -Value $Detail -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $statusPath -Name "MorriProfileUpdatedUtc" `
        -Value ([DateTime]::UtcNow.ToString("o")) -PropertyType String -Force |
        Out-Null
}

function Resolve-BuiltinGroupName {
    param([Parameter(Mandatory)][string]$Sid)

    $identity = [Security.Principal.SecurityIdentifier]::new($Sid)
    $account = $identity.Translate([Security.Principal.NTAccount]).Value
    return ($account -split "\\", 2)[-1]
}

try {
    Set-MorriProfileStatus -Status "starting"
    if (Get-LocalUser -Name $AccountName -ErrorAction SilentlyContinue) {
        throw "The local account $AccountName already exists; refusing to overwrite it."
    }

    Set-MorriProfileStatus -Status "awaiting_password"
    $password = Read-Host "Temporary password for $AccountName" -AsSecureString
    $plainPassword = [PSCredential]::new($AccountName, $password).
        GetNetworkCredential().Password
    if (
        $plainPassword.Length -lt 14 -or
        $plainPassword -notmatch "[A-Z]" -or
        $plainPassword -notmatch "[a-z]" -or
        $plainPassword -notmatch "[0-9]"
    ) {
        throw "The temporary password does not meet BoxBrain complexity rules."
    }

    Set-MorriProfileStatus -Status "creating_account"
    New-LocalUser `
        -Name $AccountName `
        -FullName $FullName `
        -Description $Description `
        -Password $password `
        -AccountNeverExpires `
        -UserMayNotChangePassword:$false | Out-Null
    $createdHere = $true

    $usersGroup = Resolve-BuiltinGroupName -Sid "S-1-5-32-545"
    $administratorsGroup = Resolve-BuiltinGroupName -Sid "S-1-5-32-544"
    Add-LocalGroupMember -Group $usersGroup -Member $AccountName

    $credential = [PSCredential]::new(".\$AccountName", $password)
    $profileProcess = Start-Process `
        -FilePath "$env:WINDIR\System32\cmd.exe" `
        -ArgumentList "/d /c exit" `
        -Credential $credential `
        -LoadUserProfile `
        -WindowStyle Hidden `
        -Wait `
        -PassThru
    if ($profileProcess.ExitCode -ne 0) {
        throw "The first profile load failed with code $($profileProcess.ExitCode)."
    }

    & "$env:WINDIR\System32\net.exe" user $AccountName /passwordreq:yes |
        Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Windows did not require a password for $AccountName."
    }
    & "$env:WINDIR\System32\net.exe" user $AccountName /logonpasswordchg:yes |
        Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Windows did not require a password change at next sign-in."
    }

    $user = Get-LocalUser -Name $AccountName
    $administratorMember = Get-LocalGroupMember -Group $administratorsGroup |
        Where-Object { $_.SID -eq $user.SID }
    if ($administratorMember) {
        throw "$AccountName was unexpectedly added to Administrators."
    }
    $profile = Get-CimInstance Win32_UserProfile |
        Where-Object { $_.SID -eq $user.SID.Value }
    if ($null -eq $profile -or -not (Test-Path -LiteralPath $profile.LocalPath)) {
        throw "Windows did not create the $AccountName profile directory."
    }

    Set-MorriProfileStatus -Status "ready"
    Write-Output "MORRI_PROFILE_READY account=$AccountName path=$($profile.LocalPath)"
}
catch {
    $detail = $_.Exception.Message
    if ($createdHere) {
        Disable-LocalUser -Name $AccountName -ErrorAction SilentlyContinue
    }
    Set-MorriProfileStatus -Status "failed" -Detail $detail
    throw
}
finally {
    if ($null -ne (Get-Variable plainPassword -ErrorAction SilentlyContinue)) {
        $plainPassword = $null
    }
}
