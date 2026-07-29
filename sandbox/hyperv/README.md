# BoxBrain Hyper-V Windows lab

This directory defines the disposable full Windows target used by the
BoxBrain Raspberry Pi edge agent and the BrainConnect observation boundary.
It replaces Windows Sandbox only for tests that require a distinct RDP
listener, durable target identity, or a restorable desktop.

The lab is deliberately separate from the workstation:

- Generation 2 Hyper-V VM with Secure Boot and virtual TPM
- dynamic memory from 1–4 GiB, starting at 2 GiB
- two virtual processors
- 64 GiB dynamically expanding system disk
- no automatic start and no automatic checkpoints
- one external virtual switch bound only to the Raspberry Pi USB-C adapter
- no personal accounts, files, provider credentials, or browser sessions

## Prerequisites

- Windows Pro or Enterprise with Hyper-V enabled
- an elevated Windows PowerShell session
- the Pi connected through its USB-C gadget link
- exactly one active adapter reported as
  `Raspberry Pi USB Remote NDIS Network Device`
- the official Windows 11 Enterprise evaluation ISO
- the ISO SHA-256 independently obtained from Microsoft's hash document

The pinned media is the English (United States) Windows 11 Enterprise,
version 25H2, x64 evaluation:

- [Microsoft Evaluation Center](https://www.microsoft.com/en-us/evalcenter/download-windows-11-enterprise)
- [Microsoft hash document](https://aka.ms/Win11-Hash-PDF)
- SHA-256:
  `A61ADEAB895EF5A4DB436E0A7011C92A2FF17BB0357F58B13BBC4062E535E7B9`

The setup refuses to create or replace a VM when the media hash, adapter,
switch, or existing VM state is ambiguous.

Inspect and record the ISO edition metadata before installation:

```powershell
.\sandbox\hyperv\Get-BoxBrainWindowsMediaInfo.ps1
```

## Create the powered-off VM

From the BoxBrain repository root in elevated Windows PowerShell:

```powershell
.\sandbox\hyperv\New-BoxBrainWindowsLab.ps1
```

Creating the external switch may briefly interrupt the workstation's direct
connection to `10.12.194.1`. `AllowManagementOS` remains enabled so Windows
and the VM can both receive addresses from the Pi.

The script validates the ISO before making Hyper-V changes, creates the VM
powered off, and records a non-secret definition at:

```text
C:\VMs\BoxBrain-Windows-Lab\vm-definition.json
```

Run the read-only validator before first boot:

```powershell
.\sandbox\hyperv\Test-BoxBrainWindowsLab.ps1
```

Create the lab-only account and unattended setup media without printing its
generated password:

```powershell
.\sandbox\hyperv\New-BoxBrainUnattendMedia.ps1
```

The generated credential is encrypted to the current Windows user with DPAPI
at `C:\VMs\BoxBrain-Windows-Lab\secrets\lab-credential.clixml`. The temporary
plaintext XML is removed after the answer ISO is created. The answer ISO still
contains the one-time setup password and must be ejected and removed after
installation.

Attach that answer ISO and start the VM from elevated Windows PowerShell:

```powershell
.\sandbox\hyperv\Mount-BoxBrainUnattendMedia.ps1
.\sandbox\hyperv\Grant-BoxBrainVmConsole.ps1
.\sandbox\hyperv\Start-BoxBrainWindowsLab.ps1
```

The console grant applies only to this VM. It does not add the workstation
user to the persistent `Hyper-V Administrators` group.

## Reliable offline installation

Generation 2 Windows media can stop at the short UEFI "press any key" window.
For a new blank VM disk, the preferred repeatable path is to apply the verified
Windows image directly to that exact VHD:

```powershell
.\sandbox\hyperv\Install-BoxBrainWindowsLabOffline.ps1
```

The installer refuses host boot/system disks, non-blank disks, unexpected VHD
paths, unexpected capacities, running VMs, and unverified media locations. It
creates the EFI, Microsoft reserved, and Windows volumes only in
`C:\VMs\BoxBrain-Windows-Lab\disks\BoxBrain-Windows-Lab.vhdx`, stages the
answer file under the guest's Panther directory, makes the VHD first in the
boot order, and ejects both ISOs.

If the host cannot reserve the normal 2 GiB startup allocation, keep dynamic
memory enabled and lower only the startup/minimum allocation:

```powershell
.\sandbox\hyperv\Set-BoxBrainWindowsLabMemory.ps1
```

The VM may then grow to its unchanged 4 GiB ceiling as host memory permits.
Do not close user applications or increase VM priority automatically.

Use these read-only helpers to inspect the runtime and offline disk:

```powershell
.\sandbox\hyperv\Get-BoxBrainWindowsLabStatus.ps1
.\sandbox\hyperv\Get-BoxBrainWindowsDiskLayout.ps1
```

## Installation and checkpoint gate

1. Start the VM only after the definition validator passes.
2. The unattended setup wipes only the VM's only virtual disk and installs the
   exact media image recorded in `media-info.json`.
3. Use a local lab-only account; do not sign in with a personal or work
   Microsoft account.
4. Do not copy the Pi API token, browser sessions, SSH private keys, or
   personal files into the VM.
5. Setup enables RDP with NLA and runs the reviewed BoxBrain Windows link
   script from `http://10.12.194.1:8788/` with explicit authorization.
6. Confirm the Pi sees the VM over its dedicated USB network.
7. Shut the VM down and create a named clean checkpoint before observation or
   input experiments.

The generated answer media contains a one-time lab password. Keep the ISO
detached after installation and do not copy the encrypted host credential into
the VM or repository.

If the first desktop login command does not finish, run the reviewed onboarding
script through Hyper-V PowerShell Direct. The served script hash is
environment-specific because the Pi injects its generated public key, so
inspect the served script and pass its independently recorded SHA-256:

```powershell
.\sandbox\hyperv\Invoke-BoxBrainWindowsGuestProvisioning.ps1 `
    -ExpectedScriptSha256 '<reviewed-served-script-sha256>'
```

Then run the independent guest verifier:

```powershell
.\sandbox\hyperv\Test-BoxBrainWindowsGuest.ps1
```

It checks the Windows edition and computer name, Pi-only address, RDP service
and firewall, OpenSSH service, restricted link account, and non-administrator
boundary without printing the lab credential.

Before registering the RDP target in BrainConnect, independently record the
certificate bound to the guest listener:

```powershell
.\sandbox\hyperv\Get-BoxBrainWindowsRdpIdentity.ps1
```

The script uses Hyper-V PowerShell Direct and the encrypted host credential to
read the guest certificate store. It writes the SHA-256 identity and
non-secret certificate metadata to
`C:\VMs\BoxBrain-Windows-Lab\rdp-certificate-identity.json`; it does not use
the BrainConnect target registry or certificate-probe helper.

After the Pi reports the target connected and a read-only diagnostic succeeds,
create the clean powered-off baseline:

```powershell
.\sandbox\hyperv\New-BoxBrainWindowsCleanCheckpoint.ps1
```

The checkpoint script requests a graceful guest shutdown and never uses
`-TurnOff` or forced shutdown. It refuses to replace an existing checkpoint.

After a bounded experiment, restore the exact clean checkpoint from an
elevated Windows PowerShell session:

```powershell
.\sandbox\hyperv\Restore-BoxBrainWindowsLabCheckpoint.ps1 `
    -GrantCurrentUserAccess
```

The script resolves exactly one VM and one named checkpoint before changing
state, supports PowerShell `-WhatIf`, requires an elevated administrator
session, and records the restored checkpoint ID in
`C:\VMs\BoxBrain-Windows-Lab\restore-status.json`. The optional access switch
adds the current Windows account to the built-in **Hyper-V Administrators**
group so later VM checks do not require elevation. A new Windows sign-in is
required before that non-elevated membership appears in the user's token.

Collect read-only session, owner, lock, single-session-policy, and recent
Terminal Services event evidence with:

```powershell
.\sandbox\hyperv\Get-BoxBrainWindowsRdpSessions.ps1
```

The script uses the existing encrypted lab credential through Hyper-V
PowerShell Direct and writes only non-secret diagnostic evidence to
`C:\VMs\BoxBrain-Windows-Lab\rdp-session-diagnostic.json`. It does not change
Windows session or RDP policy.

The full installation, link, and checkpoint must be recorded in the current
BoxBrain session handoff. Removal is intentionally not automated by this
directory; deleting the VM, switch, disk, checkpoint, or media requires a
separate explicit operator request and exact-target verification.
