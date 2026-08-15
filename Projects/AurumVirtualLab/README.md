# Aurum Virtual Hardware Lab

This lane gives Aurum fast, repeatable pre-hardware evidence without confusing emulation with physical proof.

The release gate runs four independent jobs in parallel:

- Docker on a native GitHub x86_64 VM: bounded Aurum runtime/unit/self-test checks.
- Docker on a native GitHub ARM64 VM: the same runtime checks on ARM64 without cross-emulation.
- QEMU x86_64 + OVMF: boots the actual Aurum PC ISO through UEFI and requires `AURUM_PC_READY` plus `selftest=ok`.
- QEMU `raspi3b`: boots the Pi 3 ARM64 kernel/device tree against the actual Aurum microSD root filesystem and requires `AURUM_PI3_READY` plus `selftest=ok`.

The Pi QEMU lane deliberately uses QEMU direct-kernel boot with the real microSD root filesystem. This validates the kernel/rootfs/systemd/Aurum handoff under the Pi 3B machine model while leaving Raspberry Pi firmware compatibility as a separate physical-hardware gate.

Evidence levels remain distinct:

`Docker runtime verified` != `QEMU machine boot verified` != `physical machine verified`.

Workflow: `.github/workflows/aurum-virtual-lab.yml`
