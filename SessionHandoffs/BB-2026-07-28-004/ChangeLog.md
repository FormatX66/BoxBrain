# Change Log

## BrainConnect

### Changed files

- Root and controller README files
- Controller API, database, and models
- Controller API and event-stream tests
- Architecture, development, product, roadmap, security, and target documents
- Flutter target model, controller API client, dashboard, and widget tests

### Reason

Turn the approved target-identity design into a durable, audited controller and
operator workflow before adding a remote observation transport.

### Dependencies

- FastAPI authentication and audit services
- SQLite schema migration support
- Flutter controller client
- Existing target identity and retention specification

### Future implications

The observation plugin must consume target UUIDs from this registry, compare
the live RDP certificate with the stored pin, and retain the no-input boundary.

## BoxBrain

### Changed files

- Admin decision, change, repository, roadmap, session, and TODO indexes
- BrainConnect project index
- Integration registry
- Session handoff index
- All nine files in `BB-2026-07-28-004`

### Reason

Record the completed target-registry milestone, its architectural decision,
verification evidence, and the next observation-probe objective.

### Dependencies

- BrainConnect commit `dcc32b8`
- BrainConnect draft pull requests 1 and 2
- BoxBrain organization pull request 3

### Future implications

Future sessions begin with the certificate-only probe and must not duplicate
target identity or lifecycle documentation outside BrainConnect.
