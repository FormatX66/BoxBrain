# Human Handoff

## Accomplished

- Converted the five product goals into one canonical connection lifecycle.
- Added a read-only Pi connection map for USB, Ethernet, Wi-Fi, Bluetooth, and
  near-field hardware.
- Added capability states for dashboard, keyboard, mouse, SSH, PowerShell, CMD,
  data, video, audio, and onboarding.
- Carried the map through the controller API into a dedicated Flutter dashboard
  card.
- Kept all transport activation, Bluetooth pairing, and live Pi deployment off.

## Decisions

- Capabilities must be observed or explicitly marked unavailable; they are never
  inferred from hardware presence.
- NFC performs onboarding/handoff only, not a repair session.
- Health evidence is sanitized before model assessment, and proposals do not
  execute silently.

## Blockers

- Bluetooth pairing policy and near-field hardware are not selected.
- Append-only connection sessions and remote enrollment are not implemented.
- Source version 0.13.0 has not been deployed to the Pi.

## Immediate next step

Review the source branch, then deploy 0.13.0 without enabling new transports and
verify that the live dashboard reports the Pi's actual connection map.

## Long-term objective

Let BoxBrain discover every available path, assess an authorized machine,
operate through proven capabilities, and support a later explicitly enrolled
remote repair.

## Session files

- [Agent handoff](AgentHandoff.md)
- [Decision log](DecisionLog.md)
- [Change log](ChangeLog.md)
- [Project updates](ProjectUpdates.md)
- [Questions](Questions.md)
- [Ideas](Ideas.md)
- [Verification checklist](VerificationChecklist.md)
- [Execution plan](ExecutionPlan.md)
