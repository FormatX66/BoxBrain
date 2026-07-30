# Verification Checklist

- [x] Native amd64 build passes 5 tests with warnings as errors.
- [x] Native arm64 build passes 5 tests with warnings as errors.
- [x] Pi FreeRDP 3.26 identity and credential-negative fixtures pass.
- [x] Systemd `0440` plus named-service read ACL is accepted.
- [x] Unsafe credential owners, modes, links, directories, and content remain
  rejected.
- [x] Credential values stay out of Git, arguments, ordinary environment
  values, API payloads, logs, results, and audit events.
- [x] Control artifact source revision and SHA-256 are recorded.
- [x] Pointer operation reached `succeeded`.
- [x] Unicode-text and allowlisted-key operations reached `succeeded`.
- [x] Independent guest process checks were performed.
- [x] The absence of durable UI proof is recorded explicitly.
- [x] Executor was disabled after the experiment.
- [x] Execution drop-in was removed.
- [x] Encrypted username, password, and domain credentials were removed.
- [x] Controller remains active and healthy.
- [x] Emergency stop remains armed.
- [x] BrainConnect controller tests pass: 56.
- [x] BrainConnect Flutter analysis reports no issues.
- [x] BrainConnect Flutter tests pass: 9.
- [x] BrainConnect diff check passes.
- [x] BrainConnect commit `e81f5f5` is pushed.
- [x] BoxBrain structure and link validation passes: 171 required files and
  187 Markdown files.
- [x] BoxBrain repository-validator test passes.
- [x] BoxBrain diff check passes.
- [ ] Independent visual or guest-state change is proven.
- [ ] Hyper-V checkpoint `clean-linked-2026-07-29` is restored.
- [ ] Certificate is re-probed after checkpoint restoration.
