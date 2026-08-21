# Aurum Voice Status

This is the durable repository mirror for voice chats and other read-only assistants.

**Preferred live source:** `https://aurum.arkmatx.com/voice-status`

**Machine-readable live source:** `https://aurum.arkmatx.com/voice-status.json`

**No-secret static text source:** `https://raw.githubusercontent.com/FormatX66/BoxBrain/main/Web/Aurum-Arkmatx/voice-status.txt`

**No-secret static JSON source:** `https://raw.githubusercontent.com/FormatX66/BoxBrain/main/Web/Aurum-Arkmatx/voice-status.json`

**Repository fallback:** `FormatX66/BoxBrain/AURUM_VOICE_STATUS.md`

## Voice instruction

When Bruce says **“Read Aurum Voice Status”**, read the live source when reachable. If the Arkmatx host is unavailable, read the no-secret static text/JSON source or this repository file. Report only the evidence recorded there. Do not upgrade a capability because a plan, manifest, workflow name, or package declaration exists.

## Current plain status

All seven everyday human capabilities are now **Defined, Executable, Tested, and Seeded on BBPI4**. The Pi deployment validated the seven bundles over the pretrusted USB-C SSH path and returned `PI4_SEED_OK`. The next shared evidence gate is **Booted** from a generation that already contains these capabilities; physical user-facing use remains after that.

**Human action:** None right now. PC seed construction, boot verification, and the next Pi generation proof are automated build work.

## Evidence standard

A capability advances only through these gates:

1. **Defined** — the requirement and stable trait identity exist.
2. **Executable** — runnable implementation code exists.
3. **Tested** — functional tests passed against the implementation.
4. **Seeded** — a verified seed instance or built artifact contains the capability.
5. **Booted** — a verified seed generation booted with the capability already present.
6. **Used** — a physical user-facing operation was proven on an authorized machine.

A green manifest or documentation check is only **Defined**. A package listed in a build script is not **Seeded** until the seed or finished artifact is inspected and verified. Deploying into an already-running seed earns **Seeded**, not **Booted**.

## Everyday human capabilities

| Trait | Capability | Current gate | Honest status | Next proof |
|---|---|---:|---|---|
| `TR8:WEB` | Web browsing | 4/6 | Browser-launch runtime is tested and the complete human-trait payload is verified on BBPI4. The PC seed definition also includes Firefox ESR, but its fresh artifact/boot proof is still pending. | Boot a generation that already contains WEB, then prove a webpage opens. |
| `TR8:FILES` | Garden / Files | 4/6 | Garden and its Documents, Photos, Music, Videos, Downloads, Projects, and Shared plots are in the verified Pi seed payload. | Boot with Garden already present, then open and save a real file. |
| `TR8:MEDIA` | Music, photos, and video | 4/6 | Unified media launch behavior and its seed bundle are verified on BBPI4. Provider playback proof is still pending. | Boot with MEDIA present, then prove image, audio, and video playback. |
| `TR8:WRITE` | Writing and word processing | 4/6 | Document creation/editor behavior and the WRITE seed bundle are verified on BBPI4. LibreOffice Writer remains wired into the PC seed definition. | Boot with WRITE present, then create, edit, save, and reopen a document. |
| `TR8:INTENT` | Intent and assistance | 4/6 | Everyday-language routing and the INTENT seed bundle are verified on BBPI4. | Boot with INTENT present and prove a typed or spoken request opens the intended capability. |
| `TR8:CONNECT` | Wi-Fi, Bluetooth, USB, and network | 4/6 | Connectivity probing and the CONNECT seed bundle are verified on BBPI4 over the trusted USB-C route. | Boot with CONNECT present and exercise network, USB, and Bluetooth through the human surface. |
| `TR8:RECOVER` | Diagnosis, repair, and rollback | 4/6 | Read-only recovery inspection and the RECOVER seed bundle are verified on BBPI4; deployment itself preserved rollback and added no persistence. | Boot with RECOVER present and prove a safe user-visible diagnosis/rollback path. |

## System milestones

- **Executable human-trait runtime — verified.** Runtime code, functional tests, seven parallel bundle builds, and complete seed-payload assembly exist on `main`.
- **Pi human-trait seed — verified.** Run `32525836598` completed at 2026-08-21 20:54 UTC from source commit `e7d7a8db…`, after validating and deploying all seven bundles with the gold seed preserved.
- **PC seed integration definition — implemented, awaiting fresh proof.** The active PC seed branch includes Firefox ESR, PCManFM, MPV, LibreOffice Writer, Xorg/Openbox, Garden, and all seven trait bundles.
- **Booted gate — not yet earned.** The verified Pi payload was added to an already-running seed; the updated PC/Pi generation must boot with the traits already present.
- **Physical use gate — not yet earned.** WEB, Garden, MEDIA, WRITE, INTENT, CONNECT, and RECOVER still need user-facing physical receipts.

## Recent corrective work

- Implemented the executable Aurum human-trait runtime.
- Replaced contract-only lanes with artifact-producing parallel builds.
- Embedded runnable human capabilities into the active PC seed definition.
- Wired bounded human-trait deployment into Pi seed reconciliation.
- Fixed the Windows-to-Linux installer line ending failure (`bash\r`) and re-proved the Pi seed successfully.
- Added regression guards that prevent contract-only checks or stale pre-integration workflow runs from being reported as progress.
- Updated the dashboard and live voice mirror to use the six-gate evidence standard.
- Added no-secret static text, JSON, and browser-readable mirrors that do not depend on Arkmatx deployment credentials.

## Canonical source relationships

- `Web/Aurum-Arkmatx/voice-status-snapshot.json` is the durable dynamic-web fallback.
- `Web/Aurum-Arkmatx/voice-status.php` adds current public GitHub workflow and commit evidence when the Arkmatx PHP host is available.
- `Web/Aurum-Arkmatx/voice-status.txt` and `voice-status.json` are no-secret public static mirrors.
- `Web/Aurum-Arkmatx/voice-status/index.html` is a browser-readable static view.
- `Web/Aurum-Arkmatx/dashboard.html` consumes the JSON form of the same status model.
- This file is the GitHub-readable fallback for voice chats using the GitHub connector.

Last durable snapshot: **2026-08-21 20:54 UTC**.
