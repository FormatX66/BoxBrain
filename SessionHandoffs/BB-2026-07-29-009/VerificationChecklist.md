# Verification Checklist

- [x] Native amd64 build passes all 6 tests with warnings as errors.
- [x] Native arm64 build passes all 6 tests with warnings as errors.
- [x] Pi experiment-runner tests pass: 7.
- [x] Exact input revision is installed on the Pi.
- [x] Installed control SHA-256 is recorded and verified.
- [x] Windows events confirm exact-user authentication.
- [x] Windows events confirm reconnection to the intended session.
- [x] Task Manager is independently present after the key-only sequence.
- [x] Notepad is independently present after the text-launch sequence.
- [x] Executor is disabled after the run.
- [x] Execution drop-in is absent.
- [x] Encrypted RDP credential count is zero.
- [x] Temporary Pi runner count is zero.
- [x] Exact checkpoint `clean-linked-2026-07-29` is restored.
- [x] Restore receipt records the exact VM and checkpoint identifiers.
- [x] BrainConnect focused tests and diff check pass.
- [x] BrainConnect changes are pushed to draft pull request 12.
- [ ] Cursor position is independently verified.
- [ ] Visible text contents are independently verified.
- [ ] FreeRDP build and Pi runtime versions are aligned or compatibility-gated.
- [x] BoxBrain structural and link validation passes: 189 required files and
  205 Markdown files.
- [x] BoxBrain repository-validator test passes.
- [x] BoxBrain diff check passes.
- [x] BoxBrain changes are pushed to draft pull request 3.
