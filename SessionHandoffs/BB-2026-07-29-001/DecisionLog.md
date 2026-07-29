# Decision Log

## BB-ADR-013

- **Date:** 2026-07-29
- **Decision:** Verify the production RDP certificate boundary with an
  ephemeral, protocol-faithful NLA/HYBRID fixture on Raspberry Pi loopback and
  keep full desktop testing as a separate milestone.
- **Reason:** Windows Sandbox is disposable but its desktop already depends on
  the Remote Desktop service and did not expose a second listener. The
  development host was rejected as a target because it contains user data and
  repositories. The identity gate still required a live production helper and
  controller test.
- **Alternatives considered:** Use the development host's RDP listener, enable
  Hyper-V and reboot, install a third-party VNC/RDP server in Windows Sandbox,
  use a non-protocol TLS server, or defer all live verification.
- **Chosen solution:** Run a short-lived RDP negotiation and TLS certificate
  server on Pi loopback, require exact NLA/HYBRID selection, rotate its
  certificate on the same endpoint, and destroy its private keys after the
  run.
- **Impact:** Exact match, mismatch disablement, unreachable, timeout, and
  pre-authentication behavior are live-verified through production components.
  The result does not claim desktop or frame compatibility.

## BB-ADR-014

- **Date:** 2026-07-29
- **Decision:** Preserve `HOME` in the controller's fixed minimal environment
  for the native FreeRDP helper.
- **Reason:** The installed helper passed with its inherited environment but
  exited before opening a socket when the controller removed `HOME`. A
  controlled preflight proved `HOME` alone was sufficient.
- **Alternatives considered:** Inherit the complete service environment, add
  `USER`, locale, and XDG variables speculatively, modify the native helper to
  bypass FreeRDP initialization, or run the helper through a shell wrapper.
- **Chosen solution:** Add only `HOME` to the existing allowlist while keeping
  fixed arguments, no shell, external certificate management, certificate
  rejection, and explicit exclusion of the API token.
- **Impact:** The production helper can create its FreeRDP context without
  broadening process inputs or enabling trust-on-first-use, authentication, or
  desktop startup.

## BB-ADR-015

- **Date:** 2026-07-29
- **Decision:** Stop and disable an earlier Pi controller revision before
  foreground upgrade verification, then enable the new revision only after the
  gate passes.
- **Reason:** The first upgrade installed the new immutable release while the
  previous service process remained active, so the foreground verifier refused
  to compete for the API port.
- **Alternatives considered:** Verify the new code through the existing service
  process, restart directly without a foreground gate, use a second temporary
  port, or leave upgrade orchestration manual.
- **Chosen solution:** Use `systemctl disable --now` after staging the release,
  run the authenticated foreground verifier, and use `enable --now` only when
  requested and after that verification succeeds.
- **Impact:** First installs and upgrades use the same gate. A failed foreground
check leaves the service disabled instead of silently returning to an
unverified state.
