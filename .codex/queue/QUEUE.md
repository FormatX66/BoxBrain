# BoxBrain Codex Queue

This is the Git-backed authoritative shared task queue for BoxBrain when Git is reachable.

## Sync model

- Git queue: shared canonical copy when reachable.
- Local queue: `%USERPROFILE%\Desktop\Codex Cue.txt` remains a fully usable offline/usage-cap fallback.
- Completion log in Git: `.codex/queue/COMPLETE.md`.
- Local completion log: `%USERPROFILE%\Desktop\Cue Complete.txt`.
- Runtime state: `.boxbrain/codex-queue-state.json` (do not treat it as the sole authority).
- Actual repository/system state is the final source of truth.

## Run command

When the user says `Codex, run queue` or `run queue`:

1. Load Git `QUEUE.md` if reachable.
2. Load local `Codex Cue.txt`.
3. Load Git `COMPLETE.md` if reachable.
4. Load local `Cue Complete.txt`.
5. Load runtime state if present.
6. Reconcile records by stable task ID.
7. Inspect the actual repository/system before executing.
8. Skip work already verified complete.
9. Resume partial work from the last verified checkpoint.
10. Run outstanding work in dependency/priority/order sequence.
11. Verify acceptance criteria before completion.
12. Sync completion and status updates back to both Git and local storage when available.

## Conflict resolution

Never blindly overwrite one side with the other.

For the same task ID:
- COMPLETE only wins if current implementation still verifies.
- SUPERSEDED wins over older PENDING/IN_PROGRESS records.
- A newer explicit user edit to task requirements must be preserved.
- DEFERRED_USAGE is temporary and must not override a verified COMPLETE state.
- If local and Git differ materially, merge the latest user requirements and preserve history.

If Git is unavailable, continue using the local queue. When Git becomes reachable again, reconcile and push local changes.

## Usage-cap behavior

If required Codex/model/tool usage is unavailable:
- do not spam retries;
- checkpoint current work;
- mark task `DEFERRED_USAGE`;
- keep the local queue usable even if Git cannot be contacted;
- schedule a single local resume for the next legitimate reset/retry window when known;
- on resume, rerun normal preflight before executing;
- sync deferred/completed state to Git when connectivity and usage permit.

## Active tasks

[TASK BB-001]
STATUS: BLOCKED
TITLE: Windows WLAN / Wi-Fi Profile Integration
PRIORITY: HIGH
DEPENDS:
REQUIRES: CODEX, LOCAL_SHELL
CHECKPOINT: 2026-08-08T06:33:15Z — Supported-command interface/profile inventory, credential_available-only boundary, diagnostics/reconnect/recognition integration, CLI, Networks web section, docs, 7 focused tests, and 103-test Pi regression suite completed. Live integration is blocked because Morris PC (DESKTOP-3U8PBEN, 10.12.194.4) is currently offline in the Pi target registry; no reconnect or credential request was attempted.

DESCRIPTION:
Extend BoxBrain with Windows WLAN integration using supported Windows WLAN mechanisms. Inventory wireless interfaces and saved Wi-Fi profiles, integrate them with BoxBrain networking, and keep credentials out of normal inventory/logs.

ACCEPTANCE:
- Detect Windows wireless interfaces and report interface name/GUID, current SSID, state, signal when available, IP, gateway, DNS, authentication, and encryption.
- Enumerate saved WLAN profiles and record profile/SSID, interface, authentication, encryption, auto-connect, and priority/order where available.
- Use supported Windows WLAN mechanisms rather than depending on direct scraping of protected profile files.
- Add structured BoxBrain network inventory with `credential_available` metadata only.
- Integrate profile awareness with diagnostics, reconnect, network recognition, and USB/network recovery workflows.
- Add CLI commands for interfaces, profiles, status, diagnose, and reconnect.
- Add a Networks section to the BoxBrain web console without exposing plaintext passwords.
- Add mocked tests and documentation.
END TASK

[TASK BB-002]
STATUS: BLOCKED
TITLE: Pi 4 One-Shot Rescue USB Boot Mode
PRIORITY: CRITICAL
DEPENDS:
REQUIRES: CODEX, LOCAL_SHELL, HARDWARE
CHECKPOINT: 2026-08-08T06:25:06Z — Guarded state/registry, CLI/web controls, early-boot consumption, USB mass-storage integration, installer wiring, rollback, docs, and 17 focused/96 total edge tests completed. Live Pi hardware check passed (Pi 4, ARM64, one UDC, ConfigFS ready). Blocked before deployment and boot verification because no legitimate rescue image/checksum is available and the live Pi is on older BoxBrain 0.14.1; requires a selected rescue image plus an authorized deployment/reboot window.

DESCRIPTION:
Implement one-shot Raspberry Pi 4 Rescue Mode. When armed, the next Pi boot presents selected rescue media and rescue controls; the following Pi reboot/power cycle automatically returns to normal BoxBrain. Support architecture-aware BoxBrain Kali Rescue and administrator-imported legitimate Windows recovery/install media.

ACCEPTANCE:
- Consumed next-boot state supports normal, rescue:kali, rescue:windows, and rescue:<image-id>.
- Rescue flag resets during early boot so the following boot returns to normal, including after failure.
- Verified rescue image registry tracks SHA-256, architecture, boot compatibility, Secure Boot metadata, and read/write mode.
- Never expose the Pi's actual BoxBrain filesystem as target USB mass storage.
- Kali profile supports architecture-specific ARM64/x86-64 rescue builds as applicable.
- Windows media import and checksum verification supported without storing Microsoft ISOs in Git.
- Rescue CLI/web controls include status, images, arm, cancel, hardware-check, and reboot-normal.
- Backup/rollback and failure-path tests exist before risky boot changes.
END TASK

[TASK BB-003]
STATUS: BLOCKED
TITLE: Rescue KVM + Automated Boot Orchestrator
PRIORITY: CRITICAL
DEPENDS: BB-002
REQUIRES: CODEX, LOCAL_SHELL, HARDWARE
BLOCKED_BY: BB-002

DESCRIPTION:
Integrate KVM into one-shot Rescue Mode using HDMI capture where available and USB HID keyboard/mouse. Build an orchestrator that recognizes POST/UEFI, triggers the temporary one-time boot menu, selects the armed BoxBrain rescue USB, and verifies rescue startup.

ACCEPTANCE:
- Detect/report HDMI capture, HID keyboard/mouse, USB mass storage, and USB networking capabilities.
- Support KVM control during POST, one-time boot menu, rescue startup, and repair sessions.
- Recognize POST/UEFI/boot-menu/rescue/failure/unknown states.
- Maintain configurable manufacturer/firmware profiles and separate boot-menu keys from setup keys.
- Use bounded HID key bursts and visual verification/confidence thresholds where video exists.
- Unknown targets default to Assisted; verified profiles may use Automatic.
- Never automatically alter permanent boot order, Secure Boot, TPM, firmware passwords, SATA/RAID, or firmware security settings.
- Rescue/KVM console shows state, controls, confidence, next action, and `NEXT PI BOOT: NORMAL BOXBRAIN`.
END TASK

[TASK BB-004]
STATUS: BLOCKED
TITLE: KVM Blind Boot Fallback + Learned Target Profiles
PRIORITY: HIGH
DEPENDS: BB-003
REQUIRES: CODEX, LOCAL_SHELL, HARDWARE
BLOCKED_BY: BB-003

DESCRIPTION:
Add conservative blind-boot fallback when KVM video is unavailable. Prefer verified learned target profiles; otherwise use bounded common one-time boot-menu key attempts and timing windows. Learn deterministic boot sequences from successful visually monitored sessions.

ACCEPTANCE:
- Priority: visual KVM, verified learned profile, generic bounded fallback, manual intervention.
- Candidate keys include F12, F11, F9, ESC, and lower-priority F8; none assumed universal.
- Configurable short key bursts, POST/menu delays, bounded attempts, no infinite retry loops.
- Do not blindly use BIOS setup keys such as F2/Delete as normal fallback actions.
- Save verified non-secret target metadata including model, firmware, boot key, timing, navigation, and BoxBrain boot label.
- Avoid arbitrary long blind navigation unless a verified target profile supplies it.
- Verify rescue success through secondary signals where possible.
- Stop automation after bounded failure and fall back to manual control.
END TASK

[TASK BB-005]
STATUS: BLOCKED
TITLE: Rescue Network Recovery Integration
PRIORITY: HIGH
DEPENDS: BB-001, BB-002
REQUIRES: CODEX, LOCAL_SHELL, HARDWARE
BLOCKED_BY: BB-001, BB-002

DESCRIPTION:
Integrate Rescue Mode with BoxBrain networking so the rescue OS establishes an authorized management link back to the Pi. Prefer USB networking, then Ethernet, authorized known Wi-Fi, then a temporary BoxBrain management network where supported.

ACCEPTANCE:
- Rescue OS attempts management connectivity in the defined priority order.
- Integrate authorized WLAN knowledge without exposing secrets in inventory/logs.
- Report target hardware inventory, disk layout, network interfaces, boot state, and basic diagnostics before repair actions.
- Detect rescue-agent connectivity and feed result back to the Boot Orchestrator.
- Preserve existing BoxBrain connectivity and avoid duplicate network-management subsystems.
END TASK

[TASK BB-006]
STATUS: COMPLETE
TITLE: Script-First Task Offload / GPT Usage Reduction
PRIORITY: HIGH
DEPENDS:
REQUIRES: CODEX, LOCAL_SHELL
PROMOTED_FROM: BH-002
CHECKPOINT: 2026-08-08T06:40:23Z — Verified script-first router, versioned registry, bounded execution, Cue/Complete deduplication, metrics, API, documentation, and full controller regression suite.

DESCRIPTION:
Implement BoxBrain/Codex task routing so repetitive, deterministic, data-heavy, or machine-execution work is preferentially handled by local scripts and conventional automation instead of consuming GPT reasoning/context on every step. Use GPT for ambiguity, planning, diagnosis, code generation, and adaptive reasoning; support hybrid workflows where GPT defines or repairs a procedure and scripts perform the routine bulk work.

The router should evaluate whether GPT involvement is actually required before model execution. Preprocess large repetitive inputs locally when practical and return compact structured summaries, diffs, error excerpts, or metadata to GPT. Once a repeated procedure stabilizes, make it eligible for promotion into a tested reusable script/service.

ACCEPTANCE:
- Implement Script vs GPT vs Hybrid classification rules with documented confidence/fallback behavior.
- Identify and migrate a first set of high-volume BoxBrain/Codex tasks suitable for script-first execution.
- Provide a reusable versioned script registry/library with tests, documentation, and defined input/output contracts.
- Scripts return structured machine-readable results suitable for compact GPT review.
- Implement exception-driven escalation so normal paths stay local and ambiguity/failures can escalate to GPT.
- Integrate idempotency and duplicate-work prevention with Cue and Cue Complete state.
- Add security boundaries, permissions, logging, rollback strategy, and human-review gates for high-impact/destructive actions.
- Log whether tasks were handled by Script, GPT, or Hybrid and why.
- Add measurable reporting for GPT usage reduction, execution time, reliability, and error rate where data is available.
- Preserve compatibility with future model-lane routing without requiring BH-001 to be implemented first.
END TASK
