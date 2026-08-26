# Adaptive Driver Test 001: Raspberry Pi 3

This project implements the first complete Aurum adaptive-driver self-build loop:

`fingerprint -> capability model -> candidate selection/synthesis -> isolated build -> safe load/test -> telemetry -> LKG comparison -> promote/reject/quarantine -> result log -> next candidate`

## Safety boundary

Test 001 began with a generation-1 compatibility interface, not a replacement
kernel module. It synthesizes a fingerprint-bound Python shim that reads the Pi
3 network interface's existing sysfs state. The generation-2 observer adds
Pi-specific incomplete-read evidence and quarantine semantics while retaining
the same userspace-only boundary. A candidate runs in an isolated subprocess and
is never installed, imported into the controller, or granted a write capability.

The loop never calls `modprobe`, changes driver bindings, writes firmware,
changes networking, or modifies boot state. Promotion updates only the isolated
experiment's metadata after preserving and cryptographically verifying the
previous LKG snapshot. The Linux reference driver remains the physical LKG.

The later kernel-module canary remains held until matching headers, an
out-of-band watchdog, reboot/recovery proof, and a fresh explicit mutation gate
are all present.

## Aurum Farmer and Future Branch ownership

The persistent Aurum Farmer owns physical completion through
`farmer/pi3-adaptive-driver-job.json`. Its default high-confidence Future Branch
watches a strict semantic receipt for the pinned experimental Pi 3. A file's
existence is not success: target identity, physical acceptance, completed and
promoted state, unchanged system driver, build/fingerprint evidence, score, and
the rollback snapshot must all be present before Farmer can seal the result.

The kernel-module canary and QPU-ordering branches are registered beside it but
remain dependency- and authority-held. The GitHub physical workflow mirrors
changed evidence into Farmer's durable runtime and resumes the waiting job; the
classical candidate order remains the no-QPU fallback.

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

## Generation 2 and missing-field quarantine fixture

The deterministic fixture can also exercise the Pi 3-specific Generation 2
tolerant observer. It remains an isolated, read-only userspace artifact; only
its verified metadata can be promoted:

```text
python -m Projects.AdaptiveDrivers.adaptive_driver_loop \
  --state-dir work/adaptive-driver-generation-2 \
  --fixture pi3b \
  --candidate pi3-net-sysfs-tolerant-v2 \
  --allow-promotion
```

The companion fault fixture makes `carrier` unavailable only inside the
synthesized observer. It does not remove or alter the fixture's sysfs file. The
observer reports the missing evidence, the controller quarantines the candidate,
and the previously promoted LKG metadata must remain byte-for-byte unchanged:

```text
python -m Projects.AdaptiveDrivers.adaptive_driver_loop \
  --state-dir work/adaptive-driver-generation-2 \
  --fixture pi3b \
  --candidate pi3-net-sysfs-tolerant-v2-missing-field-fixture \
  --include-faults \
  --allow-promotion
```

## QPU policy

Classical ranking is always available. A QPU provider is optional and is not
called for a small candidate space. For larger spaces, its shortlist is accepted
only when the provider result is valid and the measured provider latency is less
than the estimated physical candidate-test time avoided. Otherwise the loop
records why QPU was skipped and uses the deterministic classical order.
