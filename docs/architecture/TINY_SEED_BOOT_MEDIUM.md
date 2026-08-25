# Aurum Tiny Seed Boot Medium

Status: **Implementation v1 in progress; x86 build path implemented, Raspberry Pi image and early-KVM path implemented and require physical proof**

## Purpose

The Tiny Seed is the smallest practical physical Aurum germ carrier. It is not a full Aurum release and it is not meant to preserve a frozen phenotype forever.

Its job is to boot enough trusted substrate to:

1. identify the machine and storage safely;
2. obtain networking (wired automatically, Wi-Fi with one simple choice when needed);
3. install or repair the protected Reseed Germ;
4. fetch current trusted Git genetics;
5. grow the appropriate hardware-family phenotype beside a known-good state;
6. boot the candidate under the Guardian and promote or roll back automatically.

**Git stores the genetics. Tiny Seed carries the germ. The machine grows Aurum.**

## Human flow

The normal setup surface is deliberately only three screens.

### 1. Network

- If wired networking or an existing connection is already online, this screen completes automatically.
- Otherwise show nearby Wi-Fi networks, ask for one password, and connect.
- Offline mode remains possible for germ repair or bootstrap installation. On x86, a verified policy-pinned fallback phenotype may grow into the inactive slot without networking; otherwise current-genetics regrowth is deferred until networking exists.

### 2. Machine

Tiny Seed identifies the architecture, firmware family, existing Aurum installations, and safe install targets.

- If Aurum already exists, prefer **Repair / Reseed**.
- If no Aurum exists, prefer **Install Aurum**.
- If there is one unambiguous safe target, preselect it.
- If multiple disks are plausible, require the human to choose. Never guess a destructive target.
- The currently booted Tiny Seed medium is excluded from install targets.

### 3. Go

Show one plain-language summary and a yes/no confirmation.

- Existing Aurum: install/refresh the protected germ, convert a legacy single runtime to A/B if needed, fetch current genetics, grow the inactive slot, health-test, arm the trial.
- Fresh machine: install the minimal germ substrate, then regrow current genetics before first boot where the platform adapter supports it.

After that, the user removes Tiny Seed and boots normally. The Guardian promotes the candidate only after health evidence; otherwise it returns to LKG.

## Minimal payload

Tiny Seed should carry only what is needed for boot, networking, disk safety, genetics retrieval, and regrowth:

- Linux kernel + initramfs as the temporary hardware compatibility substrate;
- systemd/udev;
- Python 3;
- Git + CA certificates;
- NetworkManager/nmcli;
- Wi-Fi firmware broad enough for common supported hardware;
- block/storage tools (`lsblk`, `blkid`, `parted`, `wipefs`, `rsync`, filesystem tools);
- bootloader tooling required by that boot family;
- `/usr/lib/aurum/germ/*`;
- one tiny setup UI, not a full desktop.

A full browser, office stack, package-development toolchain, and normal desktop environment do not belong in the Tiny Seed unless a specific hardware adapter proves they are required.

## Bootstrap phenotype

Fresh installs start with a deliberately tiny healthy slot A. It exists only to keep the machine viable while the germ grows the current phenotype.

The bootstrap slot is not a historical Aurum release. It is a survival anchor with a trivial self-test. Once current genetics pass the post-boot health gate, the grown candidate becomes LKG.

## Pre-germ legacy bridge

Older Aurum installations such as Hopper Gen 0 predate the protected germ.

When Tiny Seed finds such an installation offline, it:

1. verifies the installed-Aurum marker and bounded console shape;
2. backs up the old console by SHA-256;
3. moves the existing `/opt/aurum` intact into slot A;
4. replaces `/opt/aurum` with the germ-controlled active-slot symlink;
5. installs the germ and Guardian outside the adaptive slot;
6. adds only the bounded `reseed` command to the compatible legacy console;
7. writes a bridge receipt and leaves slot A as LKG.

This is the one-time bridge from pre-germ Aurum to the universal regrowth model.

## x86 PC boot/install adapter

The x86 Tiny Seed build targets amd64 and is intentionally dual-use:

- removable-media boot via UEFI and legacy BIOS where firmware permits;
- fresh internal install with a small BIOS-GRUB partition, FAT32 EFI system partition, and ext4 root;
- both UEFI removable fallback and BIOS GRUB are attempted on install;
- current genetics are grown into the inactive Aurum slot, never copied over the bootstrap LKG in place.

The first physical proof target is Hopper.

## Raspberry Pi / ARM adapter

The same setup/germ code is architecture-neutral. Raspberry Pi media uses a Pi-compatible ARM64 kernel/firmware boot frontend and the same germ payload.

The Pi image pre-creates a locked `aurum` account and masks the vendor first-user wizard, so a headless boot cannot stop before networking. An optional [Aurum Early KVM](AURUM_EARLY_KVM.md) authority bundle can be placed on the boot partition before first boot. The bundle is consumed into the protected root, then a certificate-pinned TLS keyboard/mouse service starts after NetworkManager and before Tiny Seed. Without that physical authority record, no KVM listener starts. HDMI capture remains the independent visual fallback.

Fresh Pi install logic is present for a Tiny Seed that has already booted on a compatible Pi:

- FAT boot partition;
- ext4 root;
- copy the proven live Pi firmware boot tree;
- rewrite `root=` to the new root UUID;
- install the same germ substrate.

Current Pi genetics are presently staged from `aurum/pi3-v0.01`. Local A/B promotion for the Pi runtime remains disabled in `GENETICS.json` until its runtime/health adapter is explicitly proven. Tiny Seed therefore refuses to pretend Pi A/B growth is complete.

## Future platforms

A new platform adds two bounded adapters:

1. **boot adapter** — how Tiny Seed itself starts on that firmware/architecture;
2. **growth/install adapter** — how a candidate phenotype is materialized and health-checked on that family.

The setup UI, genetics protocol, receipts, and safety rules remain shared.

## Safety invariants

- Never overwrite the medium currently booting Tiny Seed.
- Never choose among multiple destructive targets automatically.
- Never replace LKG with an unproven candidate.
- Never activate an unknown genetics schema or germ protocol.
- Resolve every fetched ref to an immutable commit and record it.
- Network access is explicit at the germ boundary.
- A failed candidate is quarantined and cannot silently promote itself.
- Pre-germ bridge patching is anchor-checked and fails closed on an unknown console shape.
- No early-KVM authority file means no early-KVM listener; malformed bundles never activate partial authority.
- Early-KVM input uses pinned TLS plus per-session HMAC/sequence checks and releases all held inputs on disconnect.

## Success criteria

### T0 — contract

- germ compiles;
- manifest validates;
- A/B Guardian tests prove promotion and rollback semantics;
- bridge tests prove bounded/idempotent legacy console migration;
- setup UI compiles.

### T1 — x86 media

- generated Tiny Seed ISO boots in UEFI VM;
- network/setup surface starts automatically;
- boot medium is excluded from target discovery;
- fresh install produces a bootable internal Tiny Seed substrate;
- current x86 genetics can grow into slot B without changing slot A;
- failed candidate returns to slot A.

### T2 — Hopper physical proof

- boot Tiny Seed on Hopper;
- bridge the currently proven Gen 0 installation without data loss;
- `reseed current` grows the current candidate;
- candidate either becomes healthy LKG or automatically returns to Gen 0;
- preserve the existing 64 GB recovery medium as a physical fallback until Tiny Seed earns replacement status.

### T3 — Pi physical proof

- boot the ARM64 Tiny Seed on a Pi;
- connect Wi-Fi through the same three-step setup surface;
- prove certificate-pinned keyboard/mouse control before the setup surface, with USB HDMI capture as the visual cross-check;
- install/repair germ substrate;
- prove Pi-specific candidate growth and rollback before setting `local_ab_slots=true` for ARM64.

## User-facing rule

The intended setup experience is:

**Boot Tiny Seed → connect if needed → choose the machine/disk → Go.**

Everything after that should be genetics, growth, evidence, and recovery—not conventional release management.
