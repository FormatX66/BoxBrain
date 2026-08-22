# Aurum Generation Naming

Aurum is not presented to people as conventional software releases (`v1`, `v2`, `v3`, and so on).

## Canonical rule

Human-facing Aurum builds, interfaces, checkpoints, receipts, and status surfaces use a **generation plus a named state**.

Confirmed current names:

- **Gen0** — Hopper origin / first physical PC generation.
- **Gen1 polished physical surface** — current named Hopper physical GUI state.

Do not invent future generation names before they are established by the project.

## Compatibility identifiers

Older machine-to-machine schemas that already contain `vN` identifiers may remain temporarily when changing them would break evidence readers or deployed nodes. They are compatibility plumbing, not Aurum product names.

New schemas and migrations should prefer a named generation/state identifier, for example:

`aurum.desktop.gen1-polished-physical-surface`

rather than:

`aurum.desktop.v2`

## Interface rule

No user-facing Aurum surface should display `v1`, `v2`, `v3`, or similar conventional release labels. Display the named generation/state instead.
