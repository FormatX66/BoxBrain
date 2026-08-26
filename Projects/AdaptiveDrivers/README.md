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

The later kernel-module canary has now cleared the exact-running-kernel build
prerequisites: matching headers, `Module.symvers`, compiler/build tools, and an
inert compile-only module were physically re-proven on the pinned Pi3. It remains
held on the stronger safety boundary: an automatic out-of-band watchdog/recovery
path must be proven, and any actual kernel-module load still requires a fresh
explicit mutation gate. The persisted preflight itself grants no mutation
authority.

## Physical Pi3 evidence

Generation 1 has been exercised on the pinned experimental Raspberry Pi 3 through
strict key-only SSH. The candidate matched the Linux reference observation at a
score of 100 while leaving the system driver unchanged.

Generation 2 is now physically proven at the same userspace-only boundary. GitHub
Actions run `32923966393` on source `426745e0b8d543b12b36db45db6195e0de24ab0e`
strictly re-proved the pinned Pi3 model, serial, host key, boot ID, and root
source, then:

- promoted `pi3-net-sysfs-tolerant-v2` after complete read evidence and a 100.0
  functional score;
- injected a missing `carrier` read into the synthesized observer and verified
  that the candidate was quarantined with
  `required-read-only-field-unavailable`;
- verified the LKG metadata SHA-256 was byte-identical before and after the
  quarantined fault;
- exercised the isolated metadata rollback back to
  `pi3-linux-reference-driver`;
- proved that no kernel module was loaded, no driver binding changed, no firmware
  mutation was allowed, and no system driver changed.

The durable evidence is
`evidence/pi3-generation2-physical.json`. This is **physical userspace adaptive
-driver proof**, not a kernel-module canary and not production ARM64 Tiny Seed
proof.

The kernel-canary prerequisite probe is now durably mirrored at
`evidence/pi3-kernel-canary-preflight.json`. Run `32926239577` proved matching
headers for kernel `6.18.34+rpt-rpi-v8`, `Module.symvers`, build tools, and an
inert compile-only canary without loading a module or changing the system driver.
Its canonical state is `held-out-of-band-watchdog-unproven`; this evidence cannot
be used as kernel-mutation authority.

Separately, the exact current Pi3 microSD card has a tested rollback image/archive
and the original card passed a fresh physical reboot canary. That removes the
old "physical hardware unavailable" assumption for safe Pi3 experiments, but it
does not grant kernel mutation authority.

The bounded overnight physical laboratory has also advanced through a temporary
virtual-driver stage. The Linux `dummy` module and `dummy0` interface were brought
up only under a locally scheduled rollback, then removed; the real `smsc95xx`
reference driver and Ethernet remained healthy and no persistent change was
retained. This is additional reversible physical-experiment evidence, not the
out-of-band recovery proof required for the real kernel canary.

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
