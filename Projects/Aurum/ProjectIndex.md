# Aurum Project Index

## Purpose

Aurum is the experimental AI-native operating-system/runtime and self-building capability stack. Its active work includes x86_64 boot/runtime paths, local reasoning, machine-native state, autonomous driver synthesis, self-build, dialogue, human capability traits, physical/virtual hardware validation, protected genetics-driven reseeding, and the minimal Tiny Seed recovery/install front door.

## Current status

Active experimental build. Evidence and readiness are tracked by capability, proof, unresolved frontier, and events rather than by heartbeat or arbitrary iteration count.

## Canonical project documents

- [North-star generational architecture](NORTH_STAR_GENERATIONAL_ARCHITECTURE.md)
- [Genetics and Reseed Germ architecture](../../docs/architecture/RESEED_GENETICS_ARCHITECTURE.md)
- [Mandatory seed recovery architecture](../../docs/architecture/SEED_RECOVERY_ARCHITECTURE.md)
- [Tiny Seed boot medium architecture](../../docs/architecture/TINY_SEED_BOOT_MEDIUM.md)
- [Operator completion contract](OPERATOR_CONTRACT.md)
- [Universal PC/Pi seed-drive north star](UNIVERSAL_PC_PI_SEED_DRIVE.md)
- [Reseed Germ / Tiny Seed evidence status](Germ/STATUS.md)
- [Tiny Seed ranked failure playbook](Germ/FAILURE_PLAYBOOK.md)
- [Stable germ genetics manifest](Germ/GENETICS.json)
- [Stable reseed/regrowth implementation](Germ/reseed.py)
- [Protected A/B Guardian](Germ/guardian.py)
- [Read-only failure triage](Germ/triage.py)
- [Pre-germ compatibility bridge](Germ/bridge.py)
- [Three-step Tiny Seed setup](Germ/tinyseed.py)
- [x86 Tiny Seed builder](Germ/build-x86-tinyseed.sh)
- [Pi ARM64 Tiny Seed builder](Germ/build-pi-tinyseed.sh)
- [Gen1 Everyone-OS execution plan](GEN1_EVERYONE_OS_PLAN.md)
- [Aurum command registry](../../docs/AURUM_COMMANDS.md)
- [Contributor start](START_HERE.md)
- [State authority](STATE_AUTHORITY.md)
- [Autonomous driver synthesis](AUTONOMOUS_DRIVER_SYNTHESIS.md)
- [Helper tasks](HELPER_TASKS.md)
- [Usage bottleneck experiment](usage-bottleneck-answer.md)
- [Aurum dashboard and voice status mirrors](../../Web/Aurum-Arkmatx/README.md)
- [Durable Aurum Voice Status](../../AURUM_VOICE_STATUS.md)
- [Aurum PC Bridge](../AurumBridge/ProjectIndex.md)
- [Codelation seed](../Codelation/ProjectIndex.md)

## Seed/genetics invariant

Git stores the current Aurum genetics. A viable seed carries a protected germ capable of resolving those genetics to immutable commits, growing a hardware-family candidate beside the active organism, preserving the local LKG, and refusing promotion without health evidence. Historical generations remain provenance and recovery targets, not mandatory sequential update steps.

The intended human setup surface is deliberately small: **boot Tiny Seed -> connect networking if needed -> choose repair/install target -> Go**. Architecture-specific boot frontends may differ, but they expose the same germ/genetics lifecycle.

## Process invariant

Aurum may record heartbeat/telemetry as evidence, but only a change in capability, gate, verified state, or unresolved frontier counts as progress and may trigger an immediate continuation build.
