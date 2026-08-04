# Human Handoff

## Accomplished

- Added a source-controlled **BoxBrain Headless Windows** Kali desktop launcher.
- Added a fixed helper that selects exactly one connected `usb0`
  `boxbrain-link` target and opens non-administrator PowerShell-over-SSH.
- Kept strict host-key checking, the Pi-owned target key, and the existing
  restricted account boundary.
- Added an explicit installer and deterministic safety tests.

## Decisions

- BB-ADR-060 makes the shortcut connection-only: it never enrolls a target,
  accepts a host key, chooses among multiple targets, or changes the computer.

## Blockers

- None for the currently connected `DESKTOP-3U8PBEN` target.

## Immediate next step

Install the shortcut on `/home/kali/Desktop`, click it once, and verify the
restricted PowerShell prompt opens.

## Long-term objective

Make verified headless target access a simple, repeatable operator action while
preserving BoxBrain's identity and privilege boundaries.

## Session files

- [Agent handoff](AgentHandoff.md)
- [Decision log](DecisionLog.md)
- [Change log](ChangeLog.md)
- [Project updates](ProjectUpdates.md)
- [Questions](Questions.md)
- [Ideas](Ideas.md)
- [Verification checklist](VerificationChecklist.md)
- [Execution plan](ExecutionPlan.md)
