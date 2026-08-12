# Aurum Local Lane Self-Test Expectations

Before local approval:

- `installer/deploy-aurum-live-to-pi.ps1` must be present.
- `Projects/Codelation` must be present.
- `%USERPROFILE%\.ssh\boxbrain_pi_ed25519` must exist.
- The repository remote must resolve to `FormatX66/BoxBrain`.

At install time the lane records SHA-256 approval for the installed watcher, the Aurum deployer, and the complete Codelation tree. At runtime a deploy is rejected if the deployer or Codelation tree no longer matches that local approval.

A successful result must contain Pi evidence with `identity=BBPI4/Aurum`, `AURUM_LIVE_VERIFIED`, `AURUM_PEER_SELF_TEST_OK`, and zero matching Aurum/Codelation systemd and user/root cron entries.
