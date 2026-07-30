# Change Log

## BrainConnect

### Changed files

- Added exact Pi runtime dependency lock
- Added guarded local and remote controller deployment scripts
- Added hardened `brainconnect-controller.service`
- Added foreground and service deployment verifier
- Added Pi deployment documentation
- Updated root, architecture, development, roadmap, security, installer, and
  test documentation

### Reason

Turn the already installed native helper into a usable authenticated
controller host without exposing the API to Wi-Fi, embedding secrets, enabling
input, or depending on a mutable source checkout.

### Dependencies

- Controller release source
  `016ec1f5b20db4c4b9679da74f8e36be4e1a11aa`
- Controller wheel SHA-256
  `1074998f743300fa87263f8d1db285a2775e5491611676d62528b332f5744100`
- Installed helper SHA-256
  `b2108177d6b0d1fd126b16b96b186ea40aead6acc4cd6a6ffeb5815851def6a1`
- Kali Python 3.13.12 and systemd 260
- Existing strict SSH key and host identity

### Future implications

Every controller upgrade should create a new immutable release and re-run the
foreground and service gates. Dashboard credential provisioning must stay
separate from committed Flutter builds.

## Raspberry Pi 4

### Changed paths

- `/opt/brainconnect/controller/releases/016ec1f5b20db4c4b9679da74f8e36be4e1a11aa`
- `/opt/brainconnect/controller/current`
- `/opt/brainconnect/plugins/releases/016ec1f5b20db4c4b9679da74f8e36be4e1a11aa`
- `/opt/brainconnect/plugins/current`
- `/etc/brainconnect/controller.env`
- `/etc/systemd/system/brainconnect-controller.service`
- `/var/lib/brainconnect/api-token.txt`
- `/var/lib/brainconnect/brainconnect.sqlite3`
- `/usr/local/libexec/brainconnect/verify-controller-deployment`

### Safety notes

- The service is enabled and active as `brainconnect`, not root or `kali`.
- The API listens only on `10.12.194.1:8000`.
- Token and database are `brainconnect:brainconnect` mode `0600`.
- State directory is mode `0700`.
- No token was printed, copied to Windows, stored in Git, or placed in the
  systemd environment file.
- No operating-system package or firewall rule changed.
- Two pre-activation package attempts failed closed on invalid remote wheel
  filenames; no release or service was promoted until the filename was valid.

## BoxBrain

### Changed files

- Admin decision, change, repository, roadmap, session, and TODO indexes
- BrainConnect project and ecosystem project indexes
- Integration registry and session handoff index
- All nine files in `BB-2026-07-28-008`

### Reason

Record the real controller deployment, artifact identities, service boundary,
verification evidence, draft review, remaining live-lab blocker, and next
execution plan without duplicating BrainConnect architecture.
