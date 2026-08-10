# Verification Checklist

- [x] rclone upstream, license, releases, headless flow, and Drive behavior were
  reviewed from authoritative sources.
- [x] Drive sync uses `copy`, not deletion-mirroring `sync`.
- [x] OAuth configuration remains outside Git and writable only by `boxbrain`.
- [x] Timer remains disabled until the explicit enrollment helper succeeds.
- [x] Patch manifest filename, schema, payload type, size, target hostname, and
  SHA-256 checks are deterministic.
- [x] Delivery rechecks checksum and connected authorized target identity.
- [x] Delivery requires exact confirmation and pinned-host-key SFTP.
- [x] Delivery does not install or execute the patch.
- [x] Pi edge-agent suite passed locally: 32 tests, one environment-only skip.
- [x] Wi-Fi regression checks prove the explicit authorization gate precedes
  saved-key retrieval and transient credential variables are cleared.
- [x] Headless-link tests prove preview makes no change, the typed bootstrap is
  fixed and credential-free, approval is exact, helper SHA-256 is checked, and
  an unverified SSH result cannot be reported as success.
- [x] BoxBrain 0.11 source suite passed locally: 39 tests, one environment-only
  POSIX-shell skip on Windows.
- [x] All 32 Pi edge-agent tests passed from the exact deployment archive on
  the ARM64 Pi.
- [x] Controller suite passed: 78 tests.
- [x] Flutter analysis and all 19 tests passed.
- [x] New and modified POSIX scripts passed `sh -n` through Git for Windows.
- [x] Official rclone 1.74.4 Linux ARM64 archive matched the published SHA-256;
  the installed binary is root-owned and reports the expected version.
- [x] BoxBrain 0.10.0 was deployed through the rollback-capable upgrade path.
- [x] Live health reports 0.10.0 and all three core services are active.
- [x] Drive service and timer are installed but disabled/inactive; OAuth state
  is absent.
- [x] Root-private rollback archive was integrity-checked after deployment.
- [x] Repository structure and links passed after excluding the preserved,
  user-owned untracked `AGENTS.md` from the local-only scan.
- [ ] GitHub CI passes on the published branch.
- [x] Verified rclone is installed on the Pi.
- [x] OAuth is completed as `boxbrainprime@gmail.com` with the exact root folder.
- [x] Private config ownership/mode and enabled active timer were verified.
- [x] Drive readback found 223 uploaded historical reports and continuing
  progress.
- [x] The first emitted token was revoked and its temporary log removed; the
  replacement flow produced zero credential-bearing log lines.
- [ ] First historical timer run reaches a successful final sync state.
- [ ] Dedicated BoxBrain Google OAuth client replaces rclone's retiring shared
  client ID.
- [ ] One disposable non-executing patch delivery and receipt are verified.
- [ ] Live Pi composite-gadget HID configuration is reviewed and authorized.
- [ ] One disposable headless Windows keystroke link is independently verified.
