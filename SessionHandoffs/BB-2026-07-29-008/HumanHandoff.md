# Human Handoff

## What was accomplished

- Added and exercised a guarded Hyper-V restore helper for the exact
  `BoxBrain-Windows-Lab` VM and `clean-linked-2026-07-29` checkpoint.
- Added `LAPTOP-EBD8CG8P\bruce` to **Hyper-V Administrators**. A new Windows
  sign-in is required before non-elevated processes receive that membership.
- Implemented BrainConnect `keyboard_sequence`: two to eight bounded text/key
  steps inside one certificate-pinned RDP connection.
- Added a fixed Windows process verifier restricted to the direct
  `10.12.194.0/24` lab link and the existing `boxbrain-link` identity.
- Passed 59 controller tests, 6 experiment-runner tests, 10 Flutter tests,
  Flutter analysis, and all 5 native tests on both amd64 and arm64.
- Promoted BrainConnect controller/native revision `eabc3d3` to the Pi. The
  installed control SHA-256 is
  `135ee649c8b40ed39b1e09138aad1461d7998d36e8251c75f366b91a42b1ea4e`.
- Ran three bounded persistent input sequences. FreeRDP transport succeeded,
  but the independent Notepad check remained false.
- Isolated the remaining fault: Explorer and `rdpclip` were in Windows session
  1 while new RDP attempts created or reached LogonUI processes in other
  sessions.
- Rotated a controller token immediately after accidental diagnostic exposure
  and passed the full authenticated service verification with the replacement.
- Disabled execution, removed the service drop-in and all encrypted RDP
  credentials, deleted the temporary runner, restored the clean checkpoint,
  and re-probed the unchanged RDP certificate without authentication.
- Published BrainConnect commits `eabc3d3` and `593daa0` in draft pull request
  12 and updated BoxBrain draft pull request 3 through commit `b6fc745`.

## Decisions made

- Represent related text/key work as one bounded operation and one pinned RDP
  connection, not as an unbounded remote desktop session.
- Keep the verifier fixed and read-only; do not turn the diagnostic SSH
  identity into a controller shell adapter.
- Stop adjusting key timing and chords. The evidence now requires investigation
  of Windows session ownership, reconnection, and unlock behavior.
- Keep UAC as the administrator approval boundary for checkpoint restoration,
  while granting the operator lasting Hyper-V group membership for later
  non-elevated checks.

## Current blockers

- BrainConnect does not yet bind input to the Explorer session. Transport can
  succeed while Windows presents LogonUI in another session.
- Verified cursor/text state and observation-only frames remain unavailable.
- Shell, pointer button, scrolling, and clipboard execution remain unavailable
  at the native boundary.
- The new Hyper-V group membership will not enter the current desktop token
  until the operator signs out and signs back in.

## Immediate next step

Use an authorized guest diagnostic to map Windows session IDs to users and
inspect Terminal Services logon/reconnect events plus the
single-session-per-user policy. Then make the smallest session-selection or
unlock change, repeat one Notepad sequence, verify process presence, remove
credentials, and restore the checkpoint.

## Long-term objective

Run repeatable, independently verified computer-use experiments against the
exact disposable Windows VM while keeping every credential ephemeral, every
state transition audited, and both the Pi and VM clean between runs.
