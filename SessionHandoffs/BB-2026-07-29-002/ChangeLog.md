# Change Log

## Hyper-V Windows lab

### Changed files

- `sandbox/hyperv/README.md`
- `sandbox/hyperv/New-BoxBrainWindowsLab.ps1`
- `sandbox/hyperv/Test-BoxBrainWindowsLab.ps1`
- `sandbox/hyperv/Get-BoxBrainWindowsMediaInfo.ps1`
- `sandbox/hyperv/New-BoxBrainUnattendMedia.ps1`
- `sandbox/hyperv/Mount-BoxBrainUnattendMedia.ps1`
- `sandbox/hyperv/Grant-BoxBrainVmConsole.ps1`
- `sandbox/hyperv/Start-BoxBrainWindowsLab.ps1`
- `sandbox/hyperv/Get-BoxBrainWindowsLabStatus.ps1`
- `sandbox/hyperv/Get-BoxBrainWindowsDiskLayout.ps1`
- `sandbox/hyperv/Install-BoxBrainWindowsLabOffline.ps1`
- `sandbox/hyperv/Set-BoxBrainWindowsLabMemory.ps1`
- `sandbox/hyperv/Invoke-BoxBrainWindowsGuestProvisioning.ps1`
- `sandbox/hyperv/Test-BoxBrainWindowsGuest.ps1`
- `sandbox/hyperv/New-BoxBrainWindowsCleanCheckpoint.ps1`
- `sandbox/hyperv/build_answer_iso.py`
- `sandbox/hyperv/requirements.lock`

### Reason

Provide a reproducible, guarded, disposable full Windows target with verified
media, Pi-only networking, encrypted host credential storage, direct VHD
installation, independent guest verification, and clean checkpoint creation.

### Dependencies

- Windows Hyper-V
- Official Windows 11 Enterprise Evaluation 25H2 media
- Python and pinned `pycdlib` for the answer ISO
- Raspberry Pi USB adapter and onboarding endpoint

### Future implications

The target can now support certificate-pinned RDP and later observation-only
frame tests. Removal remains intentionally unimplemented and requires a
separate explicit request.

## Pi Windows onboarding

### Changed files

- `edge/kali-pi-agent/onboarding/windows-link.ps1`
- `edge/kali-pi-agent/tests/test_core.py`

### Reason

Preserve an array when exactly one Pi address is allowed so strict mode can
evaluate `.Count`.

### Dependencies

- Existing generated Pi target public key
- USB-only onboarding service at `10.12.194.1:8788`

### Future implications

Single-address onboarding is repeatable and remains compatible with multiple
private addresses when explicitly configured.

## Bounded target diagnostics

### Changed files

- `edge/kali-pi-agent/src/boxbrain/diagnostics.py`
- `edge/kali-pi-agent/tests/test_core.py`

### Reason

Prevent a slow Windows device inventory from consuming the diagnostic's full
outer SSH timeout.

### Dependencies

- PowerShell job support in the restricted Windows account
- Existing 90-second Pi SSH diagnostic deadline

### Future implications

Reports now distinguish a timed-out device scan from a completed zero-error
scan while still returning other bounded system evidence.

## TestClient migration

### Changed files

- `controller/pyproject.toml`

### Reason

Use Starlette's supported `httpx2` TestClient transport instead of the
deprecated `httpx` compatibility fallback.

### Dependencies

- `httpx2>=2.9,<3`
- Starlette TestClient

### Future implications

Backend tests no longer emit the upstream TestClient migration warning. The
runtime OpenAI/MCP dependency may still use original `httpx` independently.

## Repository validator

### Changed files

- `Admin/validate_repository.py`
- `Admin/tests/test_validate_repository.py`

### Reason

Exclude generated and ignored directories such as `.venv`, `.pytest_cache`,
`.dart_tool`, and `build` from canonical Markdown discovery.

### Dependencies

- Python standard library
- Repository `.gitignore` conventions

### Future implications

Installing local development dependencies no longer creates false broken-link
or orphan-document failures. A regression check covers the generated-directory
boundary.

## Canonical knowledge records

### Changed files

- `README.md`
- `Admin/SessionIndex.md`
- `Admin/Decisions.md`
- `Admin/ChangeLog.md`
- `Admin/Roadmap.md`
- `Admin/MasterTODO.md`
- `Architecture/SystemArchitecture.md`
- `Architecture/Integrations.md`
- `Projects/BrainConnect/ProjectIndex.md`
- `SessionHandoffs/README.md`
- `SessionHandoffs/BB-2026-07-29-002/*`

### Reason

Make the Windows target, decisions, evidence, remaining risks, and next
execution boundary discoverable without duplicating BrainConnect
implementation documentation.

### Future implications

The next session can begin from the clean checkpoint and existing certificate
gate instead of repeating VM or Pi onboarding work.
