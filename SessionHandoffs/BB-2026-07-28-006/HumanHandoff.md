# Human Handoff

## What was accomplished

- Built the native Linux `brainconnect-freerdp-probe` helper against FreeRDP
  3.15.x and OpenSSL 3.
- Added strict fixed-argument parsing, bounded schema version 1 JSON, X.509
  metadata extraction, and an internal hard deadline.
- Forced every observed certificate to be rejected before authentication.
- Required the server-selected security protocol to be exactly NLA/HYBRID and
  added a test proving TLS-only selection emits no observation.
- Added digest-pinned Docker builds and passed native tests on amd64 and
  Raspberry Pi-compatible arm64.
- Mapped native deadline exit code 124 to the controller's bounded timeout
  error.
- Reverified 27 controller tests, Python compilation, Flutter analysis, 8
  Flutter tests, and the production Flutter web build.
- Published BrainConnect commit `01c34d7` and opened draft pull request 4.

## Decisions made

- Pin the current native build to Debian 13 and FreeRDP 3.15.x; upgrades require
  a deliberate callback and integration review.
- Use FreeRDP external certificate management and always return rejection from
  the X.509 callback.
- Treat `FreeRDP_SelectedProtocol == PROTOCOL_HYBRID` as a prerequisite for
  output. Advertising SSL and HYBRID is not itself trusted.
- Keep the runtime image non-root with no shell entrypoint, credentials,
  persistent certificate store, or device mounts.

## Current blockers

- The helper is not installed or packaged for a Linux/Pi controller host.
- No isolated disposable Windows RDP target has been selected for live
  exact-match and changed-certificate verification.
- BrainConnect pull request 4 is stacked on pull requests 3, 2, and 1; review
  and merge them in dependency order.
- BoxBrain pull request 3 still requires review and merge.

## Immediate next step

Package and install the helper on a Linux or Raspberry Pi controller, configure
its absolute path, and run the certificate-only workflow against an isolated
Windows RDP target with an independently known fingerprint.

## Long-term objective

Operate BoxBrain as the searchable coordination layer for an auditable
BrainConnect controller that can observe isolated lab systems through narrowly
scoped, replaceable plugins before any separately authorized input capability
is considered.
