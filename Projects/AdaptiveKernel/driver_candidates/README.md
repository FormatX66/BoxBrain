# Pi 3 compile-only driver candidates

This directory keeps offline kernel/driver candidates warm without replacing or
binding the proven `smsc95xx` driver. The first candidate checks the exact Pi 3
kernel header API surface needed for future USB-network observation work. It is
not a hardware driver and has no runtime authority.

## Safety boundary

- Target exactly `Raspberry Pi 3 Model B Rev 1.2`; same-family revisions are a
  contract mismatch, not an implicit match.
- Build only against an explicitly named ARM64 header tree whose recorded kernel
  release exactly matches the requested target release.
- Build in a temporary directory and retain only a JSON receipt. The `.ko` is
  hashed and discarded.
- Never run `insmod`, `modprobe`, `depmod`, `modules_install`, or an install target.
- Define no module alias or device table, so no hardware or uevent can request it.
- Register no USB, platform, PCI, network, or other device driver.
- The module init function contains only `return -EPERM;`, so even an accidental
  manual load attempt is refused.
- Never write firmware, boot configuration, networking, sysfs bindings, or the
  source/header tree.
- Before reporting verified compilation, inspect the temporary `.ko` with
  read-only `modinfo` and `nm`: vermagic must name the exact release, aliases and
  device-table symbols must be absent, and unresolved registration/I/O symbols
  must not appear. Missing inspection tools hold verification rather than
  converting a compile into success.

`verify_contract.py` enforces these properties from the candidate source,
Kbuild file, and manifest before compilation. This is defense in depth, not
kernel mutation authority.

The first exact-header compile against Pi kernel `6.18.34+rpt-rpi-v8` usefully
failed closed: that kernel declares both `struct urb.actual_length` and
`struct urb.transfer_buffer_length` as `u32`, not signed `int`. The probe now
asserts the observed `u32` API and keeps that compatibility fact compile-checked
without registering or loading a driver. The bounded failed-assumption and
corrected direct-compile receipt is preserved at
`../results/pi3-driver-candidate-direct-compile-20260826.json`.

Independent workflow run `32958005908` repeated the corrected compile through
the Aurum runner path and retained artifact `9602758019`, digest
`sha256:2b80a65ac91c1208d9f62a7cf37174208a409d45a39e97dc1991b1f8087a8a18`.
The workflow and direct paths produced the same temporary module SHA-256 while
both separately proved it was never loaded or retained. The bounded CI receipt
is `../results/pi3-driver-candidate-ci-32958005908.json`.

## Offline checks

```text
python Projects/AdaptiveKernel/driver_candidates/verify_contract.py
python -m unittest discover -s Projects/AdaptiveKernel/driver_candidates/tests -v
```

## Safe compile-only CI shape

Use an isolated Linux runner or container with a trusted, immutable copy of the
exact Pi kernel headers and an ARM64 compiler. Pass the release explicitly:

```text
python Projects/AdaptiveKernel/driver_candidates/compile_only.py \
  --kernel-build /opt/pi3-headers/6.18.34+rpt-rpi-v8 \
  --expected-kernel-release 6.18.34+rpt-rpi-v8 \
  --cross-compile aarch64-linux-gnu- \
  --receipt candidate-receipt.json
```

The header tree must contain `Makefile`, `.config`, `Module.symvers`, and
`include/config/kernel.release`; `.config` must contain `CONFIG_ARM64=y`. A
release mismatch is a refusal, not a retry. A successful receipt proves only
source-contract validation, exact-header compilation, and read-only artifact
inspection. Safe CI must provide `modinfo` plus GNU/LLVM `nm`; a portable
compile without those tools produces held evidence, not verified success. It does not prove a
module load, driver binding, packet behavior, boot safety, or promotion.
