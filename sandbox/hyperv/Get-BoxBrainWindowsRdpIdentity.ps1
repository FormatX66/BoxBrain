[CmdletBinding()]
param(
    [string]$VmName = 'BoxBrain-Windows-Lab',
    [string]$CredentialPath = 'C:\VMs\BoxBrain-Windows-Lab\secrets\lab-credential.clixml',
    [string]$OutputPath = 'C:\VMs\BoxBrain-Windows-Lab\rdp-certificate-identity.json'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an elevated Windows PowerShell session.'
}

Import-Module Hyper-V -ErrorAction Stop
$vm = Get-VM -Name $VmName -ErrorAction Stop
if ($vm.State -ne 'Running') {
    throw "VM must be running to read its RDP identity; current state is $($vm.State)."
}
if (-not (Test-Path -LiteralPath $CredentialPath -PathType Leaf)) {
    throw "Encrypted lab credential not found: $CredentialPath"
}

$credential = Import-Clixml -LiteralPath $CredentialPath
if ($credential -isnot [Management.Automation.PSCredential]) {
    throw 'Encrypted lab credential file did not contain a PSCredential.'
}

$outputDirectory = Split-Path -Parent $OutputPath
if (-not (Test-Path -LiteralPath $outputDirectory -PathType Container)) {
    New-Item -ItemType Directory -Path $outputDirectory | Out-Null
}

$session = $null
try {
    $session = New-PSSession -VMName $VmName -Credential $credential -ErrorAction Stop
    $guestIdentity = Invoke-Command -Session $session -ScriptBlock {
        $listener = Get-CimInstance `
            -Namespace 'root/cimv2/TerminalServices' `
            -ClassName Win32_TSGeneralSetting `
            -Filter "TerminalName='RDP-tcp'" `
            -ErrorAction Stop
        $listenerThumbprint = (
            [string]$listener.SSLCertificateSHA1Hash
        ).Replace(' ', '').ToUpperInvariant()

        $certificates = @(
            Get-ChildItem -Path 'Cert:\LocalMachine\Remote Desktop' |
                Where-Object HasPrivateKey
        )
        $certificate = if ($listenerThumbprint) {
            @(
                $certificates |
                    Where-Object {
                        $_.Thumbprint.Replace(' ', '').ToUpperInvariant() -eq
                            $listenerThumbprint
                    }
            )
        }
        else {
            @(
                $certificates |
                    Where-Object {
                        $_.NotBefore -le (Get-Date) -and
                        $_.NotAfter -gt (Get-Date)
                    }
            )
        }
        if ($certificate.Count -ne 1) {
            throw (
                'Expected exactly one active RDP certificate; found ' +
                $certificate.Count + '.'
            )
        }

        $sha256 = [Security.Cryptography.SHA256]::Create()
        try {
            $certificateSha256 = (
                [BitConverter]::ToString(
                    $sha256.ComputeHash($certificate[0].RawData)
                )
            ).Replace('-', '').ToLowerInvariant()
        }
        finally {
            $sha256.Dispose()
        }

        [ordered]@{
            computer_name = $env:COMPUTERNAME
            transport = 'rdp'
            port = 3389
            certificate_sha256 = $certificateSha256
            certificate_sha1 = (
                $certificate[0].Thumbprint.Replace(' ', '').ToLowerInvariant()
            )
            subject = $certificate[0].Subject
            issuer = $certificate[0].Issuer
            valid_from = $certificate[0].NotBefore.ToUniversalTime().ToString('o')
            valid_to = $certificate[0].NotAfter.ToUniversalTime().ToString('o')
            listener_binding_explicit = [bool]$listenerThumbprint
            source = 'guest certificate store via Hyper-V PowerShell Direct'
        }
    }

    $result = [ordered]@{
        recorded_at = (Get-Date).ToUniversalTime().ToString('o')
        vm_name = $VmName
        state = 'complete'
        identity = $guestIdentity
    }
    $resultJson = $result | ConvertTo-Json -Depth 5
    $resultJson | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    $resultJson
}
catch {
    $result = [ordered]@{
        recorded_at = (Get-Date).ToUniversalTime().ToString('o')
        vm_name = $VmName
        state = 'unavailable'
        error = $_.Exception.Message
    }
    $resultJson = $result | ConvertTo-Json
    $resultJson | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    $resultJson
    throw
}
finally {
    if ($session) {
        Remove-PSSession -Session $session -ErrorAction SilentlyContinue
    }
}
