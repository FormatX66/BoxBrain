# Decision Log

## BB-ADR-055

- **Date:** 2026-08-03
- **Reason:** BoxBrain needs one accurate view of every way the Pi and target can
  communicate before assessment or repair is attempted.
- **Alternatives considered:** One preferred connection only; separate ad hoc
  status panels; assume capabilities from adapter type.
- **Chosen solution:** Use one connect, map, assess, operate, log, and remote-
  enroll lifecycle. Every transport and capability reports an explicit observed
  state and activation remains separately authorized.
- **Impact:** The edge API, controller, and console share one extensible contract;
  future Bluetooth, NFC, video, audio, and remote-agent work plug into it.
