# Change Log

## Changed files

- Architecture and integration registries now identify the Pi 4 as the core and
  document the USB/Bluetooth transport boundary.
- The ConfigFS gadget now defines RNDIS, keyboard, and mouse functions.
- The guarded migration verifies both HID character devices before commit.
- `boxbrainctl usb-hid` is the canonical command; `usb-keyboard` remains an
  alias for compatibility.
- Tests and operator documentation cover the mouse endpoint and pairing limit.

## Reason

Provide driverless keyboard and mouse emulation when BoxBrain is physically
connected without conflating USB attachment with Bluetooth authorization.

## Dependencies

Linux ConfigFS/libcomposite, one Pi USB device controller, RNDIS, and HID gadget
functions. Bluetooth implementation will depend on the installed BlueZ service.

## Future implications

The next live step is a rollback-protected USB maintenance-window proof.
Bluetooth remains a separate reviewed feature.
