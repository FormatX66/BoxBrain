# Change Log

## BrainConnect

### Changed files

- Added `plugins/rdp-observer/native/install-pi.ps1`
- Made the native integration fixture accept an explicit expected FreeRDP
  runtime-version prefix while preserving 3.15 as the container default
- Updated root, controller, architecture, development, roadmap, security,
  target, observer, and native-helper documentation

### Reason

Turn the tested arm64 image into a guarded, repeatable installation on the
actual Kali Raspberry Pi 4 without silently changing the host package set.

### Dependencies

- Native helper source revision `01c34d7`
- Content-addressed arm64 Docker image
  `sha256:5d80ae566ebaaad309e2c61837aa6668586703959c79cf6294c2e42df70144be`
- Kali `libfreerdp3-3` `3.26.0+dfsg-1`
- Existing Pi SSH key and stored host identity

### Future implications

The installer must be rerun after any helper, image, or FreeRDP runtime change.
Controller deployment must reference the root-owned helper path and must not
weaken the runtime/provenance gate.

## Raspberry Pi 4

### Changed paths

- `/usr/local/libexec/brainconnect/brainconnect-freerdp-probe`
- `/usr/local/share/brainconnect/brainconnect-freerdp-probe.provenance.json`

### Reason

Install the verified observation-only certificate helper and its bounded
provenance record.

### Safety notes

- The binary is `root:root` mode `0755`.
- Provenance is `root:root` mode `0644`.
- No package was installed, upgraded, downgraded, or held.
- A failed first installer attempt created only an empty unintended directory
  under `/home/kali`; it was verified empty and removed before the corrected
  installation.

## BoxBrain

### Changed files

- Admin decision, change, repository, roadmap, session, and TODO indexes
- BrainConnect project and ecosystem project indexes
- Integration registry and session handoff index
- All nine files in `BB-2026-07-28-007`

### Reason

Record the real Pi deployment, exact artifact/runtime identities, verification
evidence, pull request, remaining controller and Windows-lab blockers, and next
execution plan.
