# Verification Checklist

- [x] Windows RDP port 3389 reachable at `10.12.194.9`.
- [x] Workstation SSH to target port 22 remains blocked.
- [x] Guest computer name independently reported as `BB-WIN-LAB`.
- [x] Active RDP certificate read through Hyper-V PowerShell Direct.
- [x] Independent SHA-256 recorded outside Git.
- [x] Target registered disabled by default.
- [x] Registered endpoint and certificate match independent evidence.
- [x] Pi helper selected FreeRDP 3.26.0.
- [x] Probe returned `authenticated = false`.
- [x] Probe returned `desktop_session_started = false`.
- [x] Exact certificate match recorded at
  `2026-07-29T16:01:56.395853Z`.
- [x] Audit sequence 29 records target registration.
- [x] Audit sequence 30 records identity verification.
- [x] Audit sequence 31 records explicit enablement.
- [x] Exposed controller token revoked and rotated.
- [x] Replacement token remains private on the Pi.
- [x] Authorized health returns HTTP 200.
- [x] Unauthorized health returns HTTP 401.
- [x] Controller reports production and `executor_enabled = false`.
- [x] BrainConnect dependency check passes.
- [x] BrainConnect backend tests pass: 27.
- [x] Flutter analysis reports no issues.
- [x] Flutter tests pass: 9.
- [ ] Observation-only frame protocol implemented.
- [ ] Live frame credential/session boundary approved.
- [ ] Clean checkpoint restored after first live frame experiment.
- [x] BoxBrain repository validation passes after final documentation update.
