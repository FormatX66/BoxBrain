# Human Handoff

## What was accomplished

- Built a guarded Raspberry Pi controller deployment around an exact Git
  revision, locked Python runtime dependencies, immutable release directories,
  provenance, and helper-checksum verification.
- Installed BrainConnect controller revision
  `016ec1f5b20db4c4b9679da74f8e36be4e1a11aa` on the directly attached Kali
  Raspberry Pi 4.
- Created a locked `brainconnect` account and enabled the hardened
  `brainconnect-controller.service`.
- Bound the API only to `10.12.194.1:8000` on the USB gadget interface.
- Kept the generated bearer token and SQLite database on the Pi as
  `brainconnect:brainconnect` mode `0600` in a mode `0700` state directory.
- Verified authenticated health in the foreground before service enablement.
- Verified HTTP 401 rejection, helper integrity, USB-only binding, private
  state, emergency-stop persistence, and recovery through multiple restarts.
- Published BrainConnect branch `feature/brainconnect-pi4-controller` at
  `ee9c518` as draft pull request
  [6](https://github.com/FormatX66/BrainConnect/pull/6).

## Decisions made

- The Pi controller is an immutable wheel-based release rather than a mutable
  source checkout.
- The service runs as a dedicated non-login user instead of `kali` or root.
- The controller binds to the direct USB address, not loopback-only, Wi-Fi, or
  every interface.
- The API token remains out of Git and out of the systemd environment file.
- Service promotion requires an authenticated foreground gate followed by
  restart and emergency-stop verification.

## Current blockers

- The isolated disposable Windows RDP target and its independently verified
  certificate fingerprint have not been selected.
- A controlled dashboard credential-provisioning workflow is still required;
  the Pi API token was intentionally not copied to Windows.
- BrainConnect pull request 6 is stacked on pull requests 5 through 1 and
  should be reviewed in dependency order.
- BoxBrain pull request 3 still requires review and merge.

## Immediate next step

Select and snapshot the isolated Windows RDP target, define the independent
fingerprint-verification path, and run certificate-only exact-match, mismatch,
timeout, and unreachable probes without credentials or a desktop session.

## Long-term objective

Operate BoxBrain as the searchable coordination layer for an auditable
BrainConnect research controller that observes disposable lab systems through
narrowly scoped plugins before any separately reviewed input capability is
considered.
