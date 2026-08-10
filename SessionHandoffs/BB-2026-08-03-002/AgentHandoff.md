# Agent Handoff

## Current objective

Promote and live-verify the read-only connection map without activating a new
transport.

## Tasks

1. Review and merge the source branch.
2. Deploy edge agent 0.13.0 through the existing guarded upgrade path.
3. Verify five transport records on the Pi API and Flutter console.
4. Add durable connection-session events.
5. Resolve Bluetooth and near-field onboarding decisions.

## Dependencies

- Existing Pi SSH tunnel and guarded edge-agent upgrade.
- Controller and Flutter compatibility with the optional `connections` field.
- Future BlueZ pairing policy and optional NFC hardware.

## Files affected

- `Architecture/ConnectionLifecycle.md`
- Edge `connections.py`, `server.py`, version, tests, and README.
- Controller edge models/client/tests.
- Flutter controller model, dashboard, and widget tests.
- Admin indexes and this session bundle.

## Required repositories

- `FormatX66/BoxBrain`
- `FormatX66/BrainConnect` for later repair-execution contracts

## Verification checklist

- [x] 49 edge-agent tests pass; one Windows-only shell check skips.
- [x] All 79 controller tests pass.
- [x] Flutter analysis passes.
- [x] All 19 Flutter tests pass.
- [ ] Live Pi 0.13.0 map is observed through the dashboard.

## Suggested commit message

`Add Pi transport capability map`

## Suggested branch

Continue `codex/pi-drive-sync` to preserve the current dependent stack.

## Potential risks

- A status map must not be mistaken for authorization.
- Remote enrollment must not create hidden persistence or log credentials.
- Capability details must remain bounded before crossing the Pi tunnel.

## Estimated completion order

Full validation, commit/push, review, read-only Pi deployment, live map proof,
session logging, then Bluetooth/NFC work.
