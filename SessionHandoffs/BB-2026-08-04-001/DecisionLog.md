# Decision Log

## BB-ADR-059

- **Date:** 2026-08-04
- **Decision:** Accept a changed target SSH host key only after the operator
  confirms the exact new fingerprint; preserve the old trust file and rotate
  only that target entry.
- **Reason:** The USB address was reused by a different or re-enrolled Windows
  identity, so continuing with the old pin or accepting a new key silently
  would defeat target identity verification.
- **Alternatives considered:** Disable strict checking; clear all target keys;
  accept the new key automatically; abandon the connection.
- **Chosen solution:** Exact fingerprint confirmation, timestamped backup,
  atomic single-entry rotation, and strict key-only proof.
- **Impact:** The intended target is connected without weakening trust for any
  other registered target.
