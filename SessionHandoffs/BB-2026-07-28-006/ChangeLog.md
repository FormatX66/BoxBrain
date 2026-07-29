# Change Log

## BrainConnect

### Changed files

- Native C helper, protocol parser, certificate extractor, and tests under
  `plugins/rdp-observer/native`
- Digest-pinned multi-architecture Docker build and PowerShell build wrapper
- Controller native-deadline error mapping and test
- RDP observer manifest and protocol documentation
- Root, controller, architecture, development, roadmap, security, and target
  documentation

### Reason

Replace the certificate-probe test double boundary with a reproducible native
FreeRDP implementation that stops before authentication and rejects
server-selected TLS downgrade.

### Dependencies

- Existing helper schema version 1 and controller process boundary
- Debian 13 `freerdp3-dev` 3.15.0 and OpenSSL 3
- Docker Buildx for current reproducible amd64 and arm64 builds

### Future implications

The next milestone must package the existing binary and test it in an isolated
Windows RDP lab. It may not broaden the certificate helper into frame delivery
or input.

## BoxBrain

### Changed files

- Admin decision, change, repository, roadmap, session, and TODO indexes
- BrainConnect project and ecosystem project indexes
- Integration registry
- Session handoff index
- All nine files in `BB-2026-07-28-006`

### Reason

Record the completed native-helper milestone, its security decision, build and
test evidence, pull request, remaining live-lab blocker, and next execution
plan.

### Dependencies

- BrainConnect commit `01c34d7`
- BrainConnect draft pull requests 1 through 4
- BoxBrain organization pull request 3

### Future implications

Future sessions begin with host packaging and isolated live verification, using
the existing native helper and protocol rather than duplicating them.
