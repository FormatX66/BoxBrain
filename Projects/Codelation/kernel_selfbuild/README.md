# Aurum Self-Kernel Compiler v0

This side branch develops a machine-specific Linux kernel compiler for Aurum.

## Goal

Aurum boots from a generic, known-good x86_64 or ARM64 Linux seed on removable media, inventories the machine, resolves the exact kernel facilities and drivers required by observed hardware, and produces a machine-specific kernel + module set with a rollback path.

The seed kernel is the recovery/observation environment. The generated kernel is never allowed to replace the only known-good boot path.

## Build model

1. **Seed boot** — boot a normal x86_64 or ARM64 Linux environment with broad driver coverage.
2. **Observe** — record CPU architecture, firmware mode, PCI/USB/platform devices, modaliases, bound drivers, and loaded modules.
3. **Resolve** — prefer existing upstream/vendor kernel drivers by modalias and device identity. Existing kernels and drivers are guidance/evidence, not blindly copied implementations.
4. **Plan** — derive a conservative machine config from a known-good base config, preserving boot-critical storage, filesystem, console, input, network, firmware and bus support.
5. **Compile** — build a machine-specific kernel and module pack. Optional capabilities remain modules where possible so hotplug does not require a full kernel rebuild.
6. **Verify** — static checks, unit/KUnit where available, VM boot tests where meaningful, artifact hashes, and an A/B boot contract.
7. **Boot trial** — first boot is a trial slot. Failure returns to the generic seed automatically.
8. **Hotplug** — when a new peripheral appears, resolve an existing module first. If none exists, create a bounded driver work item and test it out-of-tree before it is eligible for loading.

## Driver policy

Aurum's order of operations for an unknown peripheral is:

- use an already-bound driver if one exists;
- resolve the device modalias against installed/source-tree module aliases;
- search for the same controller/chip family and bus protocol;
- reuse a compatible generic class driver where the hardware contract proves compatibility;
- only then create a new driver candidate.

A generated driver is **not** automatically trusted simply because it compiles. Real hardware loading requires protocol evidence, successful tests, an explicit capability/permission gate, and a rollback path. Aurum must never invent register maps, DMA layouts, firmware commands, interrupt semantics, or hardware authority.

## Why modules stay important

"Custom kernel" means the kernel is tailored to the machine, not that every peripheral must be compiled into the monolithic image. Boot-critical hardware can be built in; hotpluggable and replaceable peripherals should normally be modules. That allows Aurum to add a new peripheral driver without recompiling the whole kernel while still keeping the running system machine-specific.

## Initial implementation

- `hardware_profile.py` — read-only Linux machine inventory from `/sys`, `/proc`, and `platform`.
- `driver_plan.py` — deterministic existing-driver/modalias/new-driver classification.
- `kernel_plan.py` — architecture-specific kernel and module build plan with boot safety gates.
- `bootstrap.py` — one command to emit `machine-profile.json` and `kernel-build-plan.json`.
- CI — unit tests plus a hosted Linux observation smoke test on this side branch.

## Next frontier

The next build wave is the actual compiler executor: kernel-source acquisition/pinning, config derivation (`olddefconfig`/`localmodconfig`-style reduction with boot-critical preservation), reproducible build, initramfs generation, QEMU boot verification where supported, signed artifact manifest, and removable-media A/B deployment.
