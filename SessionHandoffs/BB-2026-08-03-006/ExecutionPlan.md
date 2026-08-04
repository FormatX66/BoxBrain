# Execution Plan

1. Reproduce and inspect the HID report failure without replaying the sequence.
2. Implement a bounded retry for transient endpoint readiness only.
3. Add deterministic tests and bump to 0.14.1.
4. Run full validation and commit.
5. Upgrade the Pi through the rollback-guarded installer.
6. Verify readiness without a keypress.
7. Obtain a fresh exact confirmation and attempt enrollment once.
8. Accept success only after key-only SSH verification.
