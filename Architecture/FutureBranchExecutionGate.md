# Future Branch Execution Gate

Future Branch is a pre-execution gate, not a post-hoc planning step.

Before asking the human to type a command, click a control, move media, reboot a machine, or perform any other physical-edge action, the control plane must first advance every safe tool-side branch it can execute itself.

## Required order

1. Read verified current state and evidence.
2. Expand likely next-success, next-failure, rollback, dependency, and verification branches.
3. Execute all safe, reversible, tool-side work that does not require the human.
4. Prepare rollback/LKG protection before mutation.
5. Verify completed tool-side changes.
6. Only then hand the human the smallest remaining physical-edge action.
7. While the human performs that action, keep dependent branches warm and ready.
8. After new evidence arrives, continue automatically from the prepared branches instead of restarting diagnosis.

## Human handoff rule

A manual command is never the completion of a branch. It is only the physical edge of a branch whose remote, repository, test, rollback, and next-step work should already be prepared when possible.

If the system can make a safe repository-side fix before asking the human to recover a machine, it must make that fix first.

## Evidence rule

Never report a branch as complete merely because code or configuration was drafted. Distinguish:

- prepared
- written
- committed
- deployed/pulled
- executed
- health-checked
- physically verified

## Recovery rule

For self-modifying Aurum workspaces, dirty state must be checkpointed before synchronization. No sync path may destroy the last proven state. Destructive reset is not an automatic recovery mechanism.
