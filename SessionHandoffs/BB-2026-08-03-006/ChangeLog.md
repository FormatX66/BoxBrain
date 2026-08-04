# Change Log

## Changed files

- Updated the HID report writer with a bounded transient-not-ready retry.
- Added deterministic success and retry-exhaustion tests.
- Bumped the edge-agent version to 0.14.1.
- Updated canonical edge-agent documentation and session indexes.

## Reason

The first authorized headless-Windows enrollment stopped when the configured
nonblocking HID endpoint briefly rejected a report.

## Dependencies

- Linux ConfigFS HID gadget and Python standard library only.

## Future implications

- Each command-sequence execution still requires fresh exact authorization.
- Persistent endpoint failures remain visible rather than being hidden by an
  unbounded retry.
