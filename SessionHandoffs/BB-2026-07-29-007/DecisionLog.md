# Decision Log

## BB-ADR-025

- **Date:** 2026-07-29
- **Decision:** Accept systemd runtime credentials owned by `root:root` with
  mode `0440` only when the service account has a named read ACL and all other
  credential safety checks pass.
- **Reason:** Systemd materializes encrypted credentials using a locked
  root-owned file plus a service-account ACL. Requiring service ownership or
  mode `0400` rejects the operating system's standard secure representation.
- **Alternatives considered:**
  - Copy credentials into service-owned files.
  - Loosen all group-readable-file checks.
  - Run the controller as root.
- **Chosen solution:** Recognize only the systemd form while retaining
  no-follow, regular-file, single-link, safe-directory, safe-owner, size,
  control-character, group-write/execute, and world-access rejection.
- **Impact:** The Pi can use host-encrypted systemd credentials without a
  second secret copy or elevated controller.

## BB-ADR-026

- **Date:** 2026-07-29
- **Decision:** Treat native input success as exact-session authentication and
  FreeRDP event submission until an independent verifier confirms the expected
  target-state change.
- **Reason:** The connector can truthfully prove connection, certificate,
  session, and input PDU success, but a disconnected RDP session and a
  transient Windows UI make visible outcome an independent fact.
- **Alternatives considered:**
  - Report every successful send as visual success.
  - Mark every send as failure until frame capture exists.
  - Infer success from elapsed time or an unlocked session.
- **Chosen solution:** Preserve the successful transport result and separately
  record that durable UI-state verification is absent.
- **Impact:** Audit and benchmark results remain truthful. The next milestone
  is a bounded persistent input session plus frame or guest-state verification.

## BB-ADR-027

- **Date:** 2026-07-29
- **Decision:** Keep the reviewed native input binary installed but inert, and
  remove the execution drop-in and every encrypted target credential after a
  live run.
- **Reason:** Rebuilding or reinstalling the exact artifact for every
  experiment adds drift without improving credential safety. Runtime authority
  comes from the disabled-by-default service setting and ephemeral credentials.
- **Alternatives considered:**
  - Remove the binary after every run.
  - Retain credentials while disabling only the executor.
  - Leave execution enabled inside the sandbox.
- **Chosen solution:** Retain the content-addressed root-owned binary, set
  `executor_enabled=false`, remove the drop-in, and delete username, password,
  and optional domain credentials.
- **Impact:** Future reviewed runs can begin from a verified artifact while the
  idle Pi retains no RDP authentication material or live execution authority.

## BB-ADR-028

- **Date:** 2026-07-29
- **Decision:** Add the left Windows key as a fixed named key while keeping
  right Windows and menu keys unavailable.
- **Reason:** A bounded left-Windows shortcut enables common Windows navigation
  without allowing arbitrary scancodes, but FreeRDP's portable named-scancode
  surface does not provide equivalent verified names for every Windows key.
- **Alternatives considered:**
  - Allow arbitrary numeric scancodes.
  - Omit Windows-key shortcuts.
  - Guess right-Windows or menu key codes.
- **Chosen solution:** Map only the verified left-Windows name and retain the
  existing maximum chord and repeat limits.
- **Impact:** Windows shortcuts remain explicit and testable without opening a
  raw keyboard injection interface.
