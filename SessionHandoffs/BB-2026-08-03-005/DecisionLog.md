# Decision Log

## BB-ADR-057

- **Date:** 2026-08-03
- **Decision:** Detect Pi connection transitions on the authorized Windows
  workstation and open the console through two loopback-only SSH forwards.
- **Reason:** A Pi cannot safely force a browser window onto an arbitrary host.
  The workstation already owns the pinned SSH identity and can observe its
  known USB, LAN, and recovery-AP paths without expanding network exposure.
- **Alternatives considered:** Start a browser from the Pi; expose noVNC on the
  LAN; install an elevated Windows service; discover arbitrary private hosts.
- **Chosen solution:** A current-user, single-instance PowerShell watcher at
  logon, with fixed private addresses, transition-based opening, and bounded
  retries.
- **Impact:** The screen appears automatically for known connection paths while
  host-key checking, key-only authentication, and loopback-only viewer access
  remain intact.
