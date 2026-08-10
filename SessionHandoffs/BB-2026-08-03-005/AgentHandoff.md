# Agent Handoff

## Current objective

Verify automatic Pi-screen opening across the currently configured connection
paths without weakening the console transport boundary.

## Tasks

1. Observe one offline-to-online transition for USB Ethernet, LAN, or AP.
2. Confirm exactly one browser tab opens for the selected path.
3. Confirm no additional tab opens while that path remains reachable.

## Dependencies

- Current-user Windows logon.
- Pinned Pi host key and `boxbrain_pi_ed25519` identity.
- Pi console package previously provisioned on the Pi.

## Files affected

- `installer/open-pi-console.ps1`
- `installer/watch-pi-console.ps1`
- `installer/install-pi-console-auto-open.ps1`
- `installer/test-pi-console-scripts.ps1`
- Console documentation and session indexes.

## Required repositories

- `FormatX66/BoxBrain`

## Verification checklist

- Run `installer/test-pi-console-scripts.ps1`.
- Run `installer/validate-project.ps1`.
- Run `Admin/validate_repository.py`.
- Verify the Startup shortcut and one live watcher process.
- Verify the launcher returns a loopback-only noVNC URL.

## Suggested commit message

`Open the Pi console when a connection appears`

## Suggested branch

`codex/pi-console-auto-open`

## Potential risks

- A changed LAN address requires an explicit watcher address update.
- The background watcher opens the Windows default browser, not a specific
  application's embedded browser.

## Estimated completion order

Commit, push, reconnect proof, then review and merge.
