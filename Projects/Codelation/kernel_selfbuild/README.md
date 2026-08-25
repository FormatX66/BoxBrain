# Aurum Self-Kernel Compiler

This package performs an out-of-tree Linux kernel build without installing into
or changing the running host kernel. It records the source identity, final
configuration, build command plan, image hash, and whether modules were built.

The first canonical carrier is the x86_64 boot-test profile in
[AurumKernel](../../AurumKernel/README.md). That profile builds a real Linux
`bzImage`, constructs a static verification initramfs, verifies the artifact
hashes, and boots it under QEMU. Building and installing a new running-host
kernel is deliberately outside this package's authority.
