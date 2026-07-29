# Verification Checklist

- [x] Read the BrainConnect project index, newest handoff, decisions, changes,
  roadmap, TODO, repository, integration, and session indexes first.
- [x] Created no duplicate architecture, protocol, repository, or project
  documentation.
- [x] Rejected the development host as a live target.
- [x] Stopped the Windows Sandbox attempt after its second RDP listener failed.
- [x] Used a Pi-loopback fixture with exact RDP NLA/HYBRID negotiation.
- [x] Inherited-environment native helper preflight passed.
- [x] Minimal environment with only `HOME` added passed.
- [x] API token remained absent from the helper environment and host output.
- [x] Exact certificate match passed before target enablement.
- [x] Certificate rotation changed the fingerprint on the same endpoint.
- [x] Mismatch disabled the previously enabled target atomically.
- [x] Unreachable endpoint returned HTTP 502 and `helper_failed`.
- [x] Stalled listener returned HTTP 504 and `helper_timeout`.
- [x] Authentication and desktop-session flags remained false.
- [x] TLS fixture received zero application-data bytes.
- [x] Temporary Pi verifier, certificates, and private keys were removed.
- [x] Controller upgrade from an active service passed the new fail-safe gate.
- [x] Pi service is enabled and active on USB-only `10.12.194.1:8000`.
- [x] State directory is mode `0700`; token and database are mode `0600`.
- [x] Deployed revision and helper checksum match provenance.
- [x] BrainConnect controller tests: 27 passed.
- [x] BrainConnect PowerShell, Python, and diff checks passed.
- [x] BrainConnect Flutter analysis: no issues found.
- [x] BrainConnect Flutter tests: 8 passed.
- [x] BrainConnect production Flutter web build succeeded.
- [x] BrainConnect branch pushed at `1df9de7`.
- [x] BrainConnect draft pull request 7 opened.
- [x] BoxBrain structural and Markdown-link validation passes.
- [x] BoxBrain documentation commit is pushed to pull request 3.
- [x] Both repository working trees are clean.
