# Aurum Reseed Germ / Tiny Seed Status

## Capability

- Genetics protocol v1 is defined at `GENETICS.json`.
- `reseed.py` resolves current trusted genetics to immutable commits and grows x86 candidates into an inactive local slot.
- `guardian.py` preserves LKG, activates trials only at a boot boundary, requires health evidence, quarantines failures, and rolls back deterministically.
- `bridge.py` converts a compatible pre-germ installed Aurum runtime into slot A without replacing it and installs the protected germ outside the adaptive slot.
- The Aurum console bridge exposes bounded `reseed status`, `reseed current authorize-network`, `reseed commit <SHA> authorize-network`, and confirmed rollback operations.
- `tinyseed.py` implements the common three-step external setup surface: Network -> Machine -> Go. A single detected existing Aurum installation is automatically treated as Repair/Reseed; destructive target ambiguity stops safely.
- Fresh Tiny Seed installs carry a minimal bootstrap LKG. If current genetics were not grown before first boot, installed bootstrap mode obtains networking and finishes regrowth rather than requiring a conventional package/update flow.
- x86 Tiny Seed media builder and GitHub Actions build/UEFI+BIOS smoke workflow exist.
- Raspberry Pi ARM64 Tiny Seed image builder and GitHub Actions static build/verification workflow exist.

## Evidence currently established in repository

- Germ/manifest Python compile and unit-test workflow is defined.
- A/B unit tests cover healthy promotion, failed-candidate rollback, and trial boot-loop rollback.
- Bridge tests cover bounded/idempotent console migration behavior.
- x86 workflow requires both UEFI and legacy BIOS QEMU boot markers before publishing the artifact.
- Pi workflow requires a reproducible, checksum-pinned Raspberry Pi OS Lite ARM64 base and compressed-image verification.
- The current x86 source branch input bootstrap was decoupled from an uninitialized Git workspace so seed-local input startup no longer depends on `/var/lib/aurum/workspace/BoxBrain` existing.
- x86 workflow run `32689874198` on source `5c012a616229f2760d7455191eadde759438d12b` passed both UEFI and legacy BIOS boot smoke gates. It then failed the recovery/failure-prep inspection gate before publication.
- That inspection failure was a verifier-layer mismatch: germ/recovery files are intentionally staged into the live root and therefore reside inside `/live/filesystem.squashfs`, while the prior gate searched only the outer ISO filesystem. The gate now extracts and inspects the squashfs without weakening any required payload check, and writes an inspectable payload listing for future diagnostics.
- The Pi Tiny Seed workflow passed on the same earlier source revision. This status change intentionally touches the shared Germ path so both x86 and Pi workflows rerun from one current source revision, preserving the same-revision combined-handoff requirement.

## Physical evidence already known

- Hopper Gen0 was freshly reinstalled and physically verified to boot from its internal NVMe.
- Hopper Gen0 built-in selftest passed and its local seed is healthy.
- Hopper Gen0 Git workspace is intentionally not initialized.
- The existing 64 GB Gen0 recovery USB remains the physical fallback and should not be overwritten during Tiny Seed testing.

## Unresolved frontier

1. Obtain successful same-revision current CI results for the germ contract and both Tiny Seed build workflows, including x86 recovery-payload inspection and artifact publication.
2. Require the combined handoff to reverify both same-source artifacts and persist `READY_TO_FLASH`; do not infer readiness from individual workflow success.
3. Flash the x86 Tiny Seed artifact to a different test USB only after the combined handoff is proven ready.
4. Physical Hopper proof:
   - boot Tiny Seed;
   - connect network through the setup surface;
   - detect the one existing Gen0 installation and choose Repair/Reseed automatically;
   - install the pre-germ bridge preserving Gen0 as slot A/LKG;
   - grow current x86 genetics into slot B;
   - reboot trial;
   - require fresh selftest + critical-service + physical desktop + input evidence;
   - promote on proof or automatically roll back to Gen0.
5. Physical Raspberry Pi proof. ARM64 local A/B promotion stays disabled until a Pi-specific runtime/health adapter is proven.
6. After physical proof, build the combined physical universal carrier so one drive can expose architecture-specific boot frontends while sharing the same germ/genetics protocol.

## State classification

**waiting for same-revision build/publication and physical proof** — x86 UEFI+BIOS boot smoke has been demonstrated on the prior revision, but current artifacts and combined handoff must still pass and publish before any `READY_TO_FLASH` claim.
