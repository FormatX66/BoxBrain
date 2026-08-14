# Aurum Adaptive Machine Kernel v0

## Saved reference milestone

On 2026-08-14 Aurum crossed the first bootstrap milestone: the `aurum/self-kernel-compiler-v0` lane successfully built, boot-tested in QEMU, hashed, and published `Aurum-Kernel-v0.01-x86_64` through the same build-and-boot architecture used by the Aurum OS image lane.

This milestone is intentionally preserved as the reference point for the next Codelation phase. The lesson is that Aurum does not need to reinvent a mature substrate before it can specialize and absorb it. Existing kernels, compiler infrastructure, drivers, and hardware descriptions can be treated as verified guidance/evidence while Aurum progressively replaces the human-language-owned layers with its own machine-native representation.

## Goal

Move beyond separate x86, ARM, or other architecture-specific Aurum kernels.

Aurum should maintain one architecture-neutral machine representation of kernel capability and dynamically materialize the physical instruction sequences required by the machine it is currently running on.

The invariant is:

**one Aurum semantic machine kernel, many physical realizations**

The same raw physical opcode bytes cannot execute unchanged on incompatible processor instruction sets. Therefore the universal part is not an identical native binary. The universal part is Aurum's own binary semantic field plus a minimal machine-discovery/lowering bootstrap that converts verified semantic operations into the physical instructions supported by the observed machine.

## Aurum Machine Field (AMF)

AMF is not intended to be a human programming language or source-code format. It is a canonical binary semantic graph representing machine behavior directly.

Each AMF capability records:

- operation semantics;
- required inputs and produced state transitions;
- memory ordering requirements;
- privilege requirements;
- concurrency/atomicity requirements;
- timing and interrupt requirements where relevant;
- hardware capabilities required;
- verification examples/proofs;
- dependencies on other AMF capabilities;
- fallback/rematerialization information;
- no architecture name unless the physical realization actually requires one.

Example semantic concepts are `atomic-compare-exchange`, `map-page`, `invalidate-address-translation`, `schedule-runnable-context`, `acknowledge-interrupt`, `read-monotonic-counter`, and `transfer-buffer-to-device`. These are semantic capabilities, not x86 or ARM instructions.

## Machine contract instead of architecture label

Aurum should detect a machine as a set of capabilities rather than primarily as an architecture name.

A machine contract can include:

- native word widths;
- register classes/counts;
- endian behavior;
- supported atomic widths and memory-order operations;
- MMU/page-table capabilities;
- address-space and privilege model;
- exception/interrupt model;
- timer/counter facilities;
- SIMD/vector capabilities;
- cache coherency behavior;
- IOMMU/DMA capabilities;
- boot/firmware entry contract;
- buses and discovered devices;
- instruction features actually observed and verified.

`x86_64`, `arm64`, `riscv64`, etc. can remain diagnostic metadata during bootstrap, but are not the primary ownership boundary of the Aurum kernel.

## Bootstrapping path

1. **Seed/recovery boot** — use the known-good generic kernel or firmware-compatible seed only to gain observation and build authority.
2. **Probe** — determine the physical machine contract from safe architectural/firmware/hardware evidence.
3. **Load AMF kernel graph** — architecture-neutral Aurum kernel semantics are loaded from the durable field.
4. **Lower** — each required AMF capability is matched to an already-verified physical realization or synthesized from bounded verified machine primitives.
5. **Verify** — generated physical instructions are tested against semantic examples, privilege constraints, memory-order constraints, and machine-specific conformance tests before promotion.
6. **Materialize** — verified capabilities are assembled into the machine's executable Aurum kernel image/cells.
7. **Trial boot** — the materialized kernel boots in a trial slot while the generic seed remains available as rollback.
8. **Absorb** — successful lowering rules and native capability realizations are cached by machine-contract fingerprint, not merely by CPU brand/model.
9. **Adapt** — newly detected hardware or CPU features trigger only the affected capability fronts, not a complete kernel rebuild.

## Driver model

Drivers follow the same model as the kernel.

A driver is first represented as a semantic device contract: bus transactions, register/state semantics, DMA requirements, interrupt semantics, buffer ownership, firmware protocol, and safety constraints.

Existing Linux/vendor drivers are evidence and guidance for that contract. Aurum may reuse a verified existing driver during bootstrap. As Aurum learns enough of the hardware contract, it can materialize the same driver capability from AMF into machine-native operations for the current machine.

No register map, DMA layout, interrupt behavior, or firmware command may be invented simply to make a driver compile.

## Adaptive lowering

The lowering system should be layered and self-hosting:

- **Stage 0:** existing compiler/kernel infrastructure can generate the first physical realizations.
- **Stage 1:** Aurum records verified semantic-to-machine mappings as binary lowering rules.
- **Stage 2:** Aurum's own bounded native builder composes mappings into larger machine capabilities.
- **Stage 3:** the bootstrap depends only on a very small physical decoder/probe plus AMF, not on a conventional source-language compiler.
- **Stage 4:** where firmware provides sufficient generic execution/boot facilities, the bootstrap can materialize the complete Aurum kernel without carrying a conventional OS toolchain.

The long-term target is not a universal physical opcode stream. It is a universal self-describing semantic kernel whose physical code is rematerialized automatically for whatever execution contract the machine exposes.

## Safety / trust invariant

Aurum must keep these distinctions explicit:

- semantic capability != physical implementation;
- generated physical code != verified physical code;
- verified physical code != permitted hardware authority;
- successful boot != permanent promotion;
- unknown hardware != permission to guess its protocol;
- failed physical lowering blocks only that capability frontier, never unrelated semantic fronts.

## Immediate build fronts

1. Define canonical AMF binary records for machine operations and state transitions.
2. Define a machine-contract schema independent of architecture names.
3. Convert a small set of existing Aurum native VM operations into AMF operations.
4. Build a reference lowering backend that emits verified x86_64 instructions only as the first physical realization, not as the semantic definition.
5. Add a second lowering realization (ARM64) for the same AMF operations and prove both satisfy the same semantic tests.
6. Remove architecture branching above the lowering boundary.
7. Extend AMF to scheduler, memory-management, interrupt, timer, and I/O primitives.
8. Build machine-contract fingerprints and durable realization caches.
9. Assemble a minimal AMF kernel that can boot under the existing seed and then progressively replace seed-owned kernel services.
10. Preserve the 2026-08-14 self-built Linux kernel milestone as the rollback/reference lane throughout this transition.
