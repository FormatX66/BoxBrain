# Verification Checklist

- [x] BrainConnect controller tests pass: 59.
- [x] BrainConnect Pi experiment-runner tests pass: 6.
- [x] Flutter analysis reports no issues.
- [x] Flutter widget tests pass: 10.
- [x] Native amd64 build passes all 5 tests with warnings as errors.
- [x] Native arm64 build passes all 5 tests with warnings as errors.
- [x] PowerShell syntax and plugin JSON checks pass.
- [x] Exact sequence-capable revision is installed on the Pi.
- [x] Control SHA-256 is recorded and verified.
- [x] Clean checkpoint is restored before and after the live experiment.
- [x] Restored RDP certificate matches the pinned identity.
- [x] Certificate probe reports no authentication or desktop session.
- [x] Persistent keyboard sequences reached transport success.
- [x] Independent Notepad process verification remained false.
- [x] Explorer/session 1 and LogonUI/other-session evidence is recorded.
- [x] Exposed controller token was rotated.
- [x] Authenticated service verification passed after rotation.
- [x] Executor is disabled.
- [x] Execution drop-in is absent.
- [x] Encrypted RDP credential count is zero.
- [x] Temporary Pi runner is removed.
- [x] Final VM restore receipt names checkpoint
  `clean-linked-2026-07-29`.
- [x] BrainConnect PR 12 is clean and mergeable.
- [x] BoxBrain PR 3 is clean and mergeable.
- [x] BoxBrain structural/link validation passes: 180 required files and 196
  Markdown files.
- [x] BoxBrain repository-validator test passes.
- [x] BoxBrain diff check passes.
- [ ] Windows session ownership and reconnect policy are mapped.
- [ ] One target UI state change is independently verified.
