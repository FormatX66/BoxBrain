# Agent Handoff

## Current objective

Deploy the authenticated BrainConnect FastAPI controller on the Kali Raspberry
Pi 4 and configure the already-installed certificate helper without enabling
remote input or probing an unapproved Windows endpoint.

## Tasks

1. Inspect the Pi's Python, systemd, network, and existing application paths;
   preserve all unrelated services.
2. Select an isolated application directory and dedicated non-login service
   account, or document why the existing account is required.
3. Package or copy the controller source at an exact BrainConnect revision.
4. Create a dedicated virtual environment and install only pinned controller
   dependencies.
5. Configure the database, API token, audit storage, helper absolute path, and
   bounded helper timeout outside the repository.
6. Run controller tests and a foreground health check before considering a
   service unit.
7. If explicitly authorized, add a hardened systemd unit with no shell,
   minimal filesystem access, restart limits, and localhost-only binding.
8. Verify emergency stop, authentication, durable restart, and helper
   availability without contacting a real RDP target.

## Dependencies

- BrainConnect commit `8a308dc` and the existing stacked branches
- Installed helper and provenance on the Kali Raspberry Pi 4
- Python 3.13 compatibility with the pinned FastAPI controller dependencies
- Existing target registry, emergency stop, and API authentication contracts
- Explicit authorization before creating or enabling a system service

## Files affected

- BrainConnect Pi controller packaging and deployment scripts
- BrainConnect controller runtime configuration examples
- BrainConnect development, architecture, security, and roadmap documentation
- BoxBrain project, decision, change, and session indexes
- Pi application and runtime-data directories after verification

## Required repositories

- `https://github.com/FormatX66/BrainConnect`
- `https://github.com/FormatX66/BoxBrain`

## Verification checklist

- The deployed source revision and package hashes are recorded.
- Controller dependencies install into a dedicated virtual environment.
- API token, SQLite data, logs, and environment files are not stored in Git.
- The controller binds only to the intended interface.
- Helper configuration is exactly
  `/usr/local/libexec/brainconnect/brainconnect-freerdp-probe`.
- Controller health, authentication, emergency stop, durable restart, and
  bounded helper-failure behavior pass.
- No real RDP endpoint, credential, desktop session, frame, input, shell,
  clipboard, file, or device redirection is exercised.
- No systemd unit is created or enabled without explicit authorization.
- BrainConnect and BoxBrain validation passes.

## Suggested commit message

`feat: deploy BrainConnect controller to Raspberry Pi`

## Suggested branch

`feature/brainconnect-pi4-controller`

## Potential risks

- Kali's Python 3.13 may expose dependency compatibility issues.
- Running the controller as `kali` would broaden authority and filesystem
  access; prefer a dedicated account.
- A service unit can accidentally expose the API to the LAN or embed secrets.
- Package upgrades can change FreeRDP from the verified 3.26 runtime; startup
  should detect provenance drift and fail closed.
- The direct USB link may reset during power or gadget-network changes.

## Estimated completion order

1. Read-only Pi controller-host inventory
2. Application layout and service-account decision
3. Source and dependency deployment
4. Foreground controller tests
5. Runtime configuration and local health check
6. Optional systemd hardening after explicit authorization
7. Restart and emergency-stop verification
8. Documentation, commit, review, and BoxBrain handoff
