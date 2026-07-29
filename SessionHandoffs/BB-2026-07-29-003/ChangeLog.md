# Change Log

## Independent RDP identity

### Changed files

- `sandbox/hyperv/Get-BoxBrainWindowsRdpIdentity.ps1`
- `sandbox/hyperv/README.md`

### Reason

Provide a repeatable identity path that reads the active Windows RDP
certificate through Hyper-V PowerShell Direct and never depends on the
BrainConnect registry or probe helper.

### Dependencies

- Running Hyper-V VM `BoxBrain-Windows-Lab`
- Encrypted host credential
- Guest `RDP-tcp` listener and certificate store

### Future implications

Certificate identity can be re-established after checkpoint restoration or
rotation without trust on first use.

## BrainConnect live-target record

### Changed files

- BrainConnect `README.md`
- BrainConnect `docs/ROADMAP.md`
- BrainConnect `docs/SECURITY.md`
- BrainConnect `docs/TARGETS.md`

### Reason

Record that the full disposable Windows target passed independent identity,
disabled registration, no-authentication probe, audit, and explicit enablement
gates.

### Dependencies

- Pi controller and FreeRDP 3.26 helper
- Target `0efb72ab-7b55-481a-914b-f689f427dfef`
- Windows endpoint `10.12.194.9:3389`

### Future implications

The certificate milestone is complete; frame delivery is the next
implementation boundary.

## Pi runtime state

### Changed state

- Registered and enabled one exact Windows target after verification.
- Appended audit sequences 29, 30, and 31.
- Rotated the controller API token after diagnostic-output exposure.
- Restarted and reverified the controller service.

### Reason

Complete the full-target identity gate and revoke a disclosed credential before
further authenticated operations.

### Dependencies

- Private Pi state directory `/var/lib/brainconnect`
- Hardened `brainconnect-controller.service`

### Future implications

The replacement token remains Pi-local. Workstation dashboard provisioning
still requires a separate controlled design.

## Canonical knowledge records

### Changed files

- `Admin/SessionIndex.md`
- `Admin/Decisions.md`
- `Admin/ChangeLog.md`
- `Admin/Roadmap.md`
- `Admin/MasterTODO.md`
- `Architecture/SystemArchitecture.md`
- `Architecture/Integrations.md`
- `Projects/README.md`
- `Projects/BrainConnect/ProjectIndex.md`
- `SessionHandoffs/README.md`
- `SessionHandoffs/BB-2026-07-29-003/*`

### Reason

Make the live identity evidence, security response, completed milestone, and
next frame boundary discoverable from the canonical indexes.

### Future implications

The next session can begin with the versioned frame protocol instead of
repeating target registration or certificate verification.
