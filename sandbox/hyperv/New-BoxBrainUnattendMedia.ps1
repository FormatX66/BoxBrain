[CmdletBinding()]
param(
    [string]$LabRoot = 'C:\VMs\BoxBrain-Windows-Lab',
    [string]$ImageName = 'Windows 11 Enterprise Evaluation',
    [string]$ComputerName = 'BB-WIN-LAB',
    [string]$LabUserName = 'boxbrain-lab',
    [string]$PiOnboardingUrl = 'http://10.12.194.1:8788/windows-link.ps1'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Protect-PathForCurrentUser {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][ValidateSet('Container', 'Leaf')][string]$Type
    )

    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $system = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
    $administrators = [Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
    if ($Type -eq 'Container') {
        $acl = [Security.AccessControl.DirectorySecurity]::new()
        $inheritance = 'ContainerInherit,ObjectInherit'
    } else {
        $acl = [Security.AccessControl.FileSecurity]::new()
        $inheritance = 'None'
    }
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($sid in @($currentUser, $system, $administrators)) {
        $rule = [Security.AccessControl.FileSystemAccessRule]::new(
            $sid,
            'FullControl',
            $inheritance,
            'None',
            'Allow'
        )
        [void]$acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $Path -AclObject $acl
}

$LabRoot = [IO.Path]::GetFullPath($LabRoot).TrimEnd('\')
if ($LabRoot.Length -lt 10 -or $LabRoot -eq [IO.Path]::GetPathRoot($LabRoot).TrimEnd('\')) {
    throw "Refusing unsafe lab root: $LabRoot"
}
if ($ComputerName -notmatch '^[A-Za-z0-9-]{1,15}$') {
    throw 'ComputerName must contain 1-15 letters, numbers, or hyphens.'
}
if ($LabUserName -notmatch '^[A-Za-z0-9._-]{1,20}$') {
    throw 'LabUserName contains unsupported characters.'
}
$piUri = [Uri]$PiOnboardingUrl
if (
    $piUri.Scheme -cne 'http' -or
    $piUri.Host -cne '10.12.194.1' -or
    $piUri.Port -ne 8788 -or
    $piUri.AbsolutePath -cne '/windows-link.ps1'
) {
    throw 'PiOnboardingUrl must be the fixed BoxBrain USB onboarding endpoint.'
}

$mediaRoot = Join-Path $LabRoot 'media'
$secretsRoot = Join-Path $LabRoot 'secrets'
$stagingRoot = Join-Path $LabRoot 'staging'
$toolsRoot = Join-Path $LabRoot 'tools\iso-builder'
$answerIso = Join-Path $mediaRoot 'BoxBrain-Autounattend.iso'
$credentialPath = Join-Path $secretsRoot 'lab-credential.clixml'
$metadataPath = Join-Path $LabRoot 'unattend-media.json'
$answerXml = Join-Path $stagingRoot 'Autounattend.xml'

foreach ($path in @($answerIso, $credentialPath, $metadataPath)) {
    if (Test-Path -LiteralPath $path) {
        throw "Refusing to replace existing lab artifact: $path"
    }
}

New-Item -ItemType Directory -Path $mediaRoot, $secretsRoot, $stagingRoot -Force | Out-Null
Protect-PathForCurrentUser -Path $secretsRoot -Type Container

$randomBytes = [byte[]]::new(36)
$generator = [Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $generator.GetBytes($randomBytes)
} finally {
    $generator.Dispose()
}
$plainPassword = 'Bb1!' + [Convert]::ToBase64String($randomBytes)
$securePassword = ConvertTo-SecureString $plainPassword -AsPlainText -Force
$credential = [Management.Automation.PSCredential]::new($LabUserName, $securePassword)
$credential | Export-Clixml -LiteralPath $credentialPath
Protect-PathForCurrentUser -Path $credentialPath -Type Leaf

$escapedPassword = [Security.SecurityElement]::Escape($plainPassword)
$escapedImageName = [Security.SecurityElement]::Escape($ImageName)
$escapedComputerName = [Security.SecurityElement]::Escape($ComputerName)
$escapedLabUserName = [Security.SecurityElement]::Escape($LabUserName)
$escapedPiUrl = [Security.SecurityElement]::Escape($PiOnboardingUrl)

$template = @'
<?xml version="1.0" encoding="utf-8"?>
<unattend xmlns="urn:schemas-microsoft-com:unattend">
  <settings pass="windowsPE">
    <component name="Microsoft-Windows-International-Core-WinPE" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">
      <SetupUILanguage>
        <UILanguage>en-US</UILanguage>
      </SetupUILanguage>
      <InputLocale>en-US</InputLocale>
      <SystemLocale>en-US</SystemLocale>
      <UILanguage>en-US</UILanguage>
      <UserLocale>en-US</UserLocale>
    </component>
    <component name="Microsoft-Windows-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">
      <DiskConfiguration>
        <Disk wcm:action="add">
          <DiskID>0</DiskID>
          <WillWipeDisk>true</WillWipeDisk>
          <CreatePartitions>
            <CreatePartition wcm:action="add">
              <Order>1</Order>
              <Type>EFI</Type>
              <Size>260</Size>
            </CreatePartition>
            <CreatePartition wcm:action="add">
              <Order>2</Order>
              <Type>MSR</Type>
              <Size>16</Size>
            </CreatePartition>
            <CreatePartition wcm:action="add">
              <Order>3</Order>
              <Type>Primary</Type>
              <Extend>true</Extend>
            </CreatePartition>
          </CreatePartitions>
          <ModifyPartitions>
            <ModifyPartition wcm:action="add">
              <Order>1</Order>
              <PartitionID>1</PartitionID>
              <Format>FAT32</Format>
              <Label>System</Label>
            </ModifyPartition>
            <ModifyPartition wcm:action="add">
              <Order>2</Order>
              <PartitionID>3</PartitionID>
              <Format>NTFS</Format>
              <Label>Windows</Label>
              <Letter>C</Letter>
            </ModifyPartition>
          </ModifyPartitions>
        </Disk>
        <WillShowUI>OnError</WillShowUI>
      </DiskConfiguration>
      <ImageInstall>
        <OSImage>
          <InstallFrom>
            <MetaData wcm:action="add">
              <Key>/IMAGE/NAME</Key>
              <Value>__IMAGE_NAME__</Value>
            </MetaData>
          </InstallFrom>
          <InstallTo>
            <DiskID>0</DiskID>
            <PartitionID>3</PartitionID>
          </InstallTo>
          <WillShowUI>OnError</WillShowUI>
        </OSImage>
      </ImageInstall>
      <UserData>
        <AcceptEula>true</AcceptEula>
        <FullName>BoxBrain Lab</FullName>
        <Organization>BoxBrain</Organization>
      </UserData>
    </component>
  </settings>
  <settings pass="specialize">
    <component name="Microsoft-Windows-Shell-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
      <ComputerName>__COMPUTER_NAME__</ComputerName>
      <RegisteredOwner>BoxBrain Lab</RegisteredOwner>
      <RegisteredOrganization>BoxBrain</RegisteredOrganization>
      <TimeZone>Eastern Standard Time</TimeZone>
    </component>
    <component name="Microsoft-Windows-TerminalServices-LocalSessionManager" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
      <fDenyTSConnections>false</fDenyTSConnections>
    </component>
    <component name="Microsoft-Windows-TerminalServices-RDP-WinStationExtensions" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
      <UserAuthentication>1</UserAuthentication>
    </component>
  </settings>
  <settings pass="oobeSystem">
    <component name="Microsoft-Windows-International-Core" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
      <InputLocale>en-US</InputLocale>
      <SystemLocale>en-US</SystemLocale>
      <UILanguage>en-US</UILanguage>
      <UserLocale>en-US</UserLocale>
    </component>
    <component name="Microsoft-Windows-Shell-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
      <OOBE>
        <HideEULAPage>true</HideEULAPage>
        <HideLocalAccountScreen>true</HideLocalAccountScreen>
        <HideOnlineAccountScreens>true</HideOnlineAccountScreens>
        <HideWirelessSetupInOOBE>true</HideWirelessSetupInOOBE>
        <NetworkLocation>Work</NetworkLocation>
        <ProtectYourPC>3</ProtectYourPC>
      </OOBE>
      <UserAccounts>
        <LocalAccounts>
          <LocalAccount wcm:action="add" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">
            <Name>__LAB_USER__</Name>
            <DisplayName>BoxBrain Lab</DisplayName>
            <Group>Administrators</Group>
            <Password>
              <Value>__PASSWORD__</Value>
              <PlainText>true</PlainText>
            </Password>
          </LocalAccount>
        </LocalAccounts>
      </UserAccounts>
      <AutoLogon>
        <Enabled>true</Enabled>
        <LogonCount>1</LogonCount>
        <Username>__LAB_USER__</Username>
        <Domain>.</Domain>
        <Password>
          <Value>__PASSWORD__</Value>
          <PlainText>true</PlainText>
        </Password>
      </AutoLogon>
      <FirstLogonCommands>
        <SynchronousCommand wcm:action="add" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">
          <Order>1</Order>
          <Description>Provision BoxBrain lab boundary</Description>
          <RequiresUserInput>false</RequiresUserInput>
          <CommandLine>powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server' -Name fDenyTSConnections -Value 0; Enable-NetFirewallRule -DisplayGroup 'Remote Desktop'; New-Item -ItemType Directory -Path 'C:\ProgramData\BoxBrain' -Force | Out-Null; $link='C:\Windows\Temp\boxbrain-link.ps1'; Invoke-WebRequest -UseBasicParsing '__PI_URL__' -OutFile $link; &amp; $link -Authorized -BoxBrainAddress '10.12.194.1'; 'complete' | Set-Content -Path 'C:\ProgramData\BoxBrain\provisioned.ok' -Encoding ASCII"</CommandLine>
        </SynchronousCommand>
      </FirstLogonCommands>
    </component>
  </settings>
</unattend>
'@

$xml = $template.
    Replace('__IMAGE_NAME__', $escapedImageName).
    Replace('__COMPUTER_NAME__', $escapedComputerName).
    Replace('__LAB_USER__', $escapedLabUserName).
    Replace('__PASSWORD__', $escapedPassword).
    Replace('__PI_URL__', $escapedPiUrl)

try {
    [xml]$parsed = $xml
    $parsed.Save($answerXml)

    $venvPython = Join-Path $toolsRoot 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        $systemPython = (Get-Command python.exe -ErrorAction Stop).Source
        & $systemPython -m venv $toolsRoot
        if ($LASTEXITCODE -ne 0) {
            throw 'Failed to create the isolated ISO-builder Python environment.'
        }
    }

    $requirements = Join-Path $PSScriptRoot 'requirements.lock'
    & $venvPython -m pip install `
        --disable-pip-version-check `
        --require-hashes `
        --no-deps `
        --requirement $requirements
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to install the pinned ISO-builder dependency.'
    }

    $builder = Join-Path $PSScriptRoot 'build_answer_iso.py'
    & $venvPython $builder --source $answerXml --output $answerIso
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to build the BoxBrain answer ISO.'
    }
} finally {
    $plainPassword = $null
    $xml = $null
    if (Test-Path -LiteralPath $answerXml -PathType Leaf) {
        Remove-Item -LiteralPath $answerXml -Force
    }
}

$metadata = [ordered]@{
    created_at = (Get-Date).ToUniversalTime().ToString('o')
    answer_iso = $answerIso
    answer_iso_sha256 = (Get-FileHash -LiteralPath $answerIso -Algorithm SHA256).Hash.ToLowerInvariant()
    image_name = $ImageName
    computer_name = $ComputerName
    lab_user_name = $LabUserName
    credential_path = $credentialPath
    credential_protection = 'Windows DPAPI current user'
    pi_onboarding_url = $PiOnboardingUrl
    plaintext_staging_removed = -not (Test-Path -LiteralPath $answerXml)
}
$metadata | ConvertTo-Json | Set-Content -LiteralPath $metadataPath -Encoding UTF8
$metadata | ConvertTo-Json
Write-Host '[ready] Unattended installation media created without printing the lab password.'
