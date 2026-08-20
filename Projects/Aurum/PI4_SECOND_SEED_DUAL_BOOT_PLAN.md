# Aurum Pi4 Second-Seed Dual-Boot Plan

## Purpose

Use BBPI4 as Aurum's second physical node now that Hopper has crossed the first real graphics/input proof boundary.

The Pi4 is not an x86-64 substitute; it is a more demanding portability test. Hopper is x86-64, while BBPI4 is ARM64. A successful Aurum phenotype on both proves that the durable seed is capability/semantic architecture rather than a machine-specific image.

## Existing Pi role to preserve

BBPI4 currently serves the BoxBrain/Kali/rescue role. That role remains valuable and must stay recoverable. Aurum must therefore coexist with the existing Pi environment rather than overwrite it as the first step.

## Preferred dual-boot model

Use separate bootable media/partitions so the existing Kali/BoxBrain environment remains known-good while Aurum ARM64 develops beside it.

Preferred order:

1. Preserve and inventory the existing Pi boot/storage layout before writes.
2. Build an ARM64 Aurum seed independently of the current Pi installation.
3. Place Aurum on separate boot media or a dedicated partition; do not overwrite the known-good Kali root.
4. Add a reversible boot-selection layer only after both sides boot independently.
5. Default behavior during development should keep the existing BoxBrain/Kali path recoverable.
6. Aurum state, lineage, and machine model remain separate from the compatibility OS filesystem.

A two-media implementation (existing Kali/BoxBrain media plus Aurum USB/secondary media) is acceptable as the first dual-boot phenotype because it preserves rollback with the smallest storage risk. A unified boot menu can follow after independent boot proof.

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
- Produce a signed/hashed inventory receipt.
- Make no storage changes.

### P1 — ARM64 seed builds off-machine

- Build/validate the Pi4 Aurum seed artifact.
- Boot-test in an ARM virtual/emulated lane where useful, without treating emulation as physical proof.

### P2 — Independent physical Aurum boot

- Put the Aurum ARM seed on separate media or dedicated free space.
- Boot BBPI4 into Aurum without touching the known-good Kali root.
- Prove local display or authorized remote console, networking, exact-machine identity, and self-build.

### P3 — Reversible dual boot

- Make both Kali/BoxBrain and Aurum selectable/recoverable.
- No boot path may depend on deleting the other.
- Preserve one-shot rescue behavior and BoxBrain's existing rescue/KVM role.

### P4 — Shared Gen1 phenotype

- Materialize the same core Aurum shell semantics and initial traits on Pi4.
- Allow visual implementation to adapt to the Pi's capabilities rather than forcing pixel-identical output.
- Confirm lineage can distinguish shared inherited traits from Hopper- or Pi-specific adaptations.

## Gen1 interpretation

BBPI4 may satisfy Gen1's **second physical node / cross-architecture seed portability** gate once the same semantic seed produces a usable physical Aurum phenotype on ARM64.

A later second x86-64 PC remains useful for measuring same-architecture portability, but lack of a second PC should not block Gen1's architecture-neutral evolution work now.

## Safety boundary

Do not repartition, overwrite, replace the Kali/BoxBrain root, alter Pi EEPROM boot order, or make another persistent boot change until P0 inventory proves the target and an explicit reversible plan exists. Build artifacts and read-only inspection can proceed automatically.

The objective is not merely "Aurum runs on a Pi." The objective is to prove that one Aurum lineage can express itself across materially different machines while preserving each machine's known-good recovery path.
