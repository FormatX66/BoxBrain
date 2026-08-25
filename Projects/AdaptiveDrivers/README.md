# Adaptive Driver Test 001: Raspberry Pi 3

This project implements the first complete Aurum adaptive-driver self-build loop:

`fingerprint -> capability model -> candidate selection/synthesis -> isolated build -> safe load/test -> telemetry -> LKG comparison -> promote/reject/quarantine -> result log -> next candidate`

## Safety boundary

Test 001 is a generation-1 compatibility interface, not a replacement kernel
module. It synthesizes a fingerprint-bound Python shim that reads the Pi 3
network interface's existing sysfs state. The candidate runs in an isolated
subprocess and is never installed, imported into the controller, or granted a
write capability.

The loop never calls `modprobe`, changes driver bindings, writes firmware,
changes networking, or modifies boot state. Promotion updates only the isolated
experiment's metadata after preserving and cryptographically verifying the
previous LKG snapshot. The Linux reference driver remains the physical LKG.

The later kernel-module canary remains held until matching headers, an
out-of-band watchdog, reboot/recovery proof, and a fresh explicit mutation gate
are all present.

## Run locally with the deterministic Pi 3 fixture

```text
python -m Projects.AdaptiveDrivers.adaptive_driver_loop \
  --state-dir work/adaptive-driver-test-001 \
  --fixture pi3b \
  --allow-promotion
```

Use `--rollback` with the same state directory to restore the protected previous
LKG metadata. On a real Pi 3, omit `--fixture`; the hardware fingerprint gate
fails closed on every other model or architecture.

## QPU policy

Classical ranking is always available. A QPU provider is optional and is not
called for a small candidate space. For larger spaces, its shortlist is accepted
only when the provider result is valid and the measured provider latency is less
than the estimated physical candidate-test time avoided. Otherwise the loop
records why QPU was skipped and uses the deterministic classical order.
