# Verification Checklist

## Completed daytime checks

- [x] Enabled plain systemd execution setting is refused.
- [x] Enabled quoted systemd execution setting is refused.
- [x] Disabled execution setting is accepted.
- [x] Authenticated inert health is accepted.
- [x] Enabled execution, engaged stop, and degraded health are refused.
- [x] Installer invokes preflight before wheel construction.
- [x] Pi installer tests pass: 16.
- [x] PowerShell installer parses without errors.
- [x] Python preflight compiles.
- [x] BrainConnect diff check passes.
- [x] BrainConnect revision `be0738c` is pushed to pull request 12.
- [x] No Pi, VM, Docker, Flutter, or service operation was performed.

## Queued nightshift checks

- [ ] Enabled state is refused on the real Pi before artifact construction.
- [ ] Disabled state passes the real Pi upgrade path.
- [ ] Full controller tests pass.
- [ ] Flutter analysis and tests pass.
- [ ] Native amd64 and arm64 builds and tests pass.
- [ ] Exact FreeRDP 3.26 Pi-runtime gates pass.
- [ ] Selected capability has independent effect evidence.
- [ ] Pi is inert and the rotated checkpoint is restored after the run.
- [x] BoxBrain structural and link validation passes: 207 required files and
  223 Markdown files.
- [x] BoxBrain repository-validator test passes.
- [x] BoxBrain diff check passes.
- [x] BoxBrain changes are committed and pushed to pull request 3.
