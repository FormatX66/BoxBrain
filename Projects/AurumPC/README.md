# Aurum PC v0.01

Aurum PC is the removable-media x86_64 bring-up environment for Aurum. Linux is used only as a temporary hardware compatibility substrate; the operator surface remains the bounded `aurum>` console.

## First boot

On a physical primary console Aurum automatically:

1. captures a read-only exact-machine hardware profile from `/proc` and `/sys`;
2. derives a conservative kernel/driver plan while preserving the removable recovery path;
3. if no wireless interface exists, emits `AURUM_WIFI_DIAG` with PCI/USB network-controller candidates, modaliases, bound drivers and loaded-module evidence;
4. attempts Wi-Fi bring-up, asking for credentials only when a wireless interface is available;
5. verifies addressing, routing, DNS and GitHub TCP connectivity;
6. refreshes only the allowlisted `FormatX66/BoxBrain` trunk when online;
7. seeds Aurum state, runs its bounded self-test, and starts the resumable local-first self-build;
8. returns to the bounded `aurum>` console.

The serial/QEMU console disables autonomous first boot so CI can drive deterministic verification without racing the physical-console build.

## Safety

Hardware inventory is read-only and defaults to `/run/aurum`. The removable boot path remains the known-good recovery path. Aurum does not automatically overwrite an internal disk. Physical driver replacement remains one target at a time with compile-before-load, behavior comparison, backup and automatic-restore gates. Storage/boot-critical replacement, firmware/NVRAM/OTP/fuse writes, power/clock/voltage/thermal/reset control and unbounded raw MMIO/PIO remain separately gated.
