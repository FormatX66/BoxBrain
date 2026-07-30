# Decision Log

## BB-ADR-019

- **Date:** 2026-07-29
- **Reason:** BrainConnect's stored target fingerprint and FreeRDP probe cannot
  independently establish the identity they are intended to compare.
- **Alternatives considered:** Trust on first use, use the FreeRDP helper
  output as both source and verifier, export the certificate through RDP, or
  query the guest certificate store through Hyper-V PowerShell Direct.
- **Chosen solution:** Read the certificate bound to `RDP-tcp` from the guest
  certificate store through Hyper-V PowerShell Direct, compute SHA-256 from
  the raw certificate, save only non-secret metadata outside Git, and then
  register that value in BrainConnect.
- **Impact:** The live certificate comparison now has separate acquisition and
  verification paths without accepting an unknown certificate or supplying a
  credential to FreeRDP.

## BB-ADR-020

- **Date:** 2026-07-29
- **Reason:** A malformed remote health-check command allowed the controller
  bearer token to appear in diagnostic output.
- **Alternatives considered:** Continue because the output was local, redact
  only the record, preserve the token and monitor it, or revoke it immediately.
- **Chosen solution:** Treat the token as compromised, atomically replace it
  on the Pi, restart the controller, and prove authenticated HTTP 200,
  unauthenticated HTTP 401, private ownership/mode, production environment,
  and `executor_enabled = false` before continuing.
- **Impact:** The exposed value is invalid. The replacement token never left
  the Pi or entered Git, and future authenticated operations must use a
  reviewed command path that cannot print the token.
