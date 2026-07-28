# Change Log

## BrainConnect

### Changed files

- Controller API, application wiring, database, models, settings, RDP probe
  adapter, and target-probe service
- Controller API and RDP probe tests
- Flutter target model, API client, dashboard, and widget tests
- RDP observer manifest, README, and versioned process protocol
- Root, controller, architecture, development, plugin, product, roadmap,
  security, and target documentation

### Reason

Implement the fail-closed certificate-verification workflow that must exist
between durable target registration and any future RDP authentication or frame
delivery.

### Dependencies

- Existing authenticated controller API and append-only audit log
- Existing target registry and emergency stop
- Future native FreeRDP 3.x helper

### Future implications

The native helper must conform to the existing version 1 protocol. It may not
expand the process boundary to credentials, desktop frames, input, shell, file,
or device redirection.

## BoxBrain

### Changed files

- Admin decision, change, repository, roadmap, session, and TODO indexes
- BrainConnect project and ecosystem project indexes
- Integration registry
- Session handoff index
- All nine files in `BB-2026-07-28-005`

### Reason

Record the completed certificate-probe boundary, architectural decision,
verification evidence, review links, remaining native-helper blocker, and next
execution plan.

### Dependencies

- BrainConnect commit `877573f`
- BrainConnect draft pull requests 1, 2, and 3
- BoxBrain organization pull request 3

### Future implications

Future sessions begin with the native helper and must use, rather than
duplicate, BrainConnect's target and helper protocol documentation.
