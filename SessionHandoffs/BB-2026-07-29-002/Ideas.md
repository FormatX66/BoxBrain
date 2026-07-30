# Ideas

- Add a read-only command that compares the running VM definition with the
  clean checkpoint metadata before each experiment.
- Record the independently observed RDP certificate fingerprint beside the
  checkpoint name and guest build, not beside a credential.
- Build a synthetic slow-device fixture that proves the 15-second device scan
  deadline without requiring a live Windows target.
- Add observation run manifests containing checkpoint, endpoint, certificate,
  frame policy, model version, and retained-evidence hashes.
- Export a sanitized one-page lab readiness report from the existing JSON
  verification files.
- Add an operator-approved cleanup script that removes only detached answer
  media and the encrypted lab credential after exact path checks.
