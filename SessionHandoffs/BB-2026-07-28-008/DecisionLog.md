# Decision Log

## BB-ADR-012

- **Date:** 2026-07-28
- **Decision:** Deploy the Pi controller as an immutable wheel with exact
  runtime dependencies, run it through a hardened systemd unit as a dedicated
  non-login user, bind it only to the direct USB address, and promote it only
  after authenticated foreground verification.
- **Reason:** The controller must be reachable from the attached Windows
  workstation without becoming a Wi-Fi/LAN service or inheriting the broad
  authority of `kali` or root. A mutable checkout and unpinned environment
  would weaken provenance and restart confidence.
- **Alternatives considered:** Bind to loopback and require SSH tunneling, bind
  to every interface and add firewall rules, bind to the Wi-Fi address, run as
  `kali`, run as root, deploy through Docker, copy a mutable source checkout,
  place the API token in the systemd environment file, or enable the unit
  before foreground verification.
- **Chosen solution:** Build one wheel from an exact Git revision, install an
  exact runtime lock into a revisioned virtual environment, record checksums
  and provenance, use a locked `brainconnect` account, keep mutable data only
  under `/var/lib/brainconnect`, bind to `10.12.194.1:8000`, generate the token
  in the private state directory, and gate activation with authenticated
  foreground and restart-persistence checks.
- **Impact:** The controller is boot-persistent and reachable over direct USB
  while remaining absent from the Pi Wi-Fi socket set. Runtime state and
  credentials remain outside Git, helper drift fails verification, and the
  emergency stop remains durable. A separate dashboard credential-provisioning
  decision is still required.
