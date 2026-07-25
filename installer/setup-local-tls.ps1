#Requires -Version 5.1
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$tlsDirectory = Join-Path $repositoryRoot "controller\data\tls"
$metadataPath = Join-Path $tlsDirectory "metadata.json"
$rootCertificatePath = Join-Path $tlsDirectory "boxbrain-root-ca.cer"
$serverCertificatePath = Join-Path $tlsDirectory "server-cert.pem"
$serverKeyPath = Join-Path $tlsDirectory "server-key.pem"
$rootSubject = "CN=BoxBrain Local Development Root CA"
$serverSubject = "CN=localhost"
$rootFriendlyName = "BoxBrain Local Development Root CA"
$serverFriendlyName = "BoxBrain Localhost HTTPS"
$createdRootThumbprint = $null
$createdServerThumbprint = $null
$trustedRootImported = $false

function Write-PemFile {
    param(
        [Parameter(Mandatory)][byte[]]$Bytes,
        [Parameter(Mandatory)][string]$Label,
        [Parameter(Mandatory)][string]$Path
    )

    $base64 = [Convert]::ToBase64String(
        $Bytes,
        [Base64FormattingOptions]::InsertLineBreaks
    )
    $content = "-----BEGIN $Label-----`r`n$base64`r`n-----END $Label-----`r`n"
    [IO.File]::WriteAllText($Path, $content, (New-Object Text.UTF8Encoding($false)))
}

function Protect-PrivateFile {
    param([Parameter(Mandatory)][string]$Path)

    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $sid = $identity.User.Value
    $acl = New-Object Security.AccessControl.FileSecurity
    $acl.SetSecurityDescriptorSddlForm(
        "D:P(A;;FA;;;$sid)",
        [Security.AccessControl.AccessControlSections]::Access
    )
    [IO.File]::SetAccessControl($Path, $acl)

    $verified = Get-Acl -LiteralPath $Path
    $rules = @($verified.Access)
    if (-not $verified.AreAccessRulesProtected -or $rules.Count -ne 1 -or
        $rules[0].IdentityReference.Value -notin @($identity.Name, $sid) -or
        ($rules[0].FileSystemRights -band
            [Security.AccessControl.FileSystemRights]::FullControl) -ne
            [Security.AccessControl.FileSystemRights]::FullControl) {
        throw "The server private key ACL could not be restricted to the current user."
    }
}

if (Test-Path -LiteralPath $metadataPath) {
    $metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
    $root = Get-Item -LiteralPath "Cert:\CurrentUser\Root\$($metadata.root_thumbprint)" -ErrorAction SilentlyContinue
    $server = Get-Item -LiteralPath "Cert:\CurrentUser\My\$($metadata.server_thumbprint)" -ErrorAction SilentlyContinue
    if ($null -ne $root -and $null -ne $server -and
        (Test-Path -LiteralPath $serverCertificatePath) -and
        (Test-Path -LiteralPath $serverKeyPath)) {
        Protect-PrivateFile -Path $serverKeyPath
        Write-Host "[ready] BoxBrain local HTTPS certificate already exists."
        Write-Host "        Root thumbprint: $($metadata.root_thumbprint)"
        Write-Host "        Server expires: $($metadata.server_not_after)"
        exit 0
    }
    throw "TLS metadata exists, but its certificate or key material is incomplete. Run remove-local-tls.ps1 -ConfirmRemoval first."
}

$untracked = @(
    Get-ChildItem Cert:\CurrentUser\My, Cert:\CurrentUser\Root |
        Where-Object {
            $_.Subject -eq $rootSubject -or $_.FriendlyName -in @(
                $rootFriendlyName,
                $serverFriendlyName
            )
        }
)
if ($untracked.Count -gt 0) {
    throw "Untracked BoxBrain certificates already exist. Remove them manually or restore metadata before setup."
}
if ((Test-Path -LiteralPath $tlsDirectory) -and
    @(Get-ChildItem -LiteralPath $tlsDirectory -Force).Count -gt 0) {
    throw "TLS output directory is not empty and has no metadata: $tlsDirectory"
}
[IO.Directory]::CreateDirectory($tlsDirectory) | Out-Null

try {
    $rootParameters = @{
        Type = "Custom"
        Subject = $rootSubject
        FriendlyName = $rootFriendlyName
        CertStoreLocation = "Cert:\CurrentUser\My"
        Provider = "Microsoft Software Key Storage Provider"
        KeyAlgorithm = "RSA"
        KeyLength = 3072
        HashAlgorithm = "SHA256"
        KeyExportPolicy = "NonExportable"
        KeyUsage = @("CertSign", "CrlSign", "DigitalSignature")
        TextExtension = @("2.5.29.19={critical}{text}ca=true&pathlength=0")
        NotAfter = (Get-Date).AddYears(5)
    }
    $rootCertificate = New-SelfSignedCertificate @rootParameters
    $createdRootThumbprint = $rootCertificate.Thumbprint

    $serverParameters = @{
        Type = "Custom"
        Subject = $serverSubject
        FriendlyName = $serverFriendlyName
        Signer = $rootCertificate
        CertStoreLocation = "Cert:\CurrentUser\My"
        Provider = "Microsoft Software Key Storage Provider"
        KeyAlgorithm = "RSA"
        KeyLength = 2048
        HashAlgorithm = "SHA256"
        KeyExportPolicy = "Exportable"
        KeyUsage = @("DigitalSignature", "KeyEncipherment")
        TextExtension = @(
            "2.5.29.17={text}DNS=localhost&IPAddress=127.0.0.1&IPAddress=::1",
            "2.5.29.37={text}1.3.6.1.5.5.7.3.1",
            "2.5.29.19={critical}{text}ca=false"
        )
        NotAfter = (Get-Date).AddYears(1)
    }
    $serverCertificate = New-SelfSignedCertificate @serverParameters
    $createdServerThumbprint = $serverCertificate.Thumbprint

    Export-Certificate -Cert $rootCertificate -FilePath $rootCertificatePath -Force | Out-Null
    Import-Certificate -FilePath $rootCertificatePath -CertStoreLocation "Cert:\CurrentUser\Root" | Out-Null
    $trustedRootImported = $true

    Write-PemFile -Bytes $serverCertificate.RawData -Label "CERTIFICATE" -Path $serverCertificatePath
    $rsa = [Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($serverCertificate)
    try {
        if ($rsa -isnot [Security.Cryptography.RSACng]) {
            throw "The generated server key is not exportable through Windows CNG."
        }
        $privateKey = $rsa.Key.Export(
            [Security.Cryptography.CngKeyBlobFormat]::Pkcs8PrivateBlob
        )
    }
    finally {
        if ($null -ne $rsa) { $rsa.Dispose() }
    }
    Write-PemFile -Bytes $privateKey -Label "PRIVATE KEY" -Path $serverKeyPath
    Protect-PrivateFile -Path $serverKeyPath

    $chain = New-Object Security.Cryptography.X509Certificates.X509Chain
    $chain.ChainPolicy.RevocationMode = "NoCheck"
    if (-not $chain.Build($serverCertificate)) {
        $reasons = ($chain.ChainStatus | ForEach-Object { $_.StatusInformation.Trim() }) -join "; "
        throw "The generated server certificate did not chain to the trusted root: $reasons"
    }

    $metadata = [ordered]@{
        schema_version = 1
        created_at = (Get-Date).ToUniversalTime().ToString("o")
        root_thumbprint = $rootCertificate.Thumbprint
        root_subject = $rootCertificate.Subject
        root_not_after = $rootCertificate.NotAfter.ToUniversalTime().ToString("o")
        server_thumbprint = $serverCertificate.Thumbprint
        server_subject = $serverCertificate.Subject
        server_not_after = $serverCertificate.NotAfter.ToUniversalTime().ToString("o")
        hosts = @("localhost", "127.0.0.1", "::1")
        certificate_file = "server-cert.pem"
        private_key_file = "server-key.pem"
    }
    $metadata | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $metadataPath -Encoding UTF8

    Write-Host "[created] Trusted Current User BoxBrain development certificate."
    Write-Host "          Root thumbprint: $($rootCertificate.Thumbprint)"
    Write-Host "          Server expires: $($serverCertificate.NotAfter.ToString('u'))"
    Write-Host "          TLS files: $tlsDirectory"
}
catch {
    if ($null -ne $createdServerThumbprint) {
        Remove-Item -LiteralPath "Cert:\CurrentUser\My\$createdServerThumbprint" -Force -ErrorAction SilentlyContinue
    }
    if ($trustedRootImported -and $null -ne $createdRootThumbprint) {
        Remove-Item -LiteralPath "Cert:\CurrentUser\Root\$createdRootThumbprint" -Force -ErrorAction SilentlyContinue
    }
    if ($null -ne $createdRootThumbprint) {
        Remove-Item -LiteralPath "Cert:\CurrentUser\My\$createdRootThumbprint" -Force -ErrorAction SilentlyContinue
    }
    $resolvedTls = [IO.Path]::GetFullPath($tlsDirectory)
    $expectedTls = [IO.Path]::GetFullPath((Join-Path $repositoryRoot "controller\data\tls"))
    if ($resolvedTls -eq $expectedTls -and (Test-Path -LiteralPath $resolvedTls)) {
        Remove-Item -LiteralPath $resolvedTls -Recurse -Force
    }
    throw
}
