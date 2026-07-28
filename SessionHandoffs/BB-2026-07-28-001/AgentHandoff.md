# Agent Handoff — BB-2026-07-28-001

## Current objective

Resume BrainConnect at the authenticated live event stream milestone while
maintaining the verified BoxBrain indexes.

## Tasks

1. Confirm both local repositories begin clean.
2. Create `feature/brainconnect-live-events` in BrainConnect.
3. Implement authenticated server-sent events or an equivalent header-authenticated
   live stream in BrainConnect.
4. Add backend and Flutter reconnect/cursor tests.
5. Update both project repositories and generate the next handoff.

## Dependencies

- BoxBrain indexes and source-of-truth rules
- BrainConnect revision `1c6c926`
- BrainConnect Python and Flutter development environments
- Existing API bearer authentication and audit sequence cursor

## Files affected

- BoxBrain root and all canonical index directories
- No BrainConnect files changed during repository organization

Detailed additions are in the [session change log](ChangeLog.md).

## Required repositories

- This BoxBrain repository
- [BrainConnect canonical repository](../../../BrainConnect/README.md)

## Verification checklist

- Run the [session verification checklist](VerificationChecklist.md).
- Confirm no BrainConnect runtime secrets or data are tracked.
- Re-run BrainConnect backend and Flutter tests after implementation changes.

## Suggested commit message

`docs: establish BoxBrain canonical repository`

## Suggested branch

`main` for the initial local foundation; use
`feature/brainconnect-live-events` for the next BrainConnect change.

## Potential risks

- Local relative links to BrainConnect will need replacement or a workspace
  manifest when repositories move or receive remote URLs.
- Metadata-only project descriptions could become stale if assets exist outside
  the inventoried workspace.
- Cross-project docs can drift if project changes do not update BoxBrain.

## Estimated completion order

1. BrainConnect live event stream
2. Backend and Flutter stream tests
3. BoxBrain project and handoff update
4. Observation target identity and allowlisting
5. Observation-only RDP or VNC adapter
