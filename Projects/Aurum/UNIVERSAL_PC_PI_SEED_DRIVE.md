# Aurum Universal PC + Pi Seed Drive

## Goal

Make one physical USB drive boot Aurum on both:

- x86-64 UEFI PCs such as Hopper
- Raspberry Pi 4 ARM64

The drive is a multi-architecture seed carrier, not one shared machine image. Each machine boots its own architecture-specific kernel/root while inheriting the same Aurum semantic seed, lineage, recovery metadata, and shared capability definitions.

## Why this is feasible

A single FAT32 boot partition can carry both boot conventions without conflict:

- x86-64 UEFI removable-media loader at `EFI/BOOT/BOOTX64.EFI`
- Raspberry Pi boot files such as `config.txt`, firmware/device-tree files, and an ARM64 kernel image

The remainder of the drive keeps architecture-specific system payloads separate.

## Proposed layout

1. `AURUM_BOOT` — FAT32, shared boot partition
   - `EFI/BOOT/BOOTX64.EFI` for x86-64 UEFI
   - x86 GRUB/config/kernel/initrd references
   - Raspberry Pi 4 firmware/config/device-tree/ARM64 kernel boot files
   - architecture-neutral seed manifest and generation metadata

2. `AURUM_X64` — x86-64 Aurum root/live payload
   - Hopper/PC compatibility substrate
   - never mounted as Pi root

3. `AURUM_ARM64` — Raspberry Pi 4 Aurum root payload
   - Pi-specific compatibility substrate
   - never mounted as x86 root

4. `AURUM_SEED` — architecture-neutral lineage/state carrier
   - Codelation seed
   - trait/TR8 definitions
   - generation manifests
   - checksums/provenance
   - recovery metadata
   - optional immutable first-playable Echo Rally ancestry

5. optional `AURUM_STATE` — explicitly versioned writable state
   - machine-specific state stored under node identity
   - Hopper and BBPI4 must not overwrite each other's machine model/state

## Boot behavior

### On an x86-64 PC

UEFI finds the removable-media x64 loader under `EFI/BOOT/BOOTX64.EFI`. It boots the x86 Aurum payload and ignores the Pi boot files.

### On Raspberry Pi 4

The Pi EEPROM/firmware sees the FAT boot partition, reads the Pi boot configuration, selects the ARM64 kernel/root payload, and ignores the x86 UEFI loader.

The Pi must already permit USB mass-storage boot in its EEPROM boot order. Do not change EEPROM configuration until the current value is inventoried and a reversible plan is recorded.

## Important constraint

The current PC seed is produced as an amd64 ISO-hybrid image. Raw-writing that ISO consumes the drive as an x86-focused image layout. Therefore the existing drive cannot simply have Pi files copied onto it reliably and be called universal.

The universal seed should be rebuilt as a deliberate partitioned disk image from the x86 and ARM artifacts. Converting the currently plugged PC seed drive will require rewriting its partition table/content after the exact device is identified and explicitly authorized.

## Build sequence

1. Preserve current PC seed artifact and checksum.
2. Complete read-only inventory of the plugged seed drive and BBPI4.
3. Build ARM64 Pi seed independently.
4. Build a universal disk-image constructor that creates the layout above.
5. Validate the image without touching physical media:
   - GPT/partition structure
   - FAT boot contents
   - x86 UEFI loader present
   - Pi firmware/config/kernel present
   - architecture payload separation
   - seed checksums and node-state isolation
6. Flash only the explicitly identified seed drive.
7. Physically prove x86 boot on Hopper.
8. Physically prove ARM64 boot on BBPI4.
9. Keep both physical proof receipts in the same generation manifest.

## Recovery

A universal seed must never make one architecture's failure destroy the other's boot payload. Architecture-specific roots are independently replaceable, while the shared seed manifest records ancestry and last-known-good generations.

If one phenotype fails, the drive remains usable to boot/recover the other architecture where hardware permits.

## North-star interpretation

This drive is a physical expression of the Aurum genetics model:

**one seed, multiple phenotypes.**

The USB carries stable meaning/evidence/capability; Hopper and BBPI4 materialize different machine-specific implementations from it.
