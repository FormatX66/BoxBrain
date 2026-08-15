# Aurum PC v0.01

Aurum PC v0.01 is the first x86-64 PC-loadable experiment for Aurum. It deliberately uses a minimal Debian Linux live system only as a temporary hardware compatibility substrate while exposing Aurum, not a conventional Linux desktop or shell, as the operator surface.

## v0.01 acceptance gate

A build is accepted only when all of the following are true:

1. an amd64 hybrid ISO is produced;
2. the ISO reaches an Aurum console under x86-64 UEFI QEMU;
3. the serial console emits `AURUM_PC_READY`;
4. the bundled Codelation runtime deterministically re-verifies `io_safe_port_choice` through the existing `io-plan` capability;
5. no arbitrary command shell is exposed by the Aurum console;
6. the image can report hardware, current Aurum chain state, Field capabilities, and perform explicit reboot/poweroff.

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
- `self-build` — run the bounded seed/native/self-build core suites, then one deterministic native autonomous-chain event and record its checkpoint;
- `git-status` — inspect the fixed BoxBrain workspace;
- `git-sync authorize-network` — explicitly authorize a clone or fast-forward-only fetch of `FormatX66/BoxBrain` branch `aurum/pi3-v0.01`;
- `git-auth` — read a GitHub token without echo and keep it only in Git's in-memory credential cache for one hour;
- `git-promote authorize-network confirm-push` — after a successful self-build, commit and push only the allowlisted generated chain-state checkpoint.

The Git surface has no arbitrary repository URL, ref, path, command, commit message, or shell argument. Sync refuses dirty workspaces, merge commits, non-BoxBrain origins, and network access without the exact authorization token. Promotion separately requires `confirm-push`, a self-build tied to the current commit, and changes restricted to `Projects/Codelation/autobuild/native_chain_state.json`.

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

The current v0.01 live ISO uses a RAM-backed writable overlay unless it was booted with Debian live persistence. Without a persistence volume, seed/workspace changes last for the current boot only. A rebuilt image contains the new commands; the already-booted original v0.01 console cannot add them to itself because it intentionally exposes no shell or Git endpoint.

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

v0.01 does not install to an internal disk. It is a live ISO. It does not expose an arbitrary shell, disk formatter, partition editor, package manager, broad network scanner, or automatic host mutation path through the Aurum console. Testing on physical hardware should therefore start by booting the ISO from removable media without selecting any installer path.
