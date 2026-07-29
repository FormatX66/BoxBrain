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

## Completed — BrainConnect Raspberry Pi 4 helper deployment

- Connected to the Pi 4 over its direct USB gadget network with strict SSH
  host-key checking.
- Verified Kali 2026.2 arm64 and exact `libfreerdp3-3` runtime version
  `3.26.0+dfsg-1`.
- Ran the full synthetic certificate boundary test on the Pi before install.
- Installed the reviewed ELF root-owned with checksum and content-addressed
  provenance.
- Changed no package version, repository, or package hold on the Pi.

## Completed — BrainConnect Raspberry Pi 4 controller deployment

- Packaged an exact Git revision as a wheel with locked runtime dependencies.
- Installed the release and plugin manifests under immutable `/opt` paths.
- Ran the controller as a locked `brainconnect` systemd service account.
- Bound the authenticated API only to `10.12.194.1:8000` on direct USB.
- Kept the generated token and SQLite database mode `0600` in a mode `0700`
  state directory outside Git.
- Verified HTTP 401 rejection, helper checksum, emergency-stop persistence,
  restart recovery, and systemd hardening.

## Completed — BrainConnect Pi RDP identity live lab

- Ran a protocol-faithful RDP/NLA certificate fixture on Pi loopback.
- Verified exact certificate match and explicit target enablement.
- Rotated the certificate on the same endpoint and verified atomic disablement.
- Verified bounded unreachable and timeout responses.
- Confirmed no authentication, desktop session, or TLS application data.
- Fixed the minimal FreeRDP runtime environment and fail-safe upgrade path.

## Next — BrainConnect disposable desktop target

- Select a full Windows VM or dedicated lab machine that can host an
  independently reachable RDP listener.
- Add observation-only frame transport without credentials or input.
- Define controlled dashboard credential provisioning without committing or
  broadly copying the Pi's long-lived token.

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
