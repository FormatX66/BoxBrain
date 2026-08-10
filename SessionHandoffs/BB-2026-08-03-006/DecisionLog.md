# Decision Log

## BB-ADR-058

- **Date:** 2026-08-03
- **Decision:** Retry only the same eight-byte USB HID report for up to one
  second when Linux returns `EAGAIN` or `EWOULDBLOCK`.
- **Reason:** A configured HID gadget can temporarily reject a nonblocking write
  before the host polls the endpoint, even while USB Ethernet remains active.
- **Alternatives considered:** Retry the entire enrollment sequence; use an
  unbounded blocking write; ignore the failed report; require manual report-level
  retries.
- **Chosen solution:** Bounded same-report retry with all other errors and
  partial writes remaining fatal.
- **Impact:** Transient endpoint readiness no longer aborts immediately, while
  BoxBrain still never replays an unverified command sequence automatically.
