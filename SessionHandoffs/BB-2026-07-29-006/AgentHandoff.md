# Agent Handoff

## Current Objective

Promote the reviewed native `pointer_move` connector to the Kali Pi controller,
keep it disabled until every runtime and credential gate passes, then collect
one bounded live result and independent visual evidence from the exact Windows
VM.

## Tasks

1. Generalize the existing native Pi installer to select `probe` or `control`
   without duplicating deployment logic.
2. Extract the reviewed arm64 control ELF, verify its checksum and architecture,
   and run the control identity and missing-credential fixtures on the Pi.
3. Confirm FreeRDP 3.26 ABI behavior before creating the final install path.
4. Select the dedicated low-privilege Windows RDP account.
5. Create encrypted systemd credentials named for target UUID
   `0efb72ab-7b55-481a-914b-f689f427dfef`.
6. Add a systemd drop-in that loads only those credentials and exposes only
   their directory path to the child adapter.
7. Install the connector root-owned with content-addressed provenance while
   leaving `BRAINCONNECT_OPEN_LAB_ADAPTER_ENABLED` false.
8. Verify the production controller still reports `executor_enabled = false`.
9. Choose and implement bounded before/after cursor evidence.
10. Enable the reviewed path for one manual pointer move, capture result and
    evidence, disable it again, and restore the clean checkpoint.

## Dependencies

- BrainConnect revision `d207694`
- BrainConnect draft pull request
  [10](https://github.com/FormatX66/BrainConnect/pull/10)
- Adapter boundary revision `310c264` and draft pull request 9
- Pi controller at `10.12.194.1:8000`
- Windows target at `10.12.194.9:3389`
- Target UUID `0efb72ab-7b55-481a-914b-f689f427dfef`
- Pi runtime `libfreerdp3-3` `3.26.0+dfsg-1`
- Checkpoint `clean-linked-2026-07-29`
- amd64 ELF SHA-256
  `15c2b1609820285eccbda2da627ef357b8c97a07dc74d8e41b59732b2351ab90`
- arm64 ELF SHA-256
  `9582804c43a9603275cee312022c97f9d090ce72d01a22209156d2643a598266`

## Files affected

- BrainConnect native CMake workspace, pointer connector, credential provider,
  protocol, fixtures, controller child environment, tests, and canonical docs
- Next: BrainConnect native Pi installer, systemd service/drop-in templates,
  Pi verifier, and live-lab runbook
- BoxBrain admin, architecture, project, integration, and session indexes
- BoxBrain `SessionHandoffs/BB-2026-07-29-006/`

## Required repositories

- `https://github.com/FormatX66/BrainConnect`
- `https://github.com/FormatX66/BoxBrain`

## Verification checklist

- Build and test the exact source revision on amd64 and arm64.
- Verify the arm64 ELF checksum before and after transfer.
- Refuse Pi package or ABI drift before install.
- Prove certificate mismatch needs no credential directory.
- Prove a matched certificate with no credential sends no authentication data.
- Reject symlinks, group/world-readable files, control characters, and
  oversized credentials.
- Keep credential values out of arguments, JSON, environment values, logs,
  results, and audit events.
- Keep all FreeRDP redirections disabled.
- Leave the production executor disabled through installation verification.
- Re-probe the exact target immediately before claim.
- Verify the live desktop dimensions bound the requested coordinates.
- Record visual before/after evidence without persisting a raw credential or
  clipboard value.
- Disable the executor and restore the clean checkpoint after the live run.

## Suggested commit message

`feat: promote FreeRDP pointer connector to Pi lab`

## Suggested branch

`feature/brainconnect-freerdp-control-pi`

## Potential risks

- FreeRDP 3.15-built code may expose runtime behavior differences on Kali's
  FreeRDP 3.26 package even though the shared ABI loads.
- An RDP credential can select or create an unexpected interactive session.
- A successful protocol write does not independently prove cursor movement.
- A service drop-in can accidentally broaden credential visibility or survive
  rollback if not managed transactionally.
- Restoring the VM checkpoint may rotate its RDP certificate and disable the
  target.
- Starting another RDP session may change desktop dimensions or displace an
  existing session.

## Estimated completion order

1. Consolidated installer and Pi-local negative fixtures
2. Exact runtime and checksum verification
3. Dedicated account and encrypted systemd credentials
4. Disabled installation and rollback verification
5. Independent cursor-evidence method
6. One manual live pointer move
7. Disablement and checkpoint restoration
8. Documentation, commit, review, and next handoff
