# Aurum PC v0.01

Aurum PC v0.01 is the first x86-64 PC-loadable experiment for Aurum. It deliberately uses a minimal Debian Linux live system only as a temporary hardware compatibility substrate while exposing Aurum, not a conventional Linux desktop or shell, as the operator surface.

## v0.01 acceptance gate

A build is accepted only when all of the following are true:

1. an amd64 hybrid ISO is produced;
2. the ISO reaches an Aurum console under x86-64 UEFI QEMU;
3. the serial console emits `AURUM_PC_READY`;
4. the bundled Codelation runtime deterministically re-verifies `io_safe_port_choice` through the existing `io-plan` capability;
5. no arbitrary command shell is exposed by the Aurum console;
6. the live image offers only a device-bound, whole-disk UEFI installer path;
7. the QEMU gate installs to a blank virtual disk and boots that installed disk without the ISO;
8. the image can report hardware, current Aurum chain state, Field capabilities, and perform explicit reboot/poweroff.

## Runtime surface

The initial console intentionally stays small:

- `status` — Aurum and machine state;
- `hardware` — CPU/kernel/DMI/memory/block/network inventory;
- `field` — currently reusable native/local capabilities;
- `selftest` — deterministic Codelation capability verification;
- `reboot` / `poweroff` — explicit machine lifecycle actions;
- `help` — bounded command list.

The x86 seed/build-node extension adds fixed operations without adding a shell:

- `seed` / `seed-status` — create and inspect the writable passive seed at `/var/lib/aurum/state/seed.bin`;
- `self-build` — start the bounded seed/native/self-build suites and deterministic autonomous chain in the background;
- `self-build-status` — inspect the active stage, elapsed time, generation, and upper-bound ETA without blocking the console;
- `self-build-cancel` — stop the active chain safely after preserving its latest completed-generation checkpoint;
- `install` — list only unmounted, non-USB internal installation targets and show their current contents;
- `install confirm ERASE-XXXXXXXX` — erase and install to the one disk bound to that freshly generated code;
- `git-status` — inspect the fixed BoxBrain workspace;
- `git-sync authorize-network` — explicitly authorize a clone or fast-forward-only fetch of `FormatX66/BoxBrain` branch `aurum/trunk-v0.01`;
- `git-auth` — read a GitHub token without echo and keep it only in Git's in-memory credential cache for one hour;
- `git-promote authorize-network confirm-push` — after a successful self-build, commit and push only the allowlisted generated chain-state checkpoint.

The Git surface has no arbitrary repository URL, ref, path, command, commit message, or shell argument. Sync refuses dirty workspaces, merge commits, non-BoxBrain origins, and network access without the exact authorization token. Promotion separately requires `confirm-push`, a self-build tied to the current commit, and changes restricted to `Projects/Codelation/autobuild/native_chain_state.json`.

Self-builds emit per-suite and per-generation progress plus a 15-second heartbeat. The physical and serial consoles share a process lock, so they cannot replay the same build concurrently. Each verified generation is written atomically; a restarted build resumes a compatible checkpoint, and an unchanged external-prerequisite block returns the verified cached result immediately.

On the updated x86 image, the first sequence is:

```text
git-sync authorize-network
seed
self-build
git-status
```

Pushing the verified checkpoint is optional and separately authorized:

```text
git-auth
git-promote authorize-network confirm-push
```

## Guided installation

Boot the ISO in UEFI mode and enter:

```text
install
```

Aurum ignores the USB boot device, read-only disks, mounted disks, undersized
disks, and unsupported transports. Each remaining internal disk is shown with
its model, size, existing partition labels, and a short confirmation command.
Nothing is written during this step.

To install, type the exact command displayed for the intended disk, for example:

```text
install confirm ERASE-12AB34CD
```

The code is derived from that disk's current device path, serial, and size. A
stale, mistyped, missing, or ambiguous code is refused after a fresh disk scan.
The fixed installer then creates a GPT, a 512 MiB FAT32 EFI System Partition,
and an ext4 Aurum root partition; copies the verified live runtime; installs the
UEFI fallback loader without changing firmware NVRAM; verifies required boot
and runtime files; flushes the disk; and tells the user to power off and remove
the USB. This is deliberately a whole-disk install, not a partition editor or
dual-boot workflow.

The current v0.01 live ISO uses a RAM-backed writable overlay unless it finds a Debian live persistence volume. The boot configuration requests a uniquely labelled `AURUM_PERSIST` volume so it cannot consume an unrelated live persistence disk. Prepare that volume as ext4 with filesystem label `AURUM_PERSIST` and place a root-level `persistence.conf` containing `/ union` on it. Without that volume, seed/workspace changes last for the current boot only. A rebuilt image contains the new commands; the already-booted original v0.01 console cannot add them to itself because it intentionally exposes no shell or Git endpoint.

The Linux kernel, systemd, Debian live-boot, and existing Linux drivers are scaffolding. They are not the target architecture. Later milestones can replace pieces of this substrate only after Aurum has equivalent verified machine-native capability.

## Build

On Debian/Ubuntu with `live-build` installed:

```sh
sudo ./Projects/AurumPC/build-iso.sh
```

Output:

```text
dist/Aurum-PC-v0.01-amd64.iso
dist/Aurum-PC-v0.01-amd64.iso.sha256
```

The GitHub Actions workflow performs the canonical build and UEFI/QEMU boot smoke test and publishes the ISO only after the boot marker is observed.

## Safety boundary

The default v0.01 boot remains a non-mutating live session. It does not expose
an arbitrary shell, partition editor, package manager, broad network scanner,
or automatic host mutation path through the Aurum console. The only internal
disk mutation path is the fixed guided installer, and it remains inert until an
exact, current, device-specific `ERASE-XXXXXXXX` confirmation is entered. The
installer never accepts an arbitrary device path, never selects USB media, and
never modifies more than the one confirmed whole-disk target. Physical testing
should boot and inspect `install` before entering any confirmation command.
