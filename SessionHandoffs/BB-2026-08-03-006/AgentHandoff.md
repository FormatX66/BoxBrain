# Agent Handoff

## Current objective

Deploy the bounded HID-report retry and perform one newly authorized enrollment
attempt against the attached Windows target.

## Tasks

1. Validate and commit BoxBrain 0.14.1.
2. Upgrade the Pi through the existing rollback-guarded path.
3. Verify Pi health, gadget state, and release-only HID readiness.
4. Obtain a fresh exact confirmation before retrying enrollment.
5. Require key-only SSH proof before reporting success.

## Dependencies

- Attached target remains unlocked with a US keyboard layout.
- Pinned management SSH access to the Pi.
- Exact `CONNECT HEADLESS WINDOWS` confirmation for each command-sequence run.

## Files affected

- `edge/kali-pi-agent/src/boxbrain/headless_link.py`
- `edge/kali-pi-agent/tests/test_headless_link.py`
- `edge/kali-pi-agent/VERSION`
- Edge-agent documentation and session indexes.

## Required repositories

- `FormatX66/BoxBrain`

## Verification checklist

- Run all edge-agent tests.
- Run the BoxBrain project and repository validators.
- Verify the deployed version and service health.
- Verify the USB gadget without sending a key.
- Do not reuse the earlier execution confirmation.

## Suggested commit message

`Retry transient USB HID report writes`

## Suggested branch

`codex/usb-hid-report-retry`

## Potential risks

- Replaying a partially delivered command could create unintended input.
- The target may not poll HID while locked, asleep, or incompletely enumerated.

## Estimated completion order

Validation, commit, deployment, readiness proof, fresh authorization, SSH proof.
