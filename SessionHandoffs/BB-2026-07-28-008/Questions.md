# Questions

## Open

- Which disposable Windows VM or physical sandbox will provide the live RDP
  certificate fixture?
- What independent trusted path will verify its SHA-256 certificate
  fingerprint before BrainConnect registration?
- Should the workstation dashboard use an SSH-forwarded session, a short-lived
  controller credential, or another reviewed provisioning flow rather than the
  Pi's long-lived token?
- Should the existing public BoxBrain remote remain public after the canonical
  organization is merged?

## Resolved this session

- The controller uses the direct USB address `10.12.194.1:8000`.
- A dedicated `brainconnect` non-login account runs the service.
- The service is authorized, installed, enabled, and restart-verified.
- The controller is packaged as an immutable wheel with exact runtime
  dependencies and recorded provenance.
- The token stays on the Pi and out of the systemd environment file.
- Token and SQLite data use mode `0600` in a mode `0700` directory.
- No Pi package or firewall rule change was required.
