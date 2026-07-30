# Change Log

## BrainConnect

### Changed files

- `controller/src/brainconnect_controller/rdp_probe.py`
- `controller/tests/test_rdp_probe.py`
- `installer/pi/install-controller.ps1`
- `installer/pi/README.md`
- `lab/pi-rdp-fixture/README.md`
- `lab/pi-rdp-fixture/verify-live-lab.ps1`
- `lab/pi-rdp-fixture/verify_pi_live_lab.py`
- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT.md`
- `docs/ROADMAP.md`
- `docs/SECURITY.md`
- `docs/TARGETS.md`

### Reason

Live-verify the deployed certificate identity boundary, correct FreeRDP
initialization under the controller's minimal environment, and make immutable
controller upgrades safe for an already-running Pi service. Synchronize the
canonical BrainConnect documentation with the verified Pi boundary while
keeping the full disposable Windows desktop and frame observer visibly pending.

### Dependencies

- Deployed source revision
  `1df9de72805c01f1a10908424096d1fcaf0bda40`
- Review branch revision `746dfdcdbe011d18128c28d7ebb1f2770aaaec58`
- Controller wheel SHA-256
  `3de9fcb43861f8fa6517b20a148680704228ca63b657dc6bc04c6f9cf25a0e3e`
- Helper SHA-256
  `b2108177d6b0d1fd126b16b96b186ea40aead6acc4cd6a6ffeb5815851def6a1`
- Kali 2026.2 arm64, Python 3.13.12, FreeRDP 3.26.0 runtime, OpenSSL,
  systemd, strict SSH host identity, and the direct USB link

### Future implications

Full desktop and frame testing must use a disposable full VM or dedicated
machine. `HOME` remains part of the helper's reviewed runtime contract.
Controller upgrades must continue to pass the disabled foreground gate before
service reactivation.

## Raspberry Pi 4

### Changed paths

- `/opt/brainconnect/controller/releases/1df9de72805c01f1a10908424096d1fcaf0bda40`
- `/opt/brainconnect/controller/current`
- `/opt/brainconnect/plugins/releases/1df9de72805c01f1a10908424096d1fcaf0bda40`
- `/opt/brainconnect/plugins/current`
- `/usr/local/libexec/brainconnect/verify-controller-deployment`
- `/var/lib/brainconnect/brainconnect.sqlite3`

### Verified behavior

- The controller is enabled and active on `10.12.194.1:8000`.
- Private state remains mode `0700`; token and database remain mode `0600`.
- Exact certificate matching passed and enabled only the verified target.
- Certificate rotation on the same endpoint disabled that target atomically.
- Unreachable probing returned HTTP 502 with `helper_failed`.
- A stalled listener returned HTTP 504 with `helper_timeout`.
- Authentication and desktop-session flags remained false.
- The TLS fixture received zero application-data bytes.
- Temporary verifier, certificates, and private keys were removed.

## BoxBrain

### Changed files

- Admin decision, change, repository, roadmap, session, and TODO indexes
- BrainConnect project and ecosystem project indexes
- Integration registry
- Session handoff index
- All nine files in `BB-2026-07-29-001`

### Reason

Record the verified production behavior, root cause, deployed artifact,
fail-safe upgrade decision, draft review, remaining desktop blocker, and next
execution plan without duplicating BrainConnect architecture.
