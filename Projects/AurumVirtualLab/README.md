# Aurum Virtual Hardware Lab

This lane gives Aurum fast, repeatable pre-hardware evidence without confusing emulation with physical proof.

The release gate runs four independent jobs in parallel:

- Docker on a native GitHub x86_64 VM: bounded Aurum runtime/unit/self-test checks.
- Docker on a native GitHub ARM64 VM: the same runtime checks on ARM64 without cross-emulation.
- QEMU x86_64 + OVMF: boots the actual Aurum PC ISO through UEFI and requires `AURUM_PC_READY` plus `selftest=ok`.
- QEMU `raspi3b`: boots the Pi 3 ARM64 kernel/device tree against the actual Aurum microSD root filesystem and requires `AURUM_PI3_READY` plus `selftest=ok`.

The Pi QEMU lane deliberately uses QEMU direct-kernel boot with the real microSD root filesystem. It validates the Pi 3 machine model, kernel, emulated SD, real image root filesystem, installed Python, Codelation, and Aurum runtime. The scratch QEMU init bypasses normal Raspberry Pi provisioning and systemd, so systemd wiring is checked structurally and remains subject to physical-node verification.

Evidence levels remain distinct:

`Docker runtime verified` != `QEMU machine boot verified` != `physical machine verified`.

Workflow: `.github/workflows/aurum-virtual-lab.yml`

Every successful lane writes a commit-bound JSON evidence record. The convergence job rejects missing targets, duplicate targets, mixed commits, or inaccurate evidence labels. Only that job can produce `aurum-convergence-proof.json`, and only the downstream promotion job can build and publish a Pi3 application/runtime release.

QEMU Pi3 evidence is always labeled `virtual-machine-runtime-proof` with `physical_hardware_evidence=not-implied`. A QEMU result never promotes physical Pi hardware status.
