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
- [x] Pi edge-agent suite passed: 32 tests, one environment-only skip.
- [x] Controller suite passed: 78 tests.
- [x] Flutter analysis and all 19 tests passed.
- [x] New and modified POSIX scripts passed `sh -n` through Git for Windows.
- [x] Live Pi read-only check confirmed rclone is currently missing.
- [x] Repository structure and links passed after excluding the preserved,
  user-owned untracked `AGENTS.md` from the local-only scan.
- [ ] GitHub CI passes on the published branch.
- [ ] Verified rclone is installed on the Pi.
- [ ] OAuth is completed as `boxbrainprime@gmail.com`.
- [ ] First live timer run and Drive readback are verified.
- [ ] One disposable non-executing patch delivery and receipt are verified.
