# Project Updates

## BrainConnect

- **Status:** Active alpha
- **Priority:** P0
- **Completion:** 96% planning estimate
- **Revision:** `593daa0` on
  `feature/brainconnect-rdp-input-verification`
- **Review:** [Draft pull request 12](https://github.com/FormatX66/BrainConnect/pull/12)
- **Complete:** Bounded persistent keyboard sequence, controller/database/UI
  support, amd64/arm64 gates, Pi promotion, fixed process verifier, guarded
  checkpoint restore, live transport run, credential rollback, and final
  checkpoint recovery.
- **Installed but inert:** Pi controller/native source `eabc3d3`; control
  SHA-256
  `135ee649c8b40ed39b1e09138aad1461d7998d36e8251c75f366b91a42b1ea4e`;
  executor disabled; no drop-in; zero encrypted RDP credentials.
- **Next:** Map Windows sessions and Terminal Services events, fix binding to
  the Explorer session, and obtain one independent Notepad process proof.

## BoxBrain

- **Status:** Active operating repository
- **Priority:** P0
- **Review:** [Draft pull request 3](https://github.com/FormatX66/BoxBrain/pull/3)
- **Complete:** Guarded exact-checkpoint restore helper, success/error receipts,
  operator Hyper-V group membership, and final clean restore.
- **Next:** Complete review/merge and add the next guest session-diagnostic
  workflow only after consolidating with existing Hyper-V tools.

## Related projects

- **Security:** UAC remains the privilege boundary; exposed controller tokens
  are rotated immediately under existing ADR-020.
- **Research:** Session identity joins transport and verified state as a
  separate benchmark dimension.
- **Automation:** The lab cycle now has guarded restore, promotion, run,
  verifier, cleanup, and final-restore building blocks.
