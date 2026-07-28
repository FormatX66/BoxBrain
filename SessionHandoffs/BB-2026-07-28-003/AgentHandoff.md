# Agent Handoff

## Current objective

Build the BrainConnect durable target registry from the canonical decision in
`docs/TARGETS.md`.

## Tasks

1. Add a target table and migration to the controller database.
2. Add typed target models and validation for UUID, endpoint, fingerprint,
   retention, and enabled state.
3. Add authenticated, audited register, list, inspect, enable, and disable
   endpoints.
4. Require an enabled target for new tasks.
5. Add controller and Flutter tests before starting FreeRDP integration.

## Dependencies

- BrainConnect `docs/TARGETS.md`
- BrainConnect database, authentication, audit, and emergency-stop services
- FreeRDP only after registry behavior is complete

## Files affected

- `BrainConnect/controller/src/brainconnect_controller/`
- `BrainConnect/controller/tests/`
- `BrainConnect/ui/lib/`
- `BrainConnect/ui/test/`
- BrainConnect architecture, security, roadmap, and target documentation
- BoxBrain project, decision, change, and handoff indexes

## Required repositories

- `https://github.com/FormatX66/BrainConnect`
- `https://github.com/FormatX66/BoxBrain`

## Verification checklist

- Database migration works on an existing alpha database.
- Invalid or duplicate targets are rejected.
- Targets default to disabled.
- Enable and disable operations require reasons and create audit events.
- Task creation rejects missing or disabled target IDs.
- No credential or frame data enters target records.
- Controller tests and Flutter tests pass without warnings.
- BoxBrain validation passes.

## Suggested commit message

`feat: add audited observation target registry`

## Suggested branch

`feature/brainconnect-target-registry`

## Potential risks

- Treating a host name as identity instead of the pinned certificate.
- Storing credentials in the target record.
- Enabling targets implicitly during registration or probing.
- Breaking existing alpha databases without a migration.
- Allowing observation work to introduce input or redirection capabilities.

## Estimated completion order

1. Database and models
2. Validation and service methods
3. Authenticated API and audit events
4. Task admission checks
5. Flutter target UI
6. Tests and documentation
7. BoxBrain handoff update
