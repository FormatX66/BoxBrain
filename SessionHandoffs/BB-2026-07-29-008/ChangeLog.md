# Change Log

## BrainConnect

- **Changed files:** Controller operation schema and SQLite migration; native
  protocol/parser/executor and tests; Flutter operation form and tests; Pi
  experiment runner and tests; plugin manifest; deployment provenance; and
  canonical architecture, security, roadmap, protocol, target, and installer
  documentation.
- **Reason:** Keep related key/text actions in one RDP connection, verify the
  outcome independently, promote the exact arm64 artifact, and isolate the
  remaining session-routing failure.
- **Dependencies:** FreeRDP 3.26 Pi runtime, enabled target UUID and certificate
  pin, systemd credentials, restricted guest identity, and disposable Windows
  checkpoint.
- **Future implications:** The transport sequence is complete. Windows session
  selection/unlock handling is now the next implementation layer.

## BoxBrain

- **Changed files:** Hyper-V checkpoint restore helper/runbook; admin session,
  decision, change, roadmap, and TODO indexes; BrainConnect project index;
  architecture integration summaries; and session bundle
  `BB-2026-07-29-008`.
- **Reason:** Preserve the exact restore, deployment, live evidence, credential
  rotation, cleanup, and next diagnosis order without duplicating BrainConnect
  implementation documentation.
- **Dependencies:** BrainConnect PR 12, BoxBrain PR 3, Hyper-V, the Pi
  controller, and the disposable Windows VM.
- **Future implications:** Future sessions can start with read-only Windows
  session diagnosis rather than repeating transport or checkpoint work.
