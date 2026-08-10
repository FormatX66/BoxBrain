# Verification Checklist

- [x] Five transport types always appear in deterministic order.
- [x] Missing hardware never reports a ready session capability.
- [x] Bluetooth HID is reported as pairing-required, not automatically trusted.
- [x] NFC is limited to onboarding/handoff semantics.
- [x] 49 edge-agent, 79 controller, and 19 Flutter tests pass; Flutter analysis
  reports no issues.
- [x] No adapter, pairing, gadget, target, or live Pi state changed.
- [ ] Repository validation passes except for the intentionally untracked
  operator `AGENTS.md`, which it reports as an orphan.
- [ ] Live Pi/dashboard source deployment is verified.
- [ ] Connection sessions and remote enrollment are implemented.
