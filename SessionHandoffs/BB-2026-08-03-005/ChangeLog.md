# Change Log

## Changed files

- Hardened `installer/open-pi-console.ps1` and added a second SSH forward for
  the viewer page.
- Added `installer/watch-pi-console.ps1` and the reversible current-user Startup
  installer.
- Expanded deterministic PowerShell tests.
- Updated the root, installer, edge-agent, and architecture documentation.
- Added this session bundle and its admin indexes.

## Reason

Automatically present the Pi desktop whenever a known BoxBrain management path
becomes reachable.

## Dependencies

- Windows PowerShell 5.1, OpenSSH, the dedicated Pi SSH identity, and the
  already-provisioned Pi console.

## Future implications

- Additional static Pi addresses can be added explicitly to the watcher.
- Arbitrary discovery should remain a separately reviewed capability.
