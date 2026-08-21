# Aurum Voice Status

This is the durable repository mirror for voice chats and other read-only assistants.

**Preferred live source:** `https://aurum.arkmatx.com/voice-status`

**Machine-readable live source:** `https://aurum.arkmatx.com/voice-status.json`

**Repository fallback:** `FormatX66/BoxBrain/AURUM_VOICE_STATUS.md`

## Voice instruction

When Bruce says **“Read Aurum Voice Status”**, read the live source when reachable. Otherwise read this repository file. Report only the evidence recorded here or in the live mirror. Do not upgrade a capability because a plan, manifest, workflow name, or package declaration exists.

## Current plain status

The seven everyday human capabilities now have executable Generation-0 runtimes and functional tests. Fresh seed-artifact, boot, and physical-use proofs are still pending.

**Human action:** None right now. The next gates are automated build and verification work.

## Evidence standard

A capability advances only through these gates:

1. **Defined** — the requirement and stable trait identity exist.
2. **Executable** — runnable implementation code exists.
3. **Tested** — functional tests passed against the implementation.
4. **Seeded** — a verified built seed artifact contains the capability.
5. **Booted** — that verified seed booted with the capability present.
6. **Used** — a physical user-facing operation was proven on an authorized machine.

A green manifest or documentation check is only **Defined**. A package listed in a build script is not **Seeded** until the finished artifact is inspected and verified.

## Everyday human capabilities

| Trait | Capability | Current gate | Honest status | Next proof |
|---|---|---:|---|---|
| `TR8:WEB` | Web browsing | 3/6 | Browser-launch runtime and provider selection are executable and tested. Firefox ESR is wired into the PC seed definition, but fresh artifact proof is pending. | Build the updated seed, inspect it, boot it, and prove a webpage opens. |
| `TR8:FILES` | Garden / Files | 3/6 | Garden creates Documents, Photos, Music, Videos, Downloads, Projects, and Shared plots. File-manager integration is defined but not yet seed-proven. | Verify Garden inside a built seed, then open and save a real file. |
| `TR8:MEDIA` | Music, photos, and video | 3/6 | Unified media launch behavior is executable and tested. MPV and audio foundations are wired into the PC seed definition. | Verify image, audio, and video playback in a booted seed. |
| `TR8:WRITE` | Writing and word processing | 3/6 | Document creation and editor launch behavior are executable and tested. LibreOffice Writer is wired into the PC seed definition. | Create, edit, save, and reopen a document from the booted seed. |
| `TR8:INTENT` | Intent and assistance | 3/6 | Everyday language maps to stable Aurum traits through executable tested code. | Prove a typed or spoken request opens the intended capability. |
| `TR8:CONNECT` | Wi-Fi, Bluetooth, USB, and network | 3/6 | Provider probing is executable and tested. Aurum has older physical connectivity evidence, but not through the new human trait runtime. | Exercise connectivity from the new human surface in a verified seed. |
| `TR8:RECOVER` | Diagnosis, repair, and rollback | 3/6 | Read-only known-good and rollback inspection is executable and tested. The user-facing trait is not yet seed-proven. | Prove safe diagnosis and rollback from the booted human surface. |

## System milestones

- **Executable human-trait runtime — verified.** Runtime code, functional tests, seven parallel bundle builds, and complete seed-payload assembly exist on `main`.
- **PC seed integration definition — implemented, awaiting proof.** The active PC seed branch includes Firefox ESR, PCManFM, MPV, LibreOffice Writer, Xorg/Openbox, Garden, and all seven trait bundles.
- **Pi seed integration definition — implemented, awaiting proof.** The bounded Pi reconciliation path deploys and tests all seven bundles over the pretrusted USB-C SSH carrier with rollback and no new persistence.
- **Previous physical seed proofs — valid but older.** PC-01 `FLASH_OK` and Pi4 `PI4_SEED_OK` prove the earlier seed paths. They do not prove the newly integrated human capabilities.

## Recent corrective work

- Implemented the executable Aurum human-trait runtime.
- Replaced contract-only lanes with artifact-producing parallel builds.
- Embedded runnable human capabilities into the active PC seed definition.
- Wired bounded human-trait deployment into Pi seed reconciliation.
- Added regression guards that prevent contract-only checks from being reported as implementation progress.
- Updated the dashboard and live voice mirror to use the six-gate evidence standard.

## Canonical source relationships

- `Web/Aurum-Arkmatx/voice-status-snapshot.json` is the durable web fallback.
- `Web/Aurum-Arkmatx/voice-status.php` adds current public GitHub workflow and commit evidence when available.
- `Web/Aurum-Arkmatx/dashboard.html` consumes the JSON form of that same live mirror.
- This file is the GitHub-readable fallback for voice chats that cannot reach the website.

Last durable snapshot: **2026-08-21 20:17 UTC**.
