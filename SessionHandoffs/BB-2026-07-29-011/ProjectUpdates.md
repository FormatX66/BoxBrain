# Project Updates

## BrainConnect

- **Status:** Active alpha
- **Completion:** 98% planning estimate
- **Current revision:** `be0738c`
- **Installed revision:** `567ffa3`
- **Verified now:** Enabled and quoted execution settings are detected;
  disabled settings and inert authenticated health are accepted; unsafe health
  is refused; the installer calls preflight before wheel construction.
- **Pending nightshift:** Real-Pi refusal/success exercise, full controller and
  Flutter suites, amd64/arm64 builds, exact Pi 3.26 gates, and the next live VM
  proof.
- **Pending operator input:** Scrolling, shell, or clipboard selection.

## BoxBrain

- Added a durable daytime operator-input list and nightshift queue.
- Recorded decisions BB-ADR-039 and BB-ADR-040.
- Updated the BrainConnect current revision and immediate next step.

## Related projects

- **Security:** Upgrade mutation is now gated by independent configuration and
  live-state evidence.
- **Research:** Nightshift results can become reproducible performance and
  compatibility records.
- **Automation:** A future scheduler may consume the nightshift queue only
  after the operator explicitly authorizes unattended execution.
