# Agent Handoff

## Current objective

Promote the source-complete USB composite profile safely, then design the
separate Bluetooth HID pairing workflow.

## Tasks

1. Review and merge the composite USB HID source.
2. Stage it over a verified non-USB management connection.
3. Reboot only inside an approved maintenance window.
4. Verify `usb0`, `/dev/hidg0`, `/dev/hidg1`, host enumeration, and rollback.
5. Select an explicit Bluetooth pairing-window and trusted-host policy.

## Dependencies

- Pi 4 USB device controller and ConfigFS/libcomposite.
- Active non-USB management interface during USB gadget migration.
- BlueZ for a later, separately authorized Bluetooth HID implementation.

## Files affected

- `Architecture/SystemArchitecture.md`
- `Architecture/Integrations.md`
- `Admin/Decisions.md`, `Admin/ChangeLog.md`, `Admin/MasterTODO.md`
- `docs/EDGE_AGENT.md`
- `edge/kali-pi-agent/README.md`
- `edge/kali-pi-agent/scripts/boxbrain-usb-composite.sh`
- `edge/kali-pi-agent/scripts/configure-usb-keyboard.sh`
- `edge/kali-pi-agent/src/boxbrain/cli.py`
- `edge/kali-pi-agent/tests/test_usb_keyboard_gadget.py`

## Required repositories

- `FormatX66/BoxBrain`
- `FormatX66/BrainConnect` for controller compatibility only

## Verification checklist

- [x] Edge-agent unit suite passes: 46 tests, one Windows-only shell skip.
- [x] Both modified shell helpers parse under the Pi's `sh`.
- [x] Pi reports one UDC and active BlueZ 5.85.
- [ ] Live composite gadget enumerates on a disposable Windows target.
- [ ] Timed rollback and explicit commit are exercised.
- [ ] Bluetooth policy is selected before any advertising or pairing.

## Suggested commit message

`Add composite USB keyboard and mouse transport`

## Suggested branch

`codex/pi-multitransport-hid`

## Potential risks

- A malformed or unsupported gadget profile can temporarily remove USB network
  access; retain Wi-Fi/Ethernet access and the rollback timer.
- Automatic Bluetooth pairing could trust an unintended nearby host.

## Estimated completion order

USB source review, staged Pi migration, disposable-host proof, Bluetooth policy,
Bluetooth source implementation, then Bluetooth pairing proof.
