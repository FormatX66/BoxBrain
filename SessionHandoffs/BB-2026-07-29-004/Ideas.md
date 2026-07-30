# Ideas

- Add a dry-run adapter that validates identity and credentials but emits no
  target input.
- Use operation correlation IDs to connect queue, adapter request, bounded
  result, evidence digest, and audit events.
- Add a modifier-key cleanup action after interruption so a failed chord cannot
  leave Ctrl, Alt, Shift, or Windows pressed.
- Normalize pointer coordinates against the observed desktop dimensions before
  dispatch.
- Classify failures as identity, credential, transport, timeout, UI state,
  application behavior, verification, or containment.
- Add a one-click experiment packet containing operation metadata, bounded
  result, evidence hashes, checkpoint name, and restoration result.
- Replay the same operation sequence across model planners after the adapter is
  deterministic.
