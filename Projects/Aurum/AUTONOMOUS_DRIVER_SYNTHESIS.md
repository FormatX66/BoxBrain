# Aurum Autonomous Driver Synthesis

## Goal

Aurum should be able to learn how a hardware component works and progressively build, test, verify, and maintain its own driver/interface for that exact hardware.

The preferred path is not "generate C from a datasheet." Aurum should collate independent evidence from the physical design, published documentation, existing proven drivers, firmware, operating-system hardware descriptions, and controlled observations of the real device.

## Core model

Aurum treats a driver as a verified behavioral model of a device:

`hardware identity + reachable states + registers/commands + memory/DMA mappings + interrupts/events + timing + power/reset behavior + verified actions + confidence`

Aurum may emit a conventional driver when compatibility requires one, but its long-term native representation can be a smaller machine-oriented hardware capability model.

## Evidence sources

For each detected component, gather as available:

1. PCI/USB/ACPI/Device Tree or other hardware identity data.
2. Vendor datasheets and programming/reference manuals.
3. Electrical schematics and reference-board designs.
4. Existing Linux/BSD/other legally usable reference drivers.
5. Firmware source, example code, initialization scripts, and protocol descriptions.
6. Known errata, revision notes, quirks, and board-specific information.
7. Live observations from authorized local hardware.

No single source is automatically assumed to be correct. Aurum should retain provenance and compare sources against one another.

## Build loop

1. **Identify**
   - Fingerprint the exact device, silicon revision, board wiring, firmware revision, bus, addresses, interrupts, DMA capabilities, clocks, reset lines, and dependencies.

2. **Collect**
   - Retrieve and index available documentation and reference implementations.
   - Build a hardware knowledge graph linking device IDs, chip families, manuals, schematics, drivers, firmware, errata, and known behaviors.

3. **Extract behavior**
   - Convert human documentation and reference-driver logic into a common state/transition model.
   - Record which registers, commands, memory regions, interrupts, timing rules, and state changes each source claims.

4. **Compare**
   - Cross-check schematic/datasheet claims against known-good driver behavior.
   - Flag contradictions, undocumented behavior, compatibility workarounds, and uncertain assumptions instead of silently choosing one source.

5. **Characterize safely**
   - Begin with passive/read-only enumeration and observation.
   - Prefer emulation, virtual hardware, traces, or a sacrificial test target before writes to physical hardware.
   - Advance to reversible operations only after prerequisites and recovery paths are verified.

6. **Synthesize**
   - Generate a minimal candidate interface for the exact detected hardware.
   - Reuse known-good behavior where appropriate, while removing unrelated compatibility baggage only when verification proves it unnecessary.

7. **Verify**
   - Compare candidate behavior with the reference implementation and expected hardware state transitions.
   - Test initialization, normal operation, error handling, reset/recovery, power transitions, concurrency, DMA boundaries, interrupts, and shutdown.
   - Record confidence per behavior rather than using one global pass/fail guess.

8. **Promote gradually**
   - Generation 0: known-good existing driver/reference.
   - Generation 1: Aurum compatibility translation/wrapper.
   - Generation 2: Aurum hardware-specific implementation.
   - Generation 3: optimized Aurum-native hardware model.
   - Generation 4: where the architecture permits, direct native capability use without a conventional generic driver abstraction.

9. **Keep fallback**
   - Preserve a known-good reference driver or recovery path until the Aurum-generated implementation has passed the required validation gates.
   - Roll back automatically when a generated implementation violates verified invariants.

10. **Relearn on change**
   - A new silicon revision, firmware version, board wiring, kernel/OS interface, bus topology, or relevant hardware change invalidates only the affected confidence domains and triggers targeted re-characterization.

## Confidence model

Confidence is attached to individual claims and behaviors. Example:

- register 0x40 bit 3 -> DMA enable: 0.987
- interrupt vector -> transfer complete: 0.999
- register 0x44 -> descriptor base address: 0.931

Aurum should retain supporting evidence, test history, hardware/firmware fingerprint, and contradictions for every promoted claim.

## Safety gates

The autonomous path must distinguish observation from operations that can damage or permanently alter hardware.

### Allowed early stages

- enumerate buses and device identity
- read standard configuration spaces and documented read-only registers
- parse documentation and existing source
- analyze traces/logs
- emulate candidate behavior
- compare outputs with a known-good driver

### Require stronger validation and explicit recovery

- arbitrary MMIO/PIO writes
- DMA programming on physical hardware
- clocks, voltage, thermal, reset, or power-controller changes
- flash/NVRAM/EEPROM writes
- firmware replacement
- fuse/OTP/security-state operations
- operations that can overwrite storage or corrupt persistent device state

Irreversible or potentially destructive operations must never be used simply to increase model confidence.

## First implementation milestone

Build the pipeline against one well-documented, inexpensive device with:

- public datasheet/programming documentation,
- public schematic/reference design if possible,
- a mature open-source driver,
- easy replacement/recovery,
- straightforward observable I/O.

The first success criterion is not replacing the reference driver immediately. It is proving that Aurum can independently reconstruct a behavioral model, predict the reference driver's important interactions, generate a minimal candidate implementation, and pass tests in emulation or a controlled target.

## Long-term outcome

When Aurum encounters supported or partially unknown hardware, it should increasingly be able to answer:

`What is this? -> What evidence describes it? -> What does it actually do? -> What interface does this exact machine need? -> Can I prove my implementation behaves correctly?`

The end state is plug-and-learn hardware: Aurum progressively builds and maintains its own verified drivers/interfaces rather than depending permanently on hand-installed static driver packages.
