# Questions

## Open

- Which isolated Windows VM will provide the exact-match and
  changed-certificate live fixtures?
- Should the first host package target Raspberry Pi OS arm64 or Debian amd64?
- Which release format should carry the binary, runtime dependency manifest,
  provenance, and checksums?
- Which external credential provider should supply the dedicated RDP lab
  account after certificate probing is proven?
- Should the existing public BoxBrain remote remain public after the canonical
  organization is merged?

## Resolved this session

- The reproducible baseline is digest-pinned Debian 13 with FreeRDP 3.15.x,
  GCC, CMake, OpenSSL 3, and Docker Buildx.
- The helper must inspect the server-selected protocol, not trust the
  advertised request mask.
- Only exact NLA/HYBRID selection can produce an observation; TLS-only
  selection fails with no JSON.
- The same source builds and passes native tests on amd64 and arm64.
- No compiler or FreeRDP development package was installed on Windows or WSL.
