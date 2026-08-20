# Aurum Pi4 Second-Seed Dual-Boot Plan

## Purpose

Use BBPI4 as Aurum's second physical node now that Hopper has crossed the first real graphics/input proof boundary.

The Pi4 is not an x86-64 substitute; it is a more demanding portability test. Hopper is x86-64, while BBPI4 is ARM64. A successful Aurum phenotype on both proves that the durable seed is capability/semantic architecture rather than a machine-specific image.

## Existing Pi role to preserve

BBPI4 currently serves the BoxBrain/Kali/rescue role. That role remains valuable and must stay recoverable. Aurum must therefore coexist with the existing Pi environment rather than overwrite it as the first step.

## Preferred boot model

The preferred Aurum carrier is now **one universal physical seed drive that can boot both x86-64 PCs and Raspberry Pi 4**, as defined in `Projects/Aurum/UNIVERSAL_PC_PI_SEED_DRIVE.md`.

That drive contains one shared boot/seed carrier plus separate x86-64 and ARM64 payloads. Hopper and BBPI4 therefore inherit one semantic seed while booting architecture-specific kernels/root payloads.

For the Pi itself, the existing Kali/BoxBrain environment remains independently recoverable. During development the preferred Pi arrangement is:

1. Preserve and inventory the existing Pi boot/storage layout before writes.
2. Build the ARM64 Aurum payload independently of the current Pi installation.
3. Rebuild the existing Aurum PC seed USB as the universal PC+Pi carrier only after that drive is exactly identified and authorized.
4. Boot BBPI4 from the universal seed without overwriting the known-good Kali root.
5. Keep Kali/BoxBrain as the independent fallback environment.
6. Add a more polished boot-selection layer only after both sides boot independently.
7. Aurum state, lineage, and machine model remain separate from the compatibility OS filesystems.

A separate-media Kali fallback plus universal Aurum USB gives the smallest storage risk and cleanest rollback.

## ARM seed adaptation

The x86 Hopper image itself cannot be reused. The seed must materialize an ARM64 phenotype with Pi4-specific boot and hardware contracts while preserving the same higher-level Aurum semantics.

Shared across Hopper and Pi4:

- Codelation/seed semantics
- generation/lineage model
- TR8/trait identities
- intent-first shell behavior
- recovery/provenance rules
- unattended candidate build/selection logic
- adaptive driver-model architecture

Machine-specific on Pi4:

- ARM64 kernel/bootstrap carrier
- Raspberry Pi firmware/boot layout
- GPU/display initialization
- USB/input/network hardware model
- storage topology and boot selection
- Pi-specific compatibility drivers until native replacements earn trust

## Milestones

### P0 — Observe only

- Confirm current Pi storage devices, boot source, firmware boot order, free space, and active Kali/BoxBrain layout.
- Identify the currently plugged PC seed USB exactly: model, serial, capacity, partition layout and current content hash where practical.
- Produce inventory receipts.
- Make no storage changes.

### P1 — ARM64 seed builds off-machine

- Build/validate the Pi4 Aurum seed artifact.
- Build/validate the universal multi-architecture disk-image constructor.
- Boot-test in ARM/x86 virtual/emulated lanes where useful, without treating emulation as physical proof.

### P2 — Universal seed physical proof

- Rebuild only the explicitly authorized PC seed USB as the universal carrier.
- Prove that exact drive boots x86-64 Aurum on Hopper.
- Prove that same exact drive boots ARM64 Aurum on BBPI4 without touching the known-good Kali root.
- Prove network, local console/display/input, node identity and self-build on the Pi phenotype.

### P3 — Reversible Pi coexistence

- Make Kali/BoxBrain and Aurum both selectable/recoverable through independent media/boot paths.
- No boot path may depend on deleting the other.
- Preserve one-shot rescue behavior and BoxBrain's existing rescue/KVM role.

### P4 — Shared Gen1 phenotype

- Materialize the same core Aurum shell semantics and initial traits on Pi4.
- Allow visual implementation to adapt to the Pi's capabilities rather than forcing pixel-identical output.
- Confirm lineage can distinguish shared inherited traits from Hopper- or Pi-specific adaptations.

## Gen1 interpretation

BBPI4 may satisfy Gen1's **second physical node / cross-architecture seed portability** gate once the same semantic seed and same universal physical carrier produce a usable physical Aurum phenotype on ARM64 and x86-64.

A later second x86-64 PC remains useful for measuring same-architecture portability, but lack of a second PC should not block Gen1's architecture-neutral evolution work now.

## Safety boundary

Do not repartition, overwrite, replace the Kali/BoxBrain root, alter Pi EEPROM boot order, or rewrite the currently plugged PC seed USB until P0 inventory proves the exact target and an explicit reversible plan exists. Build artifacts and read-only inspection can proceed automatically.

The objective is not merely "Aurum runs on a Pi." The objective is to prove that one Aurum lineage and one seed carrier can express themselves across materially different machines while preserving each machine's known-good recovery path.
