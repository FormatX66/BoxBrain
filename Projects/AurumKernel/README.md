# Aurum Self-Built Kernel v0.02

This kernel lane supplies candidate artifacts to the broader
[TinySeed Self-Build Lifecycle](../../docs/architecture/TINYSEED_SELF_BUILD_LIFECYCLE.md).
The currently proven Pi 3 artifact is a bridge-kernel candidate for the first
internal boot, not yet proof of autonomous full-phenotype growth.

This lane builds a real x86_64 Linux kernel from packaged source, entirely
out-of-tree, then boots it with a static verification initramfs under QEMU.
It does not install into, replace, or reconfigure the running host kernel.

## Verified path

1. Resolve a packaged Linux source archive or an explicitly supplied source tree.
2. Derive a conservative x86 defconfig with serial console and initramfs support.
3. Compile `bzImage` through the bounded
   [self-kernel compiler](../Codelation/kernel_selfbuild/README.md).
4. Create a BusyBox initramfs containing deterministic readiness markers.
5. Hash the source archive identity, configuration, kernel, initramfs, modules
   bundle, manifest, and build settings.
6. Recheck every hash before QEMU starts.
7. Require both `AURUM_KERNEL_READY` and `selftest=ok` from the serial console.
8. Emit `boot-test-receipt.json` with kernel, initramfs, and console-log hashes.

The default boot-test profile compiles the kernel image without the unused
module catalog so the first proof is bounded. Set `AURUM_BUILD_MODULES=1` for a
full module build and staged module bundle.

## WSL/Linux commands

```sh
export AURUM_KERNEL_WORK_ROOT="$HOME/.cache/aurum-kernel-v0.02"
export AURUM_BUILD_JOBS=8
sh Projects/AurumKernel/build-kernel.sh
sh Projects/AurumKernel/boot-test.sh
```

The resulting ignored local bundle is
`dist/Aurum-Kernel-v0.02-x86_64/`. It remains a VM-tested candidate, not a
physical-machine or promotion proof. A real boot slot still requires a protected
Last Known Good path, trial-slot authority, and device/health evidence.

## Raspberry Pi 3 trial lane

The Pi 3 cannot boot the x86_64 artifact. Its preparation lane pins Raspberry
Pi's `rpi-6.12.y` source by commit, cross-builds `Image`, matching Pi 3 DTBs,
overlays, and modules with `bcm2711_defconfig`, and boots the exact ARM64 kernel
under QEMU's `raspi3b` machine before it can enter a flashable trial image.

```sh
export AURUM_PI3_KERNEL_WORK_ROOT="$HOME/.cache/aurum-pi3-kernel-v0.02"
export AURUM_BUILD_JOBS=8
sh Projects/AurumKernel/build-pi3-kernel.sh
sh Projects/AurumKernel/boot-test-pi3.sh
sudo sh Projects/AurumKernel/prepare-pi3-image.sh
sudo sh Projects/AurumKernel/verify-pi3-image.sh
```

Image-only fixes can be revisioned without rebuilding the already-proven kernel:

```sh
sudo AURUM_PI3_IMAGE_REVISION=0.02.1 \
  sh Projects/AurumKernel/prepare-pi3-image.sh
```

The image builder retains the stock kernel and configuration below
`boot/firmware/aurum-stock/`, adds a physical readiness service, checks the root
filesystem without modifying it after unmount, and emits a compressed image,
checksum, partition receipt, and manifest. It never writes removable media.

Use a separate microSD card for the first physical trial. Swapping back to the
untouched card is the Last Known Good recovery path. Direct USB flashing is not
a normal Pi 3 interface; USB mass-storage *boot* is a later option whose support
depends on the exact Pi 3 model, OTP state, and storage-device compatibility.
