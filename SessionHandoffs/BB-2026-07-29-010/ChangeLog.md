# Change Log

## Changed files

### BrainConnect

- Controller pointer-button schema and tests
- Flutter pointer-button form
- Native strict protocol, session readiness, stdout isolation, click delivery,
  frame observation, provenance, and tests
- Pi experiment runner
- Architecture, development, security, target, open-lab, roadmap, plugin,
  controller, native-build, and top-level documentation

### BoxBrain

- Hyper-V credential-rotation helper and runbook
- BrainConnect project index
- System and integration architecture
- Roadmap and Master TODO
- Decision, change, and session indexes
- Session `BB-2026-07-29-010`

## Reason

Close the independent mouse/keyboard verification gap, remediate a disposable
credential disclosure, establish a new safe checkpoint, and preserve the
next upgrade-preflight issue.

## Dependencies

- Exact Windows target identity and certificate pin
- Target-bound systemd runtime credentials
- Standard target-user RDP session and ten-second readiness window
- Bounded memory-only frame protocol
- UAC-gated credential rotation and checkpoint helpers

## Future implications

- Keyboard text and coordinate clicks now have independent visible evidence.
- The earlier checkpoint must never be restored.
- Controller upgrades must start from an inert executor state.
- Shell, scrolling, and clipboard remain deliberate separate capability
  expansions.
