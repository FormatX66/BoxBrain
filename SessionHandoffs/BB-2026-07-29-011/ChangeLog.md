# Change Log

## Changed files

### BrainConnect

- Added `installer/pi/controller-upgrade-preflight.py`.
- Updated the controller installer to run the read-only guard before package
  construction and upload.
- Added focused preflight and installer-ordering tests.
- Updated the Pi deployment documentation.

### BoxBrain

- Updated the BrainConnect project, roadmap, repository, decision, change,
  session, and task indexes.
- Added session `BB-2026-07-29-011`.

## Reason

Prevent controller promotion while execution is active or unverifiable and
preserve a clear division between low-impact daytime work and nightshift
verification.

## Dependencies

- Existing private Pi API token and authenticated health endpoint
- Existing reviewed RDP systemd drop-in path
- Existing inert Pi and rotated Windows checkpoint

## Future implications

- Upgrades now stop before mutation when controller safety state disagrees.
- The first real-Pi exercise and all resource-intensive regressions remain
  queued for nightshift.
- Scrolling remains the recommended next capability pending operator input.
