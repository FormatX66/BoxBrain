# Questions

## Open

- Which FreeRDP 3.x package and executable path should be canonical for Windows
  development and Raspberry Pi deployment?
- Should certificate-probe metadata retain only the fingerprint, or also
  bounded subject, issuer, validity, and protocol-version fields?
- Which external credential provider should supply the dedicated RDP lab
  account after the observation plugin exists?
- Should the existing public BoxBrain remote remain public after the canonical
  organization is merged?

## Resolved this session

- Target identity is now stored durably in SQLite schema version 3.
- Registration is disabled by default and enablement requires exact
  fingerprint confirmation plus a written reason.
- Task admission now requires an existing, enabled target UUID.
- The previous FastAPI/Starlette test migration warning remains resolved; all
  18 controller tests pass without warnings.
