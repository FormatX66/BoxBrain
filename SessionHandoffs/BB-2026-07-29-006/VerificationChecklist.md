# Verification Checklist

- [x] Native request accepts only canonical `pointer_move`.
- [x] Reordered, escaped, extra, duplicate, and unsupported fields fail closed.
- [x] Exact NLA/HYBRID endpoint and certificate are checked before credentials.
- [x] Certificate mismatch test succeeds without a credential directory.
- [x] Matched-certificate/missing-credential test sends no authentication data.
- [x] Credential names bind to the request target UUID.
- [x] Credential values are absent from arguments, JSON, controller state,
  ordinary environment values, result objects, and audit events.
- [x] Credential files require root/service ownership and owner-only access.
- [x] Symlinks, hard-link count drift, control characters, and oversized values
  fail closed.
- [x] Local credential buffers and the FreeRDP password setting receive
  best-effort cleansing.
- [x] Gateway, reconnect, clipboard, drive, device, audio, printer, smart-card,
  and file redirection are disabled.
- [x] Pointer coordinates are bounded by the negotiated desktop.
- [x] Native internal deadline exits with code 124.
- [x] amd64 native build passes 5 tests.
- [x] arm64 native build passes 5 tests.
- [x] Controller tests pass: 56.
- [x] Python compile and dependency checks pass.
- [x] BrainConnect diff check passes.
- [x] BrainConnect commit `d207694` is pushed.
- [x] BrainConnect draft pull request 10 is clean and mergeable.
- [x] BoxBrain structure and link validation passes: 162 required files and
  178 Markdown files.
- [x] BoxBrain backend tests pass: 57.
- [x] BoxBrain Kali Pi edge-agent tests pass: 21.
- [x] BoxBrain Flutter analysis reports no issues.
- [x] BoxBrain Flutter tests pass: 9.
- [x] BoxBrain diff check passes.
- [ ] Control fixtures pass against the Pi's FreeRDP 3.26 runtime.
- [ ] Control ELF is installed with provenance on the Pi.
- [ ] Encrypted target credential is provisioned.
- [ ] Executor remains disabled through installation verification.
- [ ] One live pointer event has independent visual evidence.
- [ ] Executor is disabled and the clean checkpoint is restored afterward.
