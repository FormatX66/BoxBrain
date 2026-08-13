# Aurum Field v0

Aurum Field is a machine-oriented logical storage capability. It deliberately does not model disks, sectors, clusters, files, directories, tables, databases, or application-owned stores. Those remain optional carrier mechanisms beneath the field.

## Core model

The collection is a **field**. The field contains immutable **grains**. A grain is not located by path or offset; it is identified by the digest of its canonical meaning. Grains may refer to other grains, forming relationships without requiring co-location. A field may be partial, merge with another field, and later become complete when missing referenced grains arrive.

A field identity is derived from the sorted set of grain identities. Therefore insertion order, carrier record order, disk block placement, file name, host, and transport chunking are not semantic properties.

## Grain kinds

- `fact`: an observed or supplied value.
- `relation`: a relationship among grain identities or values.
- `capability`: declarative data describing something Aurum can do, accept, and provide. It is not executable code.
- `view`: a named or meaningful perspective into a field.

The kinds are one-byte semantic tags in v0. New kinds require a format revision rather than silently changing meaning.

## Canonical value encoding

Aurum Field v0 uses its own small typed binary grammar rather than JSON inside the field:

`00 null | 01 false | 02 true | 03 signed-integer | 04 bytes | 05 UTF-8 text | 06 32-byte reference | 07 list | 08 canonical map`

Lengths and integers use unsigned varints; signed integers use zig-zag mapping. Map entries are ordered by the canonical binary form of their key, making the same logical map encode identically regardless of construction order.

## Identity

A grain identity is BLAKE2s-256 over:

`"AURUM-FIELD-0\0" || kind-byte || canonical-body`

A field identity is BLAKE2s-256 over:

`"AURUM-FIELD-ID-0\0" || sorted(grain-id...)`

The digest primitive is intentionally standard cryptography; the semantic format, canonical grammar, identity domains, merge rules, and carrier independence are Aurum Field rules. Inventing new cryptography is outside this storage experiment.

## Carrier projection

When the field must cross a conventional boundary, each grain can be projected as an independent record:

`AFG0 || version || kind || body-length || grain-id || canonical-body`

The record offset is not part of the grain or field identity. Records can be reordered. Duplicate records collapse. A damaged carrier region can be skipped by locating and validating the next self-identifying record. A projection is a transport artifact, not the field itself.

The same grains could later be carried as webhost objects, RAM pages, Git blobs, network frames, shared memory, or another physical substrate without changing their identities or relationships.

## Capability model

Aurum should treat software-shaped boundaries as implementation carriers rather than conceptual ownership boundaries. A capability grain says what is accepted, what is provided, and relevant traits. The current Python file is only the v0 reference carrier used to prove the field rules; it is not the definition of the capability.

## v0 safety boundary

This experiment stores and relates data only. Capability grains are declarative and do not authorize or execute commands. Existing Aurum JSON/JSONL state remains authoritative and untouched. The first field is deliberately separate until the format proves stable enough for a migration experiment.
