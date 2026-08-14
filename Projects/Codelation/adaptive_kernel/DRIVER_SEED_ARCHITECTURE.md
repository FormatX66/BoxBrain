# Aurum Driver Seed Architecture v0

## Core rule

Drivers are generated kernel capabilities, not durable driver files.

The Aurum Kernel Seed owns the semantic knowledge needed to construct a device capability. When hardware appears, Aurum identifies the device and its machine/bus context, materializes the smallest bounded driver capability needed for that attachment, verifies it, and binds it. When the device disappears, Aurum unbinds the capability and reclaims its executable realization.

The durable object is the device contract plus verified construction knowledge. The machine-specific executable driver is disposable.

## Lifecycle

ATTACH -> OBSERVE -> IDENTIFY -> RESOLVE DEVICE CONTRACT -> MATERIALIZE -> VERIFY -> BIND -> OPERATE

DETACH -> QUIESCE -> UNBIND -> RECLAIM

A later reattachment starts from the semantic device contract again. Aurum may reuse verified construction knowledge and proof identities, but it does not require a permanently installed driver binary.

## Expand and contract

The running Aurum kernel is capability-shaped around the hardware that actually exists now.

- A newly observed peripheral adds a bounded driver capability after verification.
- A removed peripheral releases its device-specific executable capability after safe quiescence.
- Shared bus, memory, interrupt, DMA, scheduler, security and protocol capabilities remain only while still required by another active dependency.
- Kernel capability accounting is reference/dependency based so removing one device cannot remove infrastructure still required by another.

This is logical kernel expansion/contraction. It does not require unsafe arbitrary rewriting of a monolithic executing image. Generated capability capsules may be materialized into protected executable memory or another verified kernel execution domain and reclaimed when no longer needed.

## No conventional driver-update model

Aurum should not depend on installing successive versions of persistent driver packages.

Instead, improvements update the Kernel Seed's semantic knowledge, device-contract knowledge, construction rules and verification rules. The next attachment rematerializes the driver from the improved knowledge.

So there is no conventional `old-driver-file -> download-new-driver-file -> install` lifecycle. There can still be updates to the durable knowledge used to construct drivers; security fixes and corrected protocol knowledge must remain possible.

## Device knowledge layers

A driver seed separates durable device meaning from machine realization:

1. Device protocol contract
   - identities and compatible revisions
   - registers or command protocol only when supported by authoritative evidence
   - state transitions
   - queues/buffers
   - timing constraints
   - firmware interaction
   - error and reset behavior
   - power-state behavior

2. Bus/interface contract
   - PCI/PCIe, USB, I2C, SPI, platform, virtual bus, or future carrier semantics
   - enumeration and addressing
   - discovery/configuration semantics

3. Machine realization
   - MMIO realization
   - memory ordering
   - interrupt realization
   - DMA/IOMMU realization
   - cache coherency
   - atomics and synchronization
   - native instruction lowering

4. Kernel capability contract
   - permissions
   - ownership
   - resource limits
   - isolation
   - scheduler interaction
   - memory mappings
   - failure containment

The same durable device contract can therefore produce different physical driver realizations on different machines.

## Existing drivers as bootstrap knowledge

During bootstrap, existing Linux/upstream/vendor drivers may be used as evidence and a behavioral roadmap. Aurum should extract reusable semantic knowledge from them rather than treating the compiled `.ko` file as the permanent source of truth.

Priority:

1. identify an already understood device contract;
2. reuse verified semantic/construction knowledge;
3. derive knowledge from a trusted existing driver/source and authoritative hardware documentation;
4. create a new bounded device-contract research frontier only when evidence is incomplete.

## Unknown hardware safety boundary

Aurum must never invent hardware facts merely to make a driver compile.

It must not guess:

- register maps;
- DMA descriptor layouts;
- firmware commands;
- interrupt acknowledgement semantics;
- destructive reset sequences;
- voltage/power behavior;
- timing requirements;
- privileged device authority.

Missing physical semantics are a local blocked frontier. Other kernel/device work continues.

A newly generated driver capability is eligible to bind only after its required evidence and verification gates pass.

## Verification ladder

A generated driver should progress through bounded stages:

1. semantic-contract validation;
2. dependency and authority validation;
3. machine-realization validation;
4. static construction checks;
5. deterministic model/simulator tests where available;
6. isolated execution/sandbox checks where available;
7. bounded hardware trial with rollback/recovery path;
8. promotion to current-session device capability.

Compile success alone is never proof of driver correctness.

## Kernel Seed relationship

The Kernel Seed contains the rules for constructing both the kernel core and attached-device capabilities.

Conceptually:

KERNEL SEED
  + MACHINE CONTRACT
  + CURRENT DEVICE GRAPH
  + VERIFIED DEVICE KNOWLEDGE
  -> CURRENT MATERIALIZED KERNEL

The materialized kernel is therefore a function of the machine and the currently attached capability graph, not a fixed collection of kernel and driver files.

## Target end state

The flash medium carries durable Aurum semantic state and the minimum bootstrap needed to discover a machine. It does not need a permanent catalog of architecture-specific driver binaries.

At runtime:

attach -> identify -> materialize -> verify -> bind

detach -> quiesce -> unbind -> reclaim

The kernel grows and shrinks with the physical machine while the Kernel Seed remains the durable source of meaning.
