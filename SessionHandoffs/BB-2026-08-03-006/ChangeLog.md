# Change Log

## Changed files

- Updated the HID report writer with a bounded transient-not-ready retry.
- Added deterministic success and retry-exhaustion tests.
- Bumped the edge-agent version to 0.14.1.
- Deployed and verified 0.14.1 through the rollback-backed Pi upgrade path.
- Updated canonical edge-agent documentation and session indexes.

## Reason

The first authorized headless-Windows enrollment stopped when the configured
nonblocking HID endpoint briefly rejected a report.

## Dependencies

- Linux ConfigFS HID gadget and Python standard library only.
- Live rollback archive:
  `/var/backups/boxbrain/pre-0.14.1-20260804T021019Z.tar.gz`.

## Future implications

- Each command-sequence execution still requires fresh exact authorization.
- Persistent endpoint failures remain visible rather than being hidden by an
  unbounded retry.
