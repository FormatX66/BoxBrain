# Project Updates

## BrainConnect

- **Status:** Active alpha
- **Priority:** P0
- **Completion:** 95% planning estimate
- **Revision:** `e81f5f5` on `feature/brainconnect-freerdp-input`
- **Review:** [Draft pull request 11](https://github.com/FormatX66/BrainConnect/pull/11)
- **Complete:** Native pointer, Unicode-text, and fixed allowlisted-key input;
  amd64/arm64 builds; Pi FreeRDP 3.26 fixtures; encrypted systemd credential
  promotion; live transport-level input run; and credential/executor rollback.
- **Installed but inert:** Control artifact SHA-256
  `1d91cf630e7b1f16f8c95bc871479218caa86a1e9d7d9aa8aa3aebdbaa59b74b`;
  `executor_enabled=false`; no execution drop-in; zero encrypted RDP
  credentials.
- **Next:** Authorized checkpoint restore, bounded persistent input session,
  independent frame or guest-state verification, and one harmless verified
  input sequence.

## Related projects

- **Security:** The standard systemd `0440` plus named-service ACL form is now a
  verified runtime-secret pattern.
- **Research:** Transport acceptance and verified state change must remain
  separate benchmark outcomes.
- **AgentFramework:** Runtime capability discovery should include whether a
  capability has an independent verifier.
- **Automation:** Checkpoint restoration, certificate re-probe, credential
  promotion, bounded run, and credential rollback should become one replayable
  workflow.
