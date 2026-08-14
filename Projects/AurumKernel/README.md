# Aurum Kernel v0.01

Aurum Kernel uses the same staged build architecture as Aurum PC.

The top-level build flow is intentionally parallel to `Projects/AurumPC/build-iso.sh`:

1. validate bounded build sources and contracts;
2. install independent VM tooling on the GitHub host;
3. build inside a Debian Bookworm container with Debian-native packages;
4. keep build outputs isolated from the running host;
5. verify checksums before boot testing;
6. boot the produced artifact in QEMU and require an Aurum readiness marker;
7. record build metadata and hashes;
8. publish only the boot-verified artifact bundle.

`build-kernel.sh` is the kernel equivalent of the Aurum PC `build-iso.sh` entry point. The reusable hardware profiler, driver planner, hotplug detector, external-module compiler, and machine-kernel compiler remain under `Projects/Codelation/kernel_selfbuild/`.

## Seed vs machine build

The CI reference lane builds x86_64 from Debian Bookworm's packaged Linux source and a conservative reference config. On an actual Aurum flash seed, the same script accepts `AURUM_KERNEL_SOURCE`, `AURUM_BASE_CONFIG`, and `AURUM_LSMOD_FILE` so the build can use the observed machine's known-good seed configuration and loaded-module evidence.

The generic seed kernel remains the rollback environment. A generated machine kernel is a trial artifact until its boot and device evidence pass.
