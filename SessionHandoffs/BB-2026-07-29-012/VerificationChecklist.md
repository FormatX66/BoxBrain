# Verification Checklist

## Completed daytime checks

- [x] Operator selected scrolling.
- [x] Scroll requests require absolute X/Y coordinates.
- [x] Each delta is bounded to -1,200 through 1,200.
- [x] Deltas must use standard 120-unit steps.
- [x] Combined motion is limited to ten steps.
- [x] Zero-motion and nonstandard-unit requests are rejected.
- [x] Focused controller checks pass: 23 cases.
- [x] Pi experiment-runner tests pass: 17.
- [x] Python source compiles.
- [x] PowerShell installer parses.
- [x] Plugin manifest parses as JSON.
- [x] Dart formatting is clean.
- [x] BrainConnect diff check passes.
- [x] BrainConnect revision `494ec3f` is pushed to pull request 12.
- [x] No Flutter execution, Docker, native build, Pi, VM, service, credential,
  or checkpoint operation was performed.

## Queued nightshift checks

- [ ] Full controller suite passes.
- [ ] Flutter analysis and widget tests pass.
- [ ] Native amd64 build and all tests pass.
- [ ] Native arm64 build and all tests pass.
- [ ] Exact FreeRDP 3.26 Pi-runtime gates pass.
- [ ] Real-Pi upgrade preflight refusal and success paths pass.
- [ ] Installed artifact hash and scrolling provenance are recorded.
- [ ] Bounded before/after frames prove one exact scroll effect.
- [ ] Pi final inert state and checkpoint restoration are verified.
- [x] BoxBrain structural/link validation passes: 216 required files and 232
  Markdown files.
- [x] BoxBrain repository-validator test passes.
- [x] BoxBrain diff check passes.
- [x] BoxBrain changes are committed and pushed to pull request 3.
