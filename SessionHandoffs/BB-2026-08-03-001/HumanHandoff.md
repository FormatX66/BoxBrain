# Human Handoff

## Accomplished

- Defined the Pi 4 as the BoxBrain core appliance and physical transport owner.
- Extended the disabled-by-default ConfigFS gadget to expose `usb0`, a keyboard
  at `/dev/hidg0`, and a mouse at `/dev/hidg1`.
- Preserved exact authorization, alternate access, timed rollback, and separate
  maintenance-window activation.
- Verified 46 edge-agent tests and parsed both shell helpers on the live Pi.

## Decisions

- USB and Bluetooth HID are separate trust boundaries.
- USB attachment does not automatically authorize Bluetooth pairing.

## Blockers

- Live USB gadget activation needs an approved maintenance window and reboot.
- Bluetooth HID needs a pairing-window and trusted-host policy decision.

## Immediate next step

Stage and verify the composite USB gadget on the disposable target during a
maintenance window; do not enable Bluetooth HID in that run.

## Long-term objective

Make the Pi-hosted BoxBrain appliance reachable through every supported
transport while preserving identity, authorization, audit, and rollback.

## Session files

- [Agent handoff](AgentHandoff.md)
- [Decision log](DecisionLog.md)
- [Change log](ChangeLog.md)
- [Project updates](ProjectUpdates.md)
- [Questions](Questions.md)
- [Ideas](Ideas.md)
- [Verification checklist](VerificationChecklist.md)
- [Execution plan](ExecutionPlan.md)
