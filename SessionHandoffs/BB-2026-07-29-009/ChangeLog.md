# Change Log

## Changed files

### BrainConnect

- Native control authentication, settings, and tests
- Pi experiment runner and tests
- Architecture, development, security, target, open-lab, roadmap, deployment,
  native-build, and top-level documentation

### BoxBrain

- BrainConnect project index
- System and integration architecture
- Roadmap and Master TODO
- Decision, change, and session indexes
- Session `BB-2026-07-29-009`

## Reason

Correct the RDP credential/session/input settings, prove keyboard effects
independently, and replace the stale session-routing blocker with the next
verified observation milestone.

## Dependencies

- Exact Windows target identity and certificate pin
- Target-local `BB-WIN-LAB` credential binding
- FreeRDP console-session and slow-path input settings
- Restricted read-only Windows process verifier
- Guarded checkpoint restore helper

## Future implications

- Keyboard launch operations can now be used as a known-good baseline.
- Cursor position and text correctness must be proved with bounded frame or
  guest-state evidence.
- FreeRDP build/runtime alignment is the next compatibility task.
- The controller remains inert between explicit, audited test windows.
