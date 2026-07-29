# Decision Log

## BB-ADR-022

- **Date:** 2026-07-29
- **Decision:** Separate durable execution state from live VM transport through
  a fixed, disabled-by-default standard-input adapter protocol with transient
  output.
- **Reason:** Controller correctness, target containment, and truthful status
  can be proven before handling live credentials or desktop input. Standard
  input keeps operation content out of process listings, and transient output
  prevents shell or clipboard results from becoming durable audit content.
- **Alternatives considered:**
  - Implement FreeRDP control directly inside the FastAPI process.
  - Pass each operation field as command-line arguments.
  - Store full shell and clipboard results in SQLite.
  - Mark operations completed based only on process exit code.
- **Chosen solution:** Invoke one administrator-configured executable with only
  `--schema-version 1`, send strict JSON on standard input, validate one
  identity-matched JSON result, and persist only terminal metadata and output
  digest.
- **Impact:** The full queue-to-result path is testable with a no-action
  subprocess fixture. The future live connector can change transport
  internals without changing the controller or Flutter contracts.
