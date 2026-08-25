# TinySeed Self-Build Lifecycle

Status: **North-star bootstrap contract; first physical bridge-kernel evidence exists, autonomous end-to-end growth remains unproven**

## Core rule

**TinySeed starts the whole Aurum self-build process.** It is the smallest
trusted initiator, not a small copy of the finished operating environment.

The lifecycle is:

```text
universal seed carrier
  -> generic discovery boot
  -> establish networking and an authorized cloud/local build route
  -> identify machine species
  -> load or build and install TinySeed + first-boot kernel
  -> reboot
  -> exact machine discovery under the first-boot kernel
  -> establish Soil, Field, and Slush
  -> pull the first build-seed instructions
  -> build the full Aurum phenotype in an inactive slot
  -> reboot into an adaptive-kernel trial
  -> verify and promote, or roll back
```

The machine-readable phase contract is
`Projects/Aurum/Germ/SELF_BUILD_LIFECYCLE.json`.

## Universal does not mean one CPU binary

The USB drive is universal at the carrier and lifecycle level. Firmware still
needs a compatible frontend and the CPU still needs a matching bootstrap
kernel. The same drive may therefore contain generic x86-64, ARM64/Pi, and
future boot adapters behind one shared TinySeed lineage.

Each generic bootstrap kernel carries only the broad, proven core drivers
needed to boot, inspect buses, reach safe storage, obtain networking when
available, and install a recovery-capable next stage. Machine-specific
optimization belongs to later phases.

## Network-first construction

Networking is an early bootstrap priority because cloud resources can shorten
source acquisition, configuration search, compilation, testing, and candidate
comparison. TinySeed uses an already-working route immediately. If none exists,
Wi-Fi onboarding is the first interactive connectivity action; Ethernet and
other authorized transports remain valid alternatives.

Once connected, Future Branch selects an attributed build route from available
capabilities, which may combine:

- verified source, artifact, and compiler caches;
- an authorized classical cloud compiler/builder;
- remote test or emulation capacity;
- model-assisted planning;
- an available QPU-backed Future Branch experiment;
- local compilation and hardware validation.

Cloud assistance does not move the trust boundary. TinySeed records the
provider, worker/runtime identity, immutable inputs, outputs, and hashes. The
target independently verifies every returned artifact and must still perform
local boot and health checks. Secrets, unique identity, and private local state
are not build inputs unless a separate explicit policy authorizes them.

Loss of networking is a `waiting` or bounded offline state, not permission to
erase Last Known Good or repeatedly consume cloud resources. The generic
kernel, protected germ, cached first-boot candidate, and recovery path must
remain viable offline. Cloud computing accelerates growth; it must not become a
single point of recovery failure.

## Machine species and machine specimen

Discovery deliberately occurs twice at different depths.

- **Machine species** is the coarse first classification: CPU architecture,
  firmware family, board or platform family, boot transport, storage family,
  and enough memory/network/display facts to choose a safe first-boot kernel.
- **Machine specimen** is the exact second inventory: CPU revisions and
  topology, memory map, buses, every device and revision, firmware, storage,
  network, display, input, accelerators including an available QPU route,
  power/thermal interfaces, and observed compatibility evidence.

The generic USB boot may choose a family-level kernel from species evidence. It
must not claim an exact adaptive phenotype until the internal first-boot kernel
has produced specimen evidence.

## Phase 0: external generic discovery boot

Firmware selects the boot adapter it understands and starts a generic
compatibility kernel from the USB carrier. This phase is recovery-capable and
read-mostly with respect to internal disks until the normal target identity and
write-authority gates have passed.

It must:

1. verify the carrier manifest and bootstrap payload;
2. establish an authorized network route, prioritizing Wi-Fi onboarding when
   no route is already online;
3. record available local, cloud, and QPU-assisted construction capabilities;
4. collect the machine-species record;
5. identify an unambiguous install target without selecting the boot carrier;
6. retain a recovery path and Last Known Good branch;
7. resolve a compatible first-boot kernel candidate.

Candidate resolution prefers an exact hash-verified cached kernel. If none is
compatible, it may build one locally or use an already authorized builder. A
download, build completion, or QPU result alone is not proof; the candidate
must pass artifact verification and a platform-appropriate boot gate.

## Phase 1: install TinySeed and the first-boot kernel

The external environment installs the smallest viable internal organism:

- the protected Reseed Germ;
- the machine-species record and provenance;
- the verified first-boot kernel, initramfs, core drivers, and firmware;
- source/build inputs or a verified route to obtain them;
- resumable network and attributed cloud-build route state without copying
  credentials into receipts;
- a minimal compiler/builder capability when local construction is viable;
- Guardian, recovery metadata, and an inactive candidate slot;
- the compact build-seed instructions needed to resume without the USB drive.

The first-boot kernel becomes the initial internal Last Known Good. TinySeed
does not overwrite another proven organism in place.

## Reboot boundary 1: internal first-boot kernel

The machine boots from internal storage using the first-boot kernel. If this
boot fails, the external generic carrier remains the recovery route.

This stage performs full specimen discovery and begins construction of the
actual Aurum phenotype. It creates or restores:

- **Soil** — durable local substrate for node identity, lineage, immutable
  build inputs, candidate slots, recovery data, and receipts;
- **Field** — machine-native facts, relationships, capabilities, provenance,
  and views, independent of their physical carrier;
- **Slush** — active and reclaimable working memory for observations,
  hypotheses, build state, and Future Branch candidates.

These are working role definitions for the bootstrap boundary. Their storage
formats may evolve without changing the phase contract.

The first-boot system then verifies and pulls the first build-seed
instructions. Those instructions identify immutable genetics/build inputs,
required capability domains, evidence gates, and recovery policy. They do not
grant permission to overwrite the running Last Known Good.

Networking is re-observed after reboot rather than assumed from the external
receipt. When online, the internal builder may resume or create an authorized
cloud-assisted build. When offline, it preserves its checkpoint and performs
only useful local work that does not require repeating an unchanged failed
network request.

## Phase 2: grow the full Aurum phenotype

Using the first-boot kernel and generic drivers, Aurum constructs an inactive
candidate containing:

- the adaptive kernel configured from exact specimen evidence;
- custom or selected hardware drivers and firmware interfaces;
- Slush, Field, and Soil runtime integration;
- the broader Aurum capability/runtime set requested by the genetics;
- independent health probes, build provenance, and rollback metadata.

Future Branch ranks kernel, driver, transport, and build candidates while the
current first-boot kernel remains warm as Last Known Good. An available QPU may
serve as an attributed Future Branch accelerator for bounded candidate
selection or experiments. It is optional: it does not replace deterministic
compilation, artifact hashing, hardware observation, or health verification.

## Reboot boundary 2: adaptive-kernel trial

A running kernel cannot safely transform itself into the finished kernel in
place. The completed phenotype therefore enters an A/B trial boot.

The Guardian independently verifies required boot, storage, memory, device,
network, input/display, thermal, and Aurum-runtime evidence. A healthy
candidate is promoted to the next Last Known Good generation. A failed or
ambiguous candidate is quarantined and the machine returns to the first-boot
kernel automatically.

## Continuing adaptation

After promotion, Aurum continues the same bounded loop:

```text
observe meaningful machine/workload delta
  -> update specimen Field and Slush state
  -> prepare candidate beside Last Known Good
  -> verify in isolation
  -> trial at a safe boundary
  -> promote or roll back
  -> checkpoint a generation only for meaningful capability/evidence change
```

Boot counts, elapsed time, heartbeats, and repeated builds are evidence, not
progress by themselves.

## Required receipts

The lifecycle preserves at least:

- carrier and boot-adapter identity;
- machine-species observation;
- first-boot kernel source/config/artifact identity;
- TinySeed installation and target identity;
- exact machine-specimen inventory;
- build-seed instruction identity;
- full phenotype build inputs and outputs;
- trial health, promotion, rollback, and quarantine results;
- actual processor/runtime/provider attribution for Future Branch or QPU work.

## Current implementation delta

The repository already has a TinySeed installer/germ, generic platform
discovery, protected regrowth and Guardian semantics, a simulated Adaptive
Kernel feedback loop, a self-built Pi 3 kernel with virtual and physical boot
evidence, and a QPU-attributed Future Branch test lane.

The unproven frontier is the autonomous handoff between those pieces:

1. emit a stable machine-species record during external boot;
2. install the physically proven Pi kernel as the internal first-boot LKG;
3. resume automatically after reboot from a durable lifecycle receipt;
4. perform exact specimen discovery;
5. materialize Soil/Field/Slush bootstrap state;
6. build the full adaptive candidate on the machine or an attributed builder;
7. prove the adaptive trial, promotion, and forced rollback on physical
   hardware.
