#Requires -Version 5.1
#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [ValidatePattern("^[A-Za-z0-9]{8}$")]
    [string]$VncPassword,

    [ValidatePattern("^[A-Za-z0-9]{8}$")]
    [string]$ControlPassword,

    [switch]$UseStoredCredentials,

    [switch]$PromptForCredentials,

    [string]$CredentialDirectory = (
        Join-Path $env:LOCALAPPDATA "BoxBrain\credentials"
    ),

    [string]$PackageUrl = (
        "http://10.12.194.1:8788/" +
        "tightvnc-2.8.88-gpl-setup-64bit.msi"
    ),

    [ValidatePattern("^[a-fA-F0-9]{64}$")]
    [string]$PackageSha256 = (
        "fa86d817ac29c5ffe1e8e7095e738d9b" +
        "a5ca28aa62304ac234580916622a8ca2"
    ),

    [ValidatePattern("^10\.12\.194\.[0-9]{1,3}$")]
    [string]$PiAddress = "10.12.194.1",

    [ValidatePattern("^10\.12\.194\.[0-9]{1,3}$")]
    [string]$TargetAddress = "10.12.194.4"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$firewallName = "BoxBrain Morris VNC (Pi USB only)"
$packagePath = Join-Path $env:TEMP "tightvnc-2.8.88-gpl-setup-64bit.msi"
$installedHere = $false
$ruleCreated = $false
$statusPath = "HKLM:\SOFTWARE\BoxBrain"

function Set-MorrisVncStatus {
    param(
        [Parameter(Mandatory)][string]$Status,
        [string]$Detail = ""
    )

    New-Item -Path $statusPath -Force | Out-Null
    New-ItemProperty -Path $statusPath -Name "MorrisVncStatus" `
        -Value $Status -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $statusPath -Name "MorrisVncDetail" `
        -Value $Detail -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $statusPath -Name "MorrisVncUpdatedUtc" `
        -Value ([DateTime]::UtcNow.ToString("o")) -PropertyType String -Force |
        Out-Null
}

function Test-ExpectedPackageUrl {
    param([Parameter(Mandatory)][string]$Url)

    $parsed = [Uri]$Url
    return (
        $parsed.Scheme -eq "http" -and
        $parsed.Host -eq $PiAddress -and
        $parsed.Port -eq 8788 -and
        $parsed.AbsolutePath -eq "/tightvnc-2.8.88-gpl-setup-64bit.msi"
    )
}

try {
    Set-MorrisVncStatus -Status "starting"
    if ($UseStoredCredentials -and $PromptForCredentials) {
        throw "Choose either stored credentials or a secure prompt."
    }
    if (
        ($UseStoredCredentials -or $PromptForCredentials) -and
        ($VncPassword -or $ControlPassword)
    ) {
        throw "Do not combine protected and command-line VNC credentials."
    }
    $vncCredentialPath = Join-Path $CredentialDirectory "morris-vnc.clixml"
    $controlCredentialPath = Join-Path `
        $CredentialDirectory "morris-vnc-control.clixml"
    if ($PromptForCredentials) {
        Set-MorrisVncStatus -Status "awaiting_credentials"
        $vncSecure = Read-Host "VNC password" -AsSecureString
        $controlSecure = Read-Host "Control password" -AsSecureString
        New-Item -ItemType Directory -Path $CredentialDirectory -Force |
            Out-Null
        [PSCredential]::new("MorrisVnc", $vncSecure) |
            Export-Clixml -LiteralPath $vncCredentialPath
        [PSCredential]::new("MorrisVncControl", $controlSecure) |
            Export-Clixml -LiteralPath $controlCredentialPath
        $VncPassword = [PSCredential]::new("MorrisVnc", $vncSecure).
            GetNetworkCredential().Password
        $ControlPassword = [PSCredential]::new(
            "MorrisVncControl", $controlSecure
        ).GetNetworkCredential().Password
    }
    elseif ($UseStoredCredentials) {
        if (
            -not (Test-Path -LiteralPath $vncCredentialPath -PathType Leaf) -or
            -not (Test-Path -LiteralPath $controlCredentialPath -PathType Leaf)
        ) {
            throw "The DPAPI-protected Morris VNC credentials are missing."
        }
        $VncPassword = (Import-Clixml -LiteralPath $vncCredentialPath).
            GetNetworkCredential().Password
        $ControlPassword = (Import-Clixml -LiteralPath $controlCredentialPath).
            GetNetworkCredential().Password
    }
    if (
        $VncPassword -notmatch "^[A-Za-z0-9]{8}$" -or
        $ControlPassword -notmatch "^[A-Za-z0-9]{8}$"
    ) {
        throw "Morris VNC credentials must be eight alphanumeric characters."
    }
    Set-MorrisVncStatus -Status "credentials_ready"
    if (-not (Test-ExpectedPackageUrl -Url $PackageUrl)) {
        throw "PackageUrl must be the pinned Pi USB onboarding URL."
    }
    if (Get-Service -Name "tvnserver" -ErrorAction SilentlyContinue) {
        throw "TightVNC Server already exists; refusing to overwrite it."
    }
    if (Get-NetFirewallRule -DisplayName $firewallName -ErrorAction SilentlyContinue) {
        throw "The BoxBrain Morris VNC firewall rule already exists."
    }

    Invoke-WebRequest -UseBasicParsing -Uri $PackageUrl -OutFile $packagePath
    Set-MorrisVncStatus -Status "package_downloaded"
    $actualHash = (Get-FileHash -LiteralPath $packagePath -Algorithm SHA256).Hash
    if ($actualHash -ne $PackageSha256) {
        throw "The TightVNC package SHA-256 does not match the pinned value."
    }

    $signature = Get-AuthenticodeSignature -LiteralPath $packagePath
    if (
        $signature.Status -ne [Management.Automation.SignatureStatus]::Valid -or
        $null -eq $signature.SignerCertificate -or
        $signature.SignerCertificate.Subject -notmatch '(^|, )O=OOO GlavSoft(,|$)'
    ) {
        throw "The TightVNC package signature is not valid for OOO GlavSoft."
    }
    Set-MorrisVncStatus -Status "package_verified"

    $arguments = @(
        "/i", $packagePath,
        "/qn", "/norestart",
        "ADDLOCAL=Server",
        "SERVER_REGISTER_AS_SERVICE=1",
        "SERVER_ADD_FIREWALL_EXCEPTION=0",
        "SERVER_ALLOW_SAS=1",
        "SET_USEVNCAUTHENTICATION=1",
        "VALUE_OF_USEVNCAUTHENTICATION=1",
        "SET_PASSWORD=1",
        "VALUE_OF_PASSWORD=$VncPassword",
        "SET_USECONTROLAUTHENTICATION=1",
        "VALUE_OF_USECONTROLAUTHENTICATION=1",
        "SET_CONTROLPASSWORD=1",
        "VALUE_OF_CONTROLPASSWORD=$ControlPassword"
    )
    $installer = Start-Process -FilePath "msiexec.exe" -ArgumentList $arguments `
        -Wait -PassThru -WindowStyle Hidden
    if ($installer.ExitCode -notin 0, 3010) {
        throw "TightVNC Server installation failed with code $($installer.ExitCode)."
    }
    $installedHere = $true
    Set-MorrisVncStatus -Status "server_installed"

    New-NetFirewallRule `
        -DisplayName $firewallName `
        -Direction Inbound `
        -Action Allow `
        -Protocol TCP `
        -LocalAddress $TargetAddress `
        -RemoteAddress $PiAddress `
        -LocalPort 5900 `
        -Profile Any | Out-Null
    $ruleCreated = $true

    Set-Service -Name "tvnserver" -StartupType Automatic
    Start-Service -Name "tvnserver"
    $service = Get-Service -Name "tvnserver"
    if ($service.Status -ne "Running") {
        throw "TightVNC Server did not reach the running state."
    }
    $listener = Get-NetTCPConnection -State Listen -LocalPort 5900 `
        -ErrorAction SilentlyContinue
    if ($null -eq $listener) {
        throw "TightVNC Server is running but port 5900 is not listening."
    }

    Set-MorrisVncStatus -Status "ready"
    Write-Output "MORRIS_VNC_READY address=$TargetAddress port=5900"
}
catch {
    $failureDetail = $_.Exception.Message
    if ($ruleCreated) {
        Remove-NetFirewallRule -DisplayName $firewallName -ErrorAction SilentlyContinue
    }
    if ($installedHere) {
        Start-Process -FilePath "msiexec.exe" `
            -ArgumentList @("/x", $packagePath, "/qn", "/norestart") `
            -Wait -WindowStyle Hidden | Out-Null
    }
    Set-MorrisVncStatus -Status "failed" -Detail $failureDetail
    throw
}
finally {
    Remove-Item -LiteralPath $packagePath -Force -ErrorAction SilentlyContinue
}
