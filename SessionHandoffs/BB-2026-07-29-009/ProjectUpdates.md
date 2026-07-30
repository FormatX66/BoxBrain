# Project Updates

## BrainConnect

- **Status:** Active alpha
- **Completion:** 97% planning estimate
- **Functional input revision:** `871fe43`
- **Documentation revision:** `379f4dc`
- **Verified now:** Exact-user authentication, console-session reconnection,
  slow-path keyboard delivery, Task Manager launch, Notepad launch, Pi cleanup,
  and exact checkpoint restoration.
- **Pending:** Frame/cursor/text-content verification, pointer buttons, scroll,
  clipboard, shell, and FreeRDP build/runtime alignment.

## BoxBrain

- Recorded decisions BB-ADR-032 and BB-ADR-033.
- Replaced Windows session binding as the active blocker.
- Preserved observation-only frame delivery as the next P0 milestone.
- Kept implementation details canonical in BrainConnect and linked them from
  the BoxBrain indexes.

## Related projects

- **Security:** Frame redaction and evidence retention remain dependencies.
- **Research:** Verified input outcomes can become repeatable benchmark cases.
- **AgentFramework:** Planner integration remains downstream of deterministic
  observation and input verification.
