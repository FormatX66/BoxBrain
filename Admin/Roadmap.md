# BoxBrain Roadmap

## Completed — Repository foundation

- Establish the canonical structure and source-of-truth rules.
- Register BrainConnect without copying its code or documentation.
- Add global indexes, dependency maps, validation, and session handoffs.
- Confirm and configure the canonical remote URLs.

## Completed — BrainConnect live events

- Authenticated first-message WebSocket connection
- Cursor resume and reconnect from the latest audit sequence
- HTTP polling fallback with sequence deduplication
- Browser-origin validation and local end-to-end verification

## Completed — BrainConnect observation design

- Define target identity and audited, disabled-by-default allowlisting.
- Select an out-of-process, observation-only FreeRDP adapter.
- Define bounded evidence retention and redaction rules.
- Keep keyboard, mouse, and shell execution disabled.

See the canonical [BrainConnect roadmap](../../BrainConnect/docs/ROADMAP.md).

## Completed — BrainConnect target registry

- Durable target records with immutable UUIDs and additive schema migration
- Audited register, inspect, enable, and disable operations
- Exact SHA-256 RDP server-certificate confirmation before enablement
- Enabled-target admission checks for every new task
- Flutter registration, review, approval, and disable workflow
- Credentials excluded from target records

## Completed — BrainConnect certificate-probe boundary

- Fixed, out-of-process helper invocation with no command shell
- Strict, versioned, bounded JSON response protocol
- Server-certificate comparison without credentials or a desktop session
- Atomic disablement and audit record after an identity mismatch
- Flutter probe action and last-verification display
- Deterministic process, timeout, protocol, mismatch, and audit tests

## Completed — BrainConnect native FreeRDP helper

- Pinned a Debian 13, FreeRDP 3.15.x, CMake, GCC, and OpenSSL build baseline.
- Implemented strict arguments, bounded JSON, X.509 parsing, and an internal
  hard deadline.
- Required exact NLA/HYBRID server selection and rejected TLS-only downgrade.
- Forced certificate rejection before authentication or `PostConnect`.
- Built and synthetic-tested amd64 and Raspberry Pi-compatible arm64 images.

## Next — BrainConnect isolated RDP live lab

- Package and install the helper plus runtime dependencies on Linux or a
  Raspberry Pi controller.
- Configure only the helper's absolute executable path.
- Verify exact-match, changed-certificate, timeout, and no-authentication
  behavior against an isolated disposable Windows RDP target.
- Record package provenance and checksums without storing credentials.
- Keep keyboard, pointer, clipboard, file, shell, and device redirection
  unavailable.

## Later — Shared ecosystem services

- Establish AgentFramework contracts when a repository is authorized.
- Promote shared security controls into the Security project.
- Add reproducible Research benchmark definitions.
- Register WebsiteBuilder, Arkmatx, WebsiteCluster, and Automation sources as
  they are discovered.
- Prepare Docker, Raspberry Pi, VM, and cloud deployment tracks only after
  their software dependencies are proven.

## Long-term objective

Operate BoxBrain as a searchable, auditable coordination system for multiple
projects, models, agents, repositories, and deployment environments.
