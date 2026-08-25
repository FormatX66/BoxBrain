# Aurum Reseed Germ / Tiny Seed Status

## Capability

- Genetics protocol v1 is defined at `GENETICS.json`.
- `reseed.py` resolves current trusted genetics to immutable commits and grows x86 candidates into an inactive local slot.
- `guardian.py` preserves LKG, activates trials only at a boot boundary, requires health evidence, quarantines failures, and rolls back deterministically.
- `bridge.py` converts a compatible pre-germ installed Aurum runtime into slot A without replacing it and installs the protected germ outside the adaptive slot.
- The Aurum console bridge exposes bounded `reseed status`, `reseed current authorize-network`, `reseed commit <SHA> authorize-network`, and confirmed rollback operations.
- `tinyseed.py` implements the common three-step external setup surface: Network -> Machine -> Go. Wi-Fi scan/service failures remain on an actionable retry screen, offline continuation is explicit, and an offline install can join Wi-Fi and resume regrowth before leaving the live console. A single detected existing Aurum installation is automatically treated as Repair/Reseed; destructive target ambiguity stops safely.
- Fresh Tiny Seed installs carry a minimal bootstrap LKG. If current genetics were not grown before first boot, installed bootstrap mode obtains networking and finishes regrowth rather than requiring a conventional package/update flow.
- x86 Tiny Seed also carries one policy-pinned, hash-complete fallback phenotype. When GitHub, DNS, or the network is unavailable, the verified carrier can grow only the inactive slot; the normal preboot test, Guardian trial, health promotion, journal, quarantine, and rollback gates remain mandatory. Online regrowth remains the preferred current-genetics path.
- x86 Tiny Seed media builder and GitHub Actions build/UEFI+BIOS smoke workflow exist.
- Raspberry Pi ARM64 Tiny Seed image builder and GitHub Actions static build/verification workflow exist.
- Pi early KVM now has a boot-partition provisioner, fail-closed first-boot authority consumer, certificate-pinned TLS controller, Linux uinput keyboard/mouse backend, bounded framebuffer evidence, and HDMI-capture fallback. The image pre-creates a locked account and masks the vendor first-user wizard; the KVM service remains inert without explicit physical authority.
- A guarded Windows flash path verifies image checksum, requires unique USB serial identity and explicit confirmation, refuses boot/system disks, re-proves identity immediately before write, and performs a full image-length raw readback hash.
- The current isolated x86 fallback-carrier experiment is draft PR #83. It builds two raw GPT USB candidates from the same protected Tiny Seed germ/live payload and policy-pinned offline phenotype: a systemd-stub UKI virtual reference with known HP physical risk, and an independent systemd-boot -> Debian kernel EFI-stub + separate initrd path intended to avoid the previously observed systemd-stub inner-kernel handoff failure. Neither candidate changes the canonical release or grants physical write authority.

## Evidence currently established in repository

- Germ/manifest Python compile and unit-test workflow is defined.
- A/B unit tests cover healthy promotion, failed-candidate rollback, and trial boot-loop rollback.
- Bridge tests cover bounded/idempotent console migration behavior.
- x86 workflow requires both UEFI and legacy BIOS QEMU boot markers before publishing the artifact.
- Pi workflow requires a reproducible, checksum-pinned Raspberry Pi OS Lite ARM64 base and compressed-image verification.
- The current x86 source branch input bootstrap was decoupled from an uninitialized Git workspace so seed-local input startup no longer depends on `/var/lib/aurum/workspace/BoxBrain` existing.
- The prior x86 recovery-payload verifier mismatch was corrected by inspecting `/live/filesystem.squashfs` rather than only the outer ISO filesystem; boot gates were not weakened.
- **Canonical current artifact identity, source commit, hashes, workflow runs, gate results, next gate, and handoff state live only in `Projects/Aurum/Release/latest-tinyseed-handoff.json`.** Read that file for the current values instead of duplicating them here.
- A handoff may report `READY_TO_FLASH` only after same-revision x86 and Pi artifacts are published and their hashes are reverified by the combined handoff.
- `READY_TO_FLASH` does **not** mean physically booted or recovery-proven. The physical-flash/readback, hardware boot, and forced-rollback gates remain independent evidence.
- Draft PR #83 head `ba4062f435464d6572d8c86f7539af1dbe50c087` is the newest **current-release provenance-locked fallback proof**. Canonical-provenance run `32838156216` passed against the current canonical `READY_TO_FLASH` source `964b12de2ac99ac069a0abf90673ebd77aabb0e0`, requiring the protected Germ, genetics, offline-carrier policy, recovery logic, and recovery trust inputs to match byte-for-byte while allowing only the carrier/loader method to differ. Fallback-matrix run `32838156218` passed the protected Germ suite, built both raw-GPT candidates, cryptographically reverified the embedded offline phenotype from each finished image, and passed OVMF removable-media boot smoke for both loader families while requiring Tiny Seed ready, boot-proof, and network-ready markers. It published `Aurum-TinySeed-amd64-fallback-matrix-experimental` as artifact id `9559809859`, digest `sha256:db44023bfcec25af0b735c97b5a64130102a7b9587290ce79af95e9becde94db`. The canonical Future Branch projector now treats this fallback as warm/current only when provenance matches the current release and the successful matrix receipt is from the same experimental head; a release rollover automatically cools older proof. This is **experimental Passed + Published + provenance-locked** evidence only; it does not promote either fallback, grant write authority, or claim physical HP compatibility. Whole-repository CircleCI on the experiment branch snapshot is not used as part of this proof because its repository-integrity/Future Branch lanes are stale relative to newer main-only state-sync changes.
- The older direct-UEFI offline-carrier PR #78 remains historical evidence and was closed after PR #83 produced the stronger current-head loader matrix.

## Physical evidence already known

- Hopper Gen0 was freshly reinstalled and physically verified to boot from its internal NVMe.
- Hopper Gen0 built-in selftest passed and its local seed is healthy.
- Hopper Gen0 Git workspace is intentionally not initialized.
- The existing 64 GB Gen0 recovery USB remains the physical fallback and must **not** be overwritten during Tiny Seed testing.
- On 2026-08-24, the separate Crayola x86 Tiny Seed physically reached the `READY` console on Hopper, preserved the existing germ as slot A, installed the bridge on `/dev/nvme0n1p2`, and reported `regrow.status=deferred-offline`. This proves the user-visible boot/install boundary and exposed the network-dependent recovery gap addressed by the offline phenotype carrier; it does not replace the pending formal boot-proof marker or Guardian rollback proof.
- Earlier HP PC-01 physical evidence showed the direct systemd-stub/UKI family reaching firmware but failing at the UKI -> embedded-kernel start boundary with `EFI_INVALID_PARAMETER`. The new systemd-boot candidate has only virtual evidence so far; OVMF success must not be treated as proof that this HP-specific physical failure is fixed.

## Unresolved frontier

1. Read `Projects/Aurum/Release/latest-tinyseed-handoff.json` and require state `READY_TO_FLASH` before physical media work.
2. Flash the current x86 Tiny Seed artifact to a **different explicitly identified test USB** using the guarded dry-run-first handoff path; require full raw readback verification before declaring the media ready to boot.
3. Physical Hopper proof:
   - boot Tiny Seed;
   - collect Tiny Seed ready + boot-proof evidence;
   - prefer network through the setup surface, but require the verified offline carrier to remain usable when network or DNS is broken;
   - detect the one existing Gen0 installation and choose Repair/Reseed automatically;
   - install the pre-germ bridge preserving Gen0 as slot A/LKG;
   - grow current x86 genetics, or the explicitly identified pinned offline fallback, into slot B;
   - reboot trial;
   - require fresh selftest + critical-service + physical desktop + input evidence;
   - promote on proof or automatically roll back to Gen0.
4. Prove Guardian forced rollback physically with a deliberately bad disposable candidate while preserving the proven LKG.
5. Flash and physically boot the Pi ARM64 Tiny Seed. ARM64 local A/B promotion stays disabled until a Pi-specific runtime/health adapter is proven.
6. Keep the PR #83 fallback matrix warm but isolated. If Hopper later shows a carrier-specific canonical failure or higher expected total cost, prefer the systemd-boot -> kernel EFI-stub candidate for the next bounded physical compatibility test because it avoids the already-observed systemd-stub inner-kernel boundary. Do not pivot merely because both candidates pass virtually.
7. After physical proof, build the combined physical universal carrier so one drive can expose architecture-specific boot frontends while sharing the same germ/genetics protocol.

## State classification

The canonical classification is the `state` plus `next_gate` in `Projects/Aurum/Release/latest-tinyseed-handoff.json`. Prose in this file intentionally does not duplicate mutable canonical artifact hashes or source revisions.
