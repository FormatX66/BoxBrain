# Master TODO

## P0 — Repository integrity

- [x] Create the canonical BoxBrain indexes.
- [x] Register the existing BrainConnect repository.
- [x] Establish non-duplication and session-handoff rules.
- [x] Add structural and Markdown-link validation.
- [x] Confirm BoxBrain and BrainConnect remote repository URLs.
- [ ] Confirm project owners and priority ordering.
- [ ] Clarify the purpose and current assets for Arkmatx.

## P0 — BrainConnect

- [x] Implement the authenticated live event stream.
- [x] Specify observation-target identity and allowlisting.
- [x] Select an observation-only FreeRDP plugin boundary.
- [x] Define evidence retention and redaction policy.
- [x] Implement the durable target registry and audited enable/disable API.
- [x] Gate task creation on enabled target UUIDs.
- [x] Add the Flutter target registration and approval workflow.
- [x] Implement the certificate-probe process protocol and identity-mismatch
  handler.
- [x] Add the Flutter certificate-probe workflow.
- [x] Implement the native out-of-process FreeRDP certificate helper.
- [x] Build and synthetic-test the helper for amd64 and arm64.
- [x] Package and install the helper on the Kali Raspberry Pi 4.
- [x] Verify the installed checksum, ownership, provenance, and host-runtime
  synthetic boundary test.
- [x] Deploy and configure the FastAPI controller on the Raspberry Pi.
- [x] Verify authentication, USB-only binding, private state, helper integrity,
  emergency-stop persistence, and hardened service restart behavior.
- [x] Live-test exact-match, certificate-rotation, unreachable, timeout, and
  no-authentication behavior through a protocol-faithful Pi RDP/NLA fixture.
- [x] Build, isolate, verify, and checkpoint a disposable full Windows VM.
- [x] Register the clean VM disabled by default and independently record its
  RDP certificate fingerprint.
- [x] Prove the existing certificate gate against the full Windows target.
- [x] Define the capability-first disposable-VM boundary.
- [x] Add the durable, audited open-profile operation queue for shell,
  keyboard, pointer, and clipboard work.
- [x] Add Flutter forms for every queued operation type.
- [x] Implement the fixed, disabled-by-default VM execution protocol and
  durable operation state machine.
- [x] Add exact certificate recheck, deterministic subprocess fixture, restart
  recovery, and transient Flutter result display.
- [x] Implement the first native VM connector for absolute pointer movement
  with post-pin, target-bound systemd credential lookup.
- [x] Build and synthetic-test the control artifact for amd64 and arm64.
- [x] Consolidate the guarded native Pi installer for control promotion.
- [x] Run control identity and credential-negative fixtures on the Pi's exact
  FreeRDP 3.26 runtime.
- [x] Provision encrypted target-bound systemd credentials and install the
  reviewed connector while leaving execution disabled.
- [x] Add bounded Unicode text and fixed allowlisted key or chord input.
- [x] Run exact-target pointer and keyboard operations through a short,
  audited enablement window.
- [x] Disable the executor, remove the execution drop-in, delete encrypted
  target credentials, and verify controller health after the live run.
- [x] Prove one live pointer click with independent visual evidence.
- [x] Record bounded results and before/after evidence for every executed
  operation.
- [x] Restore and verify `clean-linked-2026-07-29` after the first live control
  experiment.
- [x] Keep one bounded RDP session active across a related input sequence.
- [x] Add a restricted Windows process verifier and exercise it after a live
  sequence.
- [x] Map Windows RDP session ownership, reconnect events, and unlock state.
- [x] Bind the native input connection to the intended Explorer session.
- [x] Independently prove Task Manager and Notepad process state after
  keyboard sequences.
- [x] Add independent frame or guest-state verification for the keyboard and
  pointer-button live proofs.
- [x] Specify and implement bounded, redacted, observation-only frames.
- [x] Rotate the disposable lab credential after diagnostic exposure and
  create/restore `clean-linked-rotated-2026-07-29`.
- [x] Refuse controller upgrades while the live execution drop-in is enabled.
- [x] Implement source-complete, coordinate-bound pointer scrolling as the
  next native capability.

## Daytime operator-input queue

- [x] Confirm pointer scrolling as the next native capability.
- [x] Confirm that FreeRDP 3.15 builds plus exact Pi 3.26 host gates remain the
  compatibility contract for the next run.
- [ ] Confirm whether the click-and-type Notepad proof should become a fixed
  automated acceptance scenario.
- [x] Keep the retired `clean-linked-2026-07-29` checkpoint untouched unless
  its deletion and merge plan receives explicit approval.

## Nightshift queue - resource intensive

- [x] Run the full controller and Flutter analysis/test suites.
- [x] Repeat native warnings-as-errors builds and all tests for amd64 and
  arm64.
- [x] Exercise the new disabled-upgrade preflight against the Pi before
  promoting a controller revision.
- [x] Repeat the exact FreeRDP 3.26 on-host compatibility gates.
- [x] Promote coordinate-bound scrolling only after the build and Pi gates.
- [x] Restore `clean-linked-rotated-2026-07-29`, capture a bounded before
  frame, run one bounded scroll, capture an after frame, independently verify
  the effect, clean the Pi, and restore the checkpoint.

The ordered details and stop conditions are recorded in
[session BB-2026-07-29-011](../SessionHandoffs/BB-2026-07-29-011/ExecutionPlan.md).

The scrolling-specific continuation is recorded in
[session BB-2026-07-29-012](../SessionHandoffs/BB-2026-07-29-012/ExecutionPlan.md).

## BoxBrain Pi Drive transport

- [x] Implement root-folder-restricted Pi Google Drive synchronization for
  service snapshots, diagnostics, and guarded patch staging.
- [x] Install checksum-verified rclone and deploy BoxBrain 0.10.0 to the live
  Pi with a verified private rollback archive.
- [x] Complete one-time Pi OAuth enrollment as `boxbrainprime@gmail.com`
  without retaining credential-bearing output.
- [ ] Verify completion of the first low-impact historical timer run.
- [ ] Create a dedicated BoxBrain Google OAuth client and reconnect rclone
  before the shared client ID retires.
- [ ] Exercise one checksum-valid, non-executing patch delivery against a
  disposable authorized target and verify its Drive receipt.

## Headless Windows keystroke bootstrap

- [x] Add a preview-first, fixed-command USB-HID bootstrap with exact local
  authorization and no credential or arbitrary-text input.
- [x] Require hash verification of the Pi-served Windows link helper and
  key-only SSH proof before reporting success.
- [ ] Decide and review the live Pi composite-gadget HID configuration; do not
  change the deployed USB networking gadget until that daytime decision.
- [x] Extend the source-only composite gadget with a standard three-button
  relative mouse at `/dev/hidg1` while preserving keyboard and `usb0`.
- [ ] Choose the bounded Bluetooth pairing-window trigger and trusted-host
  policy before implementing or advertising Bluetooth HID.
- [ ] Exercise one authorized disposable Windows target with an unlocked admin
  console, then verify the restricted SSH link and restore the target.

Detailed implementation work belongs in the canonical
[BrainConnect roadmap](https://github.com/FormatX66/BrainConnect/blob/main/docs/ROADMAP.md).

## P1 — Ecosystem discovery

- [ ] Locate or define WebsiteBuilder.
- [ ] Locate or define AgentFramework.
- [ ] Locate or define WebsiteCluster.
- [ ] Locate or define Automation.
- [ ] Create Security and Research repositories only when implementation work
  begins.

## P2 — Operations

- [x] Configure remote origins.
- [x] Complete review and merge of the BoxBrain organization branch.
- [x] Add CI for repository validation.
- [ ] Define release and archive procedures.
- [ ] Define Docker, Raspberry Pi, VM, and cloud deployment matrices.
