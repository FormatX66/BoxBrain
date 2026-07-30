# Ideas

- Add a bounded `input_sequence` operation that reuses one RDP session and
  caps total events, duration, text length, and inter-event delay.
- Capture a small redacted region or perceptual hash rather than a full desktop
  frame when only state-change evidence is needed.
- Add a disposable guest test application that exposes a non-sensitive,
  read-only marker for the last accepted test input.
- Store `transport_accepted` and `state_verified` as separate outcomes.
- Add a one-command lab cycle that restores the checkpoint, re-probes the
  certificate, promotes credentials, runs the bounded test, and rolls back.
- Make the controller refuse another live run if the previous cleanup proof is
  missing.
