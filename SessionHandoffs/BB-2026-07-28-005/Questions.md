# Questions

## Open

- Which reproducible FreeRDP 3.x package, compiler, and CMake baseline should
  be canonical for Linux/Kali and Raspberry Pi builds?
- Which isolated Windows target will provide the exact-match and
  changed-certificate integration fixtures?
- Which external credential provider should supply the dedicated RDP lab
  account after certificate probing is proven?
- Should the existing public BoxBrain remote remain public after the canonical
  organization is merged?

## Resolved this session

- The helper protocol is fixed, versioned, bounded, and out of process.
- Subject, issuer, validity, FreeRDP version, fingerprint, endpoint, and
  explicit no-authentication/no-session claims are the allowed response data.
- Registered disabled targets may be probed before enablement.
- A certificate mismatch disables an enabled target; helper failures do not.
- The current workstation cannot build the native helper without new system
  dependencies, and none were installed implicitly.
