# Decision Log

## BB-ADR-044

- **Date:** 2026-07-30
- **Reason:** A Windows checkout uploaded CRLF shell scripts that Bash rejected.
- **Alternatives considered:** Depend only on contributor Git settings; convert
  files manually before each deployment; normalize in the deployment script.
- **Chosen solution:** Enforce `*.sh` LF in Git and stage explicit LF-normalized
  copies before upload.
- **Impact:** Remote installation is independent of workstation line-ending
  settings.

## BB-ADR-045

- **Date:** 2026-07-30
- **Reason:** FreeRDP accepting a wheel event does not prove visible scrolling.
- **Alternatives considered:** Trust transport success; use full-screen video;
  compare identical bounded regions.
- **Chosen solution:** Require two identical bounded observations with different
  controller-verified frame hashes around the exact scroll.
- **Impact:** Scrolling has independent effect evidence without continuous
  capture.

## BB-ADR-046

- **Date:** 2026-07-30
- **Reason:** The operator already had the purpose-built Hyper-V Administrators
  authority, but the restore helper unnecessarily demanded full elevation.
- **Alternatives considered:** Require a UAC prompt every restore; call Hyper-V
  commands outside the helper; honor the established operator group.
- **Chosen solution:** Accept either Administrator or Hyper-V Administrators
  membership while preserving exact VM and checkpoint validation.
- **Impact:** Recovery remains bounded and script-driven without an avoidable
  interactive elevation step.
