# Change Log

## BrainConnect

### Changed files

- `README.md`
- `controller/tests/test_api.py`
- `controller/tests/test_event_stream.py`
- `docs/ARCHITECTURE.md`
- `docs/PLUGIN_CONTRACT.md`
- `docs/ROADMAP.md`
- `docs/SECURITY.md`
- `docs/TARGETS.md`

### Reason

Remove the upstream WebSocket test migration warning and make the first target
and observation boundary implementable.

### Dependencies

- FastAPI and Starlette event-stream implementation
- Flutter WebSocket client
- FreeRDP 3.x for the future observer

### Future implications

Target registry work now has a stable schema and approval workflow. FreeRDP
integration must retain the documented no-input capability boundary.

## BoxBrain

### Changed files

- Admin decision, change, repository, roadmap, session, and TODO indexes
- BrainConnect project index
- Integration registry
- Session handoff index
- All nine files in `BB-2026-07-28-003`

### Reason

Record the resolved blockers, confirmed remotes, new decisions, verification,
and next implementation milestone.

### Dependencies

- BrainConnect commit `7924654`
- Existing `FormatX66/BoxBrain` remote history

### Future implications

Future sessions start from the target-registry milestone and must update the
existing BoxBrain remote rather than creating a duplicate.
