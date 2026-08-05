#Requires -Version 5.1
#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern("^[A-Za-z0-9]{8}$")]
    [string]$VncPassword,

    [Parameter(Mandatory)]
    [ValidatePattern("^[A-Za-z0-9]{8}$")]
    [string]$ControlPassword,

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

    Write-Output "MORRIS_VNC_READY address=$TargetAddress port=5900"
}
catch {
    if ($ruleCreated) {
        Remove-NetFirewallRule -DisplayName $firewallName -ErrorAction SilentlyContinue
    }
    if ($installedHere) {
        Start-Process -FilePath "msiexec.exe" `
            -ArgumentList @("/x", $packagePath, "/qn", "/norestart") `
            -Wait -WindowStyle Hidden | Out-Null
    }
    throw
}
finally {
    Remove-Item -LiteralPath $packagePath -Force -ErrorAction SilentlyContinue
}
