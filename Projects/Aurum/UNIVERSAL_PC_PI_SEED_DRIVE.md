# Aurum Universal Boot Seed

## North-star goal

Build **one physical Aurum boot drive that can carry the seed to as many supported machines and architectures as practical**.

Informal shorthand: **one boot drive to rule them all**.

The drive is not one monolithic OS image. It is a self-describing multi-architecture seed carrier with multiple boot frontends and machine-specific phenotype payloads behind one shared semantic Aurum lineage.

When inserted into a supported machine, the boot firmware sees the frontend it understands, Aurum identifies the machine/architecture, selects or materializes the appropriate phenotype, and preserves all machine-specific state under that node's identity.

The first two physical targets are:

- x86-64 UEFI PCs such as Hopper
- Raspberry Pi 4 ARM64

They are the beginning of the universal carrier, not its final scope.

## Architectural rule

**One seed. Many boot frontends. Many phenotypes. One lineage.**

Architecture-specific kernels, firmware helpers, device trees, bootloaders, drivers, and compatibility roots are implementation material. The durable identity is the shared Aurum seed, capability semantics, provenance, recovery data, lineage, and construction knowledge.

A machine must never be forced to consume another architecture's payload merely because both live on the same drive.

## Target boot families

The carrier should be extensible rather than hard-coded to only two machines. Candidate boot families include:

- x86-64 UEFI
- x86 legacy BIOS where still useful
- ARM64 UEFI systems
- Raspberry Pi firmware boot
- additional ARM boards with board-specific firmware/device-tree adapters
- future architectures such as RISC-V when stable boot/runtime support is available

Supporting a new platform means adding a bounded boot adapter plus phenotype construction knowledge, not creating a separate Aurum identity.

No claim is made that one drive can boot literally every historical computer. The north-star requirement is that **one physical carrier should boot every Aurum-supported platform whose firmware can reasonably consume that carrier**.

## Shared boot-partition concept

A shared FAT-compatible boot area can contain non-conflicting boot conventions side by side, for example:

- `EFI/BOOT/BOOTX64.EFI` for x86-64 UEFI removable media
- future architecture-specific UEFI removable loaders where appropriate
- Raspberry Pi boot files such as `config.txt`, firmware/device-tree files, and ARM64 kernel material
- architecture-neutral seed manifest and generation metadata

Firmware selects what it understands; Aurum then selects the matching phenotype.

## Proposed logical layout

1. `AURUM_BOOT` — shared boot/front-door partition
   - architecture/firmware-specific boot adapters
   - minimal discovery/bootstrap code
   - generation selector and recovery entry
   - architecture-neutral seed manifest

2. `AURUM_PAYLOADS` — architecture/board phenotype store
   - x86-64 payload
   - ARM64/Pi payload
   - future platform payloads
   - each payload independently replaceable and checksummed

3. `AURUM_SEED` — architecture-neutral lineage carrier
   - Codelation seed
   - trait/TR8 definitions
   - construction knowledge
   - generation manifests
   - checksums/provenance
   - recovery metadata
   - immutable historical ancestry such as first-playable Echo Rally

4. `AURUM_STATE` — versioned writable state
   - namespaced by node identity
   - hardware models
   - local generation evidence
   - user-approved local personalization
   - never allow one node to overwrite another node's machine state

The physical implementation may initially use separate partitions for x86 and ARM roots if that is simpler/recoverable. The logical contract above matters more than the exact partition count.

## Boot behavior

### x86-64 PC

UEFI finds the removable x64 loader, loads the x86 bootstrap, identifies the machine, then boots/materializes the x86 Aurum phenotype. Pi/other-platform files are ignored.

### Raspberry Pi 4

Pi firmware reads its boot files, loads the ARM64 bootstrap and Pi device-tree/firmware material, identifies BBPI4, then boots/materializes the Pi phenotype. x86 boot material is ignored.

The Pi must already permit the relevant boot medium in EEPROM `BOOT_ORDER`; persistent EEPROM changes remain gated until current configuration is inventoried and rollback is known.

### Future supported machine

Its firmware consumes the appropriate frontend. If the seed already contains a compatible phenotype, it boots it. If Aurum has sufficient construction knowledge but no ready phenotype, the long-term design allows the seed to materialize/cache one using an authorized build path, then record that adaptation into lineage.

## Discovery before phenotype

The universal carrier should progressively minimize assumptions before machine identification. Early bootstrap should determine only what is needed to choose a safe next stage, such as:

- CPU architecture
- firmware/boot family
- board/system identity
- available memory
- storage topology
- display/input availability
- network capability
- known-good hardware compatibility path

Missing facts are blockers, not values to invent.

## Current constraint

The present Hopper seed is produced as an amd64 ISO-hybrid. Raw-writing that ISO consumes the drive as an x86-focused image layout, so it cannot simply have Pi files copied onto it and reliably become universal.

The universal carrier must be intentionally constructed as a disk image containing all required frontends/payloads and the shared seed/state contracts.

## Build sequence

1. Preserve the current working PC seed artifact/checksum and Hopper proof.
2. Complete read-only inventory of the actual plugged seed drive and BBPI4.
3. Build the ARM64/Pi phenotype independently.
4. Build a universal-carrier constructor rather than architecture-specific raw writers.
5. Validate the image off-media:
   - partition/filesystem structure
   - boot adapters present for each declared platform
   - architecture payload separation
   - shared seed checksums/provenance
   - node-state isolation
   - recovery path
6. Flash only the explicitly identified seed drive.
7. Re-prove x86 boot on Hopper.
8. Prove ARM64 boot on BBPI4.
9. Record both physical proofs in the same generation manifest.
10. Add future platforms by boot-adapter/phenotype modules without replacing the universal seed identity.

## Self-updating carrier

Long term, the drive should be capable of safely refreshing itself while preserving known-good generations:

observe machine -> identify supported boot family -> select/materialize phenotype -> validate -> cache signed/checksummed generation -> preserve rollback -> contribute scoped evidence to lineage

A failed platform adaptation must not damage payloads that already boot other machines.

## Recovery rule

The universal seed must remain useful even when one phenotype fails. Boot adapters, phenotype payloads, shared seed data, and machine state are independently recoverable.

A bad ARM candidate must not break x86 recovery. A bad x86 candidate must not destroy Pi boot. No new platform is allowed to overwrite the last known-good universal front door without a tested rollback.

## Success levels

- **U0:** same physical drive boots Hopper x86-64 and BBPI4 ARM64.
- **U1:** same drive carries a shared Gen1 Aurum shell/traits across both while keeping machine-specific lineage separated.
- **U2:** new supported hardware can be added through modular boot adapters/phenotypes without redesigning the whole carrier.
- **U3:** the seed can safely identify, materialize, validate, cache, and recover machine-specific phenotypes with minimal human intervention.

## North-star interpretation

The drive is a physical expression of Aurum's generational genetics:

**Preserve the seed; adapt the phenotype to the machine.**

The user should eventually need to know only one thing: plug in the Aurum seed. The machine-specific boot mechanics are Aurum's problem, not theirs.
