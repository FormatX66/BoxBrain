# Questions

## Open

- Which disposable full Windows VM or dedicated lab computer will provide the
  frame-observation target?
- Should that target run on this workstation under Hyper-V after explicit
  feature-enable and reboot approval, or on separate hardware?
- What bounded frame cadence, maximum resolution, size, redaction, and
  retention should the first observer support?
- Should the workstation dashboard use an SSH-forwarded short-lived session or
  another credential exchange rather than the Pi's long-lived token?
- Should the existing public BoxBrain remote remain public after the canonical
  organization is merged?

## Resolved this session

- Windows Sandbox is not the full RDP target because it cannot expose a second
  listener while its own desktop session is active.
- The certificate boundary is live-verified with a protocol-faithful Pi-local
  fixture.
- `HOME` is the only newly preserved helper environment variable.
- The API token remains excluded from the helper environment and Windows host.
- Controller upgrades disable the earlier service before foreground
  verification and re-enable only after success.
- Exact match, certificate rotation, mismatch disablement, unreachable,
  timeout, no-authentication, no-desktop, and zero-application-data checks pass.
