# Agent Handoff

## Current Objective

Make BrainConnect's proven RDP input transport reach the intended Windows
Explorer session and produce one independently verified state change.

## Tasks

1. Start from `clean-linked-2026-07-29` and re-probe the pinned certificate.
2. Map session IDs, usernames, states, and relevant Terminal Services events
   using an authorized read-only guest diagnostic.
3. Inspect Windows `fSingleSessionPerUser`, reconnect, lock, and RDP logon
   behavior without changing policy first.
4. Determine why NLA/PostConnect succeeds while input attempts reach LogonUI
   sessions instead of Explorer session 1.
5. Implement the smallest bounded session-selection or unlock fix.
6. Repeat one Notepad launch/type sequence and independently verify Notepad.
7. Keep transport acceptance and verified state change as separate results.
8. Disable execution, remove credentials, restore the checkpoint, and re-probe
   the certificate.

## Dependencies

- BrainConnect commit `593daa0` on
  `feature/brainconnect-rdp-input-verification`
- BrainConnect draft pull request
  [12](https://github.com/FormatX66/BrainConnect/pull/12)
- Pi deployment source revision `eabc3d3`
- Installed control SHA-256
  `135ee649c8b40ed39b1e09138aad1461d7998d36e8251c75f366b91a42b1ea4e`
- BoxBrain commit `b6fc745` and draft pull request
  [3](https://github.com/FormatX66/BoxBrain/pull/3)
- Pi controller `10.12.194.1:8000`
- Windows target `10.12.194.9:3389`
- Target UUID `0efb72ab-7b55-481a-914b-f689f427dfef`
- Pinned certificate SHA-256
  `42cb09ef4c234542485e307afb32f00c9d0de063bcad077b94397c0a51f209b2`
- Checkpoint `clean-linked-2026-07-29`

## Files affected

- BrainConnect native RDP settings/session handling and native tests
- BrainConnect experiment verifier only if session identity becomes a typed
  verification result
- BrainConnect open-lab, architecture, security, roadmap, and deployment docs
- BoxBrain Hyper-V diagnostics, admin indexes, project index, and handoff

## Required repositories

- `https://github.com/FormatX66/BrainConnect`
- `https://github.com/FormatX66/BoxBrain`

## Verification checklist

- Exact checkpoint restored before and after the run.
- Certificate probe remains matched and unauthenticated.
- Session user/state mapping is recorded before any policy change.
- No arbitrary FreeRDP options, scancodes, or remote shell are introduced.
- Every sequence remains within existing step, text, repeat, and delay limits.
- Notepad is absent before the run and present only after the input sequence.
- Executor window is bounded and audited.
- Execution drop-in and encrypted credentials are removed afterward.
- Controller token never appears in command output.
- Final controller health reports executor disabled and emergency stop armed.

## Suggested commit message

`Fix RDP input session binding`

## Suggested branch

`feature/brainconnect-rdp-session-binding`

## Potential risks

- RDP can lock or create a parallel session instead of reconnecting to the
  intended desktop.
- A Windows policy change can affect all future RDP logons to the lab VM.
- Process presence proves application launch, not correct text content.
- A failed cleanup could retain target credentials or an enabled drop-in.
- A restored checkpoint can change target identity and invalidate approval.

## Estimated completion order

1. Read-only session/event diagnosis
2. Smallest session-routing design
3. Native and controller tests
4. amd64/arm64 artifact gates
5. Checkpoint restore and certificate probe
6. Short live run with independent process proof
7. Credential/executor rollback and final restore
8. Documentation and handoff
