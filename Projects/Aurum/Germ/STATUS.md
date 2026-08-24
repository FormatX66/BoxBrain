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
- A guarded Windows flash path verifies image checksum, requires unique USB serial identity and explicit confirmation, refuses boot/system disks, re-proves identity immediately before write, and performs a full image-length raw readback hash.

## Evidence currently established in repository

- Germ/manifest Python compile and unit-test workflow is defined.
- A/B unit tests cover healthy promotion, failed-candidate rollback, and trial boot-loop rollback.
- Bridge tests cover bounded/idempotent console migration behavior.
- x86 workflow requires both UEFI and legacy BIOS QEMU boot markers before publishing the artifact.
- Pi workflow requires a reproducible, checksum-pinned Raspberry Pi OS Lite ARM64 base and compressed-image verification.
- The current x86 source branch input bootstrap was decoupled from an uninitialized Git workspace so seed-local input startup no longer depends on `/var/lib/aurum/workspace/BoxBrain` existing.
- The prior x86 recovery-payload verifier mismatch was corrected by inspecting `/live/filesystem.squashfs` rather than only the outer ISO filesystem; boot gates were not weakened.
- Source commit `cc016ddf86444ab3e992ec07187802900dca7b56` now has same-revision published x86 and Pi Tiny Seed artifacts.
- x86 artifact `Aurum-TinySeed-amd64.iso` passed build, UEFI boot smoke, legacy BIOS boot smoke, boot-proof marker, recovery-payload inspection and publication. Verified SHA-256: `cd79720c01455125bd766ae321c5e924a4dc2fe7edf8d63739c2c5cd4f47bc87`.
- Pi artifact `Aurum-TinySeed-Pi-arm64.img.xz` passed build, integrity and static recovery-payload verification and publication. Verified SHA-256: `34c19cee54f781c1eac741b6f414447ac2d9d18bbceda214b56eb693e22f451d`.
- The combined handoff reverified both artifact hashes from the same source revision and persisted `Projects/Aurum/Release/latest-tinyseed-handoff.json` with state `READY_TO_FLASH`.
- `READY_TO_FLASH` does **not** mean physically booted or recovery-proven. The next gate is explicit physical flash/readback followed by real hardware boot proof.

## Physical evidence already known

- Hopper Gen0 was freshly reinstalled and physically verified to boot from its internal NVMe.
- Hopper Gen0 built-in selftest passed and its local seed is healthy.
- Hopper Gen0 Git workspace is intentionally not initialized.
- The existing 64 GB Gen0 recovery USB remains the physical fallback and must **not** be overwritten during Tiny Seed testing.

## Unresolved frontier

1. Flash the x86 Tiny Seed artifact to a **different explicitly identified test USB** using the guarded dry-run-first handoff path; require full raw readback verification before declaring the media ready to boot.
2. Physical Hopper proof:
   - boot Tiny Seed;
   - collect Tiny Seed ready + boot-proof evidence;
   - connect network through the setup surface;
   - detect the one existing Gen0 installation and choose Repair/Reseed automatically;
   - install the pre-germ bridge preserving Gen0 as slot A/LKG;
   - grow current x86 genetics into slot B;
   - reboot trial;
   - require fresh selftest + critical-service + physical desktop + input evidence;
   - promote on proof or automatically roll back to Gen0.
3. Prove Guardian forced rollback physically with a deliberately bad disposable candidate while preserving the proven LKG.
4. Flash and physically boot the Pi ARM64 Tiny Seed. ARM64 local A/B promotion stays disabled until a Pi-specific runtime/health adapter is proven.
5. After physical proof, build the combined physical universal carrier so one drive can expose architecture-specific boot frontends while sharing the same germ/genetics protocol.

## State classification

**READY_TO_FLASH / awaiting physical proof** — same-revision x86 and Pi artifacts are published and hash-reverified by the combined handoff. The next boundary is physical media selection and explicit destructive write authority; no claim of physical boot, promotion, or rollback proof has been made yet.
