# Ideas

- Use systemd's credential directory to give the adapter a short-lived
  credential file descriptor without exposing it to the controller.
- Start with pointer movement because it avoids text and clipboard disclosure.
- Add a desktop-session nonce to before/after evidence to prevent input from
  being attributed to the wrong session.
- Add an adapter self-test mode that authenticates, verifies the session, and
  disconnects without sending input.
- Release every modifier key in a `finally` path and include cleanup status in
  the result.
- Normalize pointer coordinates into a fixed 0-16383 space using the live
  desktop dimensions already declared by the operation schema.
- Keep shell as a separate capability adapter if combining SSH and RDP would
  make identity evidence clearer.
