# Ideas

- Add an adapter `authenticate_verify_disconnect` self-test that uses the same
  credential and session path but sends no input.
- Record negotiated desktop dimensions and session activation time as bounded
  transient evidence.
- Use a short-lived encrypted systemd credential drop-in whose removal is part
  of the same rollback transaction as executor disablement.
- Add a runtime capability endpoint so planners see `pointer_move` rather than
  the manifest's broader future capability set.
- Add a target-session generation value so a new RDP login cannot be mistaken
  for the session observed before an operation.
- Promote accepted-event and verified-visual-change as separate result fields
  in a future protocol version rather than overloading `succeeded`.
- Make the consolidated installer generate a dry-run promotion report with
  source revision, image ID, ELF checksum, runtime package, destination, and
  rollback paths.
