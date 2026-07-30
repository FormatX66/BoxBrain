# Change Log

## BrainConnect

- **Changed files:** Controller schemas, SQLite migration, execution service,
  adapter runner, packaged fixture, API endpoint, settings, tests, Flutter
  operation/result models, dashboard workflow, plugin protocol, and canonical
  documentation.
- **Reason:** Prove a truthful, transport-neutral execution boundary before
  installing live VM control or credentials.
- **Dependencies:** Open-lab operation queue, exact RDP certificate helper,
  enabled target registry, emergency stop, and append-only audit stream.
- **Future implications:** The live connector must implement version 1 without
  changing durable state or exposing secrets. Raw result persistence would
  require a new explicit decision.

## BoxBrain

- **Changed files:** Admin indexes, roadmap, master TODO, repository index,
  system architecture, data flow, BrainConnect project index, project table,
  handoff index, and this session bundle.
- **Reason:** Record the completed execution boundary and make the live
  connector the next discoverable task.
- **Dependencies:** BrainConnect commit `310c264` and draft pull request 9.
- **Future implications:** Controller execution semantics are now stable enough
  for transport-specific FreeRDP work.
