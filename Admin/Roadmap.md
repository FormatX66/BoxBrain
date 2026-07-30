# BoxBrain Roadmap

## Completed — Repository foundation

- Establish the canonical structure and source-of-truth rules.
- Register BrainConnect without copying its code or documentation.
- Add global indexes, dependency maps, validation, and session handoffs.
- Confirm and configure the canonical remote URLs.

## Completed — BrainConnect live events

- Authenticated first-message WebSocket connection
- Cursor resume and reconnect from the latest audit sequence
- HTTP polling fallback with sequence deduplication
- Browser-origin validation and local end-to-end verification

## Completed — BrainConnect observation design

- Define target identity and audited, disabled-by-default allowlisting.
- Select an out-of-process, observation-only FreeRDP adapter.
- Define bounded evidence retention and redaction rules.
- Keep keyboard, mouse, and shell execution disabled.

See the canonical [BrainConnect roadmap](https://github.com/FormatX66/BrainConnect/blob/main/docs/ROADMAP.md).

## Completed — BrainConnect target registry

- Durable target records with immutable UUIDs and additive schema migration
- Audited register, inspect, enable, and disable operations
- Exact SHA-256 RDP server-certificate confirmation before enablement
- Enabled-target admission checks for every new task
- Flutter registration, review, approval, and disable workflow
- Credentials excluded from target records

## Completed — BrainConnect certificate-probe boundary

- Fixed, out-of-process helper invocation with no command shell
- Strict, versioned, bounded JSON response protocol
- Server-certificate comparison without credentials or a desktop session
- Atomic disablement and audit record after an identity mismatch
- Flutter probe action and last-verification display
- Deterministic process, timeout, protocol, mismatch, and audit tests

## Completed — BrainConnect native FreeRDP helper

- Pinned a Debian 13, FreeRDP 3.15.x, CMake, GCC, and OpenSSL build baseline.
- Implemented strict arguments, bounded JSON, X.509 parsing, and an internal
  hard deadline.
- Required exact NLA/HYBRID server selection and rejected TLS-only downgrade.
- Forced certificate rejection before authentication or `PostConnect`.
- Built and synthetic-tested amd64 and Raspberry Pi-compatible arm64 images.

## Completed — BrainConnect Raspberry Pi 4 helper deployment

- Connected to the Pi 4 over its direct USB gadget network with strict SSH
  host-key checking.
- Verified Kali 2026.2 arm64 and exact `libfreerdp3-3` runtime version
  `3.26.0+dfsg-1`.
- Ran the full synthetic certificate boundary test on the Pi before install.
- Installed the reviewed ELF root-owned with checksum and content-addressed
  provenance.
- Changed no package version, repository, or package hold on the Pi.

## Completed — BrainConnect Raspberry Pi 4 controller deployment

- Packaged an exact Git revision as a wheel with locked runtime dependencies.
- Installed the release and plugin manifests under immutable `/opt` paths.
- Ran the controller as a locked `brainconnect` systemd service account.
- Bound the authenticated API only to `10.12.194.1:8000` on direct USB.
- Kept the generated token and SQLite database mode `0600` in a mode `0700`
  state directory outside Git.
- Verified HTTP 401 rejection, helper checksum, emergency-stop persistence,
  restart recovery, and systemd hardening.

## Completed — BrainConnect Pi RDP identity live lab

- Ran a protocol-faithful RDP/NLA certificate fixture on Pi loopback.
- Verified exact certificate match and explicit target enablement.
- Rotated the certificate on the same endpoint and verified atomic disablement.
- Verified bounded unreachable and timeout responses.
- Confirmed no authentication, desktop session, or TLS application data.
- Fixed the minimal FreeRDP runtime environment and fail-safe upgrade path.

## Completed - BrainConnect disposable desktop target

- Built a Generation 2 Windows 11 Enterprise Evaluation Hyper-V VM.
- Isolated the VM on the Raspberry Pi USB network.
- Verified RDP at `10.12.194.9:3389`.
- Provisioned a non-administrator, public-key-only, Pi-only SSH boundary.
- Completed a bounded Pi-originated healthy read-only diagnostic.
- Gracefully powered off and created Standard checkpoint
  `clean-linked-2026-07-29`.

See the [Hyper-V Windows lab runbook](../sandbox/hyperv/README.md).

## Completed - BrainConnect full Windows certificate gate

- Recorded the active RDP listener certificate through Hyper-V PowerShell
  Direct and the guest certificate store.
- Registered `10.12.194.9:3389` disabled by default.
- Proved the existing native helper exact-match gate without credentials or a
  desktop session.
- Verified append-only register, identity-match, and enable audit events.
- Enabled the exact target only after the independent identity matched.

## Completed - BrainConnect open-lab operation queue

- Defined a capability-first experiment for the exact disposable Windows VM.
- Retained exact-target containment, immutable audit, emergency stop, hard
  operation limits, bounded shell timeouts, and checkpoint recovery.
- Added durable typed operations for shell, keyboard text and keys, pointer
  movement/buttons/scrolling, and clipboard read/write.
- Added Flutter forms and queued-operation health visibility.
- Kept the control plugin disabled and `executor_enabled = false`.

## Completed - BrainConnect disabled execution boundary

- Defined a fixed, versioned subprocess request/result protocol.
- Passed operation and target data through bounded standard input, not process
  arguments.
- Re-probed the exact RDP certificate before every execution claim.
- Added atomic containment rechecks and truthful running/terminal states.
- Persisted only result metadata while returning output text transiently.
- Recovered interrupted running operations as `failed/interrupted`.
- Passed every operation kind through a packaged no-action subprocess fixture.
- Added gated **Run next**, status chips, and transient result display in
  Flutter.

## Completed - BrainConnect native pointer connector

- Built one headless FreeRDP executable for canonical absolute pointer moves.
- Added bounded Unicode text and fixed allowlisted key or chord input.
- Required exact NLA/HYBRID endpoint and certificate match before credential
  lookup.
- Selected target-UUID-bound systemd runtime credentials.
- Rejected loose credential files, symlinks, malformed requests, unsupported
  operations, and out-of-desktop coordinates.
- Disabled gateway, reconnect, clipboard, drive, device, audio, printer,
  smart-card, and file redirection.
- Passed five native tests on both amd64 and arm64.
- Installed the content-addressed arm64 connector on the Pi and retained it
  inert between bounded runs.

## Completed - BrainConnect Pi pointer and keyboard transport

- Consolidated native probe and control promotion without duplicate
  deployment logic.
- Passed control identity and credential-negative fixtures on the Pi's exact
  FreeRDP 3.26 runtime.
- Installed the content-addressed input artifact and used encrypted,
  target-bound systemd credentials.
- Added bounded Unicode text and fixed allowlisted key or chord input.
- Proved exact-target authentication and successful FreeRDP submission for
  pointer, text, and key events.
- Disabled execution, removed its service drop-in, deleted all encrypted RDP
  credentials, and verified controller health afterward.

## Completed - BrainConnect persistent input evidence

- Added and exercised a guarded exact-checkpoint restore helper.
- Added two-to-eight-step keyboard sequences inside one pinned RDP connection.
- Added a fixed, read-only Windows process verifier.
- Promoted the sequence artifact and controller revision to the Pi.
- Used the first failed proof to isolate Explorer to session 1 and the new
  attempts to LogonUI sessions.
- Rotated the exposed controller token, removed all execution credentials, and
  restored the clean checkpoint after the run.

## Completed - BrainConnect verified RDP keyboard control

- Mapped RDP session ownership and Terminal Services authentication and
  reconnect events.
- Bound the target-local account to `BB-WIN-LAB` and requested the existing
  console session.
- Forced slow-path input and rejected suspended input.
- Passed six native tests on both amd64 and arm64 and seven runner tests.
- Independently proved that keyboard sequences launched Task Manager and
  Notepad.
- Disabled execution, removed credentials and temporary runners, and restored
  the exact clean checkpoint.

## Completed - BrainConnect bounded frame and pointer-click proof

- Added memory-only bounded frame transport with verified region, PPM, cursor,
  Base64, byte-length, and pixel-hash fields.
- Verified visible keyboard text and one coordinate-bound pointer click by
  inserting a later marker at the clicked Notepad caret position.
- Rotated the disposable lab credential after diagnostic exposure and created
  and restored `clean-linked-rotated-2026-07-29`.
- Returned the Pi to inert state with no drop-in, encrypted credentials, or
  temporary runners.

## Completed - BrainConnect upgrade safety preflight

- Added a read-only controller upgrade preflight before wheel construction,
  artifact upload, or service mutation.
- Refuse an enabled execution drop-in even if the service is inactive.
- Require authenticated inert health and an armed emergency stop when the
  installed controller is active.
- Added focused refusal, success, health, ordering, and installer parse tests.

## Next - BrainConnect remaining native operations

- Coordinate-bound, ten-step-limited scrolling is source-complete.
- Cross-build, exact Pi-runtime gate, and independently observed live scroll
  proof remain queued for nightshift.
- Shell and clipboard remain separate later capability expansions.
- Align or compatibility-gate the FreeRDP build and Pi runtime versions.
- Define controlled dashboard credential provisioning without committing or
  broadly copying the Pi's long-lived token.

## Later — Shared ecosystem services

- Establish AgentFramework contracts when a repository is authorized.
- Promote shared security controls into the Security project.
- Add reproducible Research benchmark definitions.
- Register WebsiteBuilder, Arkmatx, WebsiteCluster, and Automation sources as
  they are discovered.
- Prepare Docker, Raspberry Pi, VM, and cloud deployment tracks only after
  their software dependencies are proven.

## Long-term objective

Operate BoxBrain as a searchable, auditable coordination system for multiple
projects, models, agents, repositories, and deployment environments.
