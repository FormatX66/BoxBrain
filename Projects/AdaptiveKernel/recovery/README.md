# AdaptiveKernel independent recovery scaffold

This directory defines the fail-closed controller shape required before a Pi 3
kernel canary may claim automatic out-of-band recovery. The current implementation
is simulation-only: it contains no SSH, network, GPIO, smart-plug, relay, KVM,
firmware, boot, or device adapter.

The scaffold keeps four identities distinct:

1. the exact experimental target (`Raspberry Pi 3 Model B Rev 1.2`, serial
   `00000000a6a7df7f`);
2. an independently identified controller;
3. an observer that remains usable when the target kernel is unavailable;
4. a power/LKG actuator and post-recovery verifier that are independently
   identified and target-kernel-independent.

The simulated state machine observes health, refuses ambiguous or non-automatic
failure claims, exercises a simulated power/LKG recovery, and requires exact
post-recovery target, LKG, and health matches. Every receipt contains a
`watchdog_evidence` object with the exact fields accepted by
`pi3_watchdog_contract.evaluate_watchdog`.

Simulation success never becomes physical proof. Those evaluator fields remain
false, `watchdog_proven` remains false, and mutation authority remains false.
This prevents a test double from unlocking the physical kernel-canary gate.

`physical_watchdog_receipt.py` is the separate fail-closed intake path for a
future real recovery cycle. It requires exact target and LKG identity, four
distinct independently identified components, target-kernel-independent
observation and actuation, automatic failure/recovery evidence with distinct
content hashes, exact post-recovery health, and zero mutation authority. The
kernel-canary preflight treats a missing receipt as a normal hold and rejects a
present malformed receipt. Even a fully validated physical watchdog receipt can
only remove the watchdog prerequisite; fresh kernel-mutation authority remains a
separate gate.

Run the focused tests from the repository root:

```text
python -m unittest -v \
  Projects.AdaptiveKernel.tests.test_pi3_watchdog_contract \
  Projects.AdaptiveKernel.recovery.test_out_of_band_controller \
  Projects.AdaptiveKernel.recovery.test_physical_watchdog_receipt \
  Projects.AdaptiveKernel.tests.test_pi3_kernel_canary_preflight_workflow
```

## Remaining physical gates

- Identify and pin a genuinely external KVM/observer controller.
- Prove that video or health observation survives loss of the Pi kernel and its
  network stack.
- Identify and exercise an external power and LKG recovery actuator.
- Automatically detect a real induced failure and actuate recovery without SSH
  or target-local timers.
- Re-prove the exact Pi model/serial, protected LKG artifact, and target health
  after recovery.
- Only then request fresh, separate kernel-mutation authority.
