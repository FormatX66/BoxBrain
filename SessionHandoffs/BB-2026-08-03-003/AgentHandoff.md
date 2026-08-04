# Agent Handoff

## Current objective

Expose the live Pi 0.13.0 connection map in the local controller/dashboard and
establish the direct Ethernet target peer.

## Tasks

1. Deploy/restart the committed controller and rebuild the Flutter dashboard.
2. Verify five connection records in `/api/v1/edge-agents` and the UI.
3. Determine which computer or adapter is connected to Pi `eth0`.
4. Enroll that exact target only after its identity and authorization are known.

## Dependencies

- Live Pi `192.168.0.194`, serial `100000004e6bf40c`, BoxBrain 0.13.0.
- Loopback tunnel PID 61716 at handoff time.
- Existing authenticated local controller/dashboard.

## Files affected

- `Admin/MasterTODO.md`, `Admin/ChangeLog.md`, `Admin/SessionIndex.md`
- `Architecture/Integrations.md`
- This session bundle

## Required repositories

- `FormatX66/BoxBrain`

## Verification checklist

- [x] Guarded upgrade completed and rollback archive is root-owned mode 600.
- [x] Pi status API reports connection-map schema version 1.
- [x] No USB HID, Bluetooth pairing, NFC, firewall, or host-network activation.
- [ ] Local controller/dashboard renders the connection map.
- [ ] Ethernet peer is identified and authorized.

## Suggested commit message

`Record Pi 0.13 connection-map deployment`

## Suggested branch

Continue `codex/pi-drive-sync`.

## Potential risks

- Do not assume carrier means an authorized target is connected.
- Do not enable Internet Connection Sharing or change static addresses until the
  exact Windows adapter and target are confirmed.

## Estimated completion order

Controller rollout, UI rebuild, map verification, Ethernet peer discovery,
target authorization, then health assessment.
