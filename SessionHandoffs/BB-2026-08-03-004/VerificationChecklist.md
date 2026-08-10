# Verification Checklist

- [x] Existing `wlan0` connection preserved.
- [x] `bbap0` active at `10.42.194.1/24`.
- [x] DHCP active and forwarding into other interfaces rejected.
- [x] Recovery SSID visible from an external Windows Wi-Fi scan.
- [x] Pi returned after reboot over the alternate Wi-Fi path.
- [x] Composite gadget active with `usb0`, `/dev/hidg0`, and `/dev/hidg1`.
- [x] UDC configured and USB carrier present.
- [x] USB migration committed and rollback timer inactive.
- [ ] External client associated with AP and SSH verified through it.
- [ ] Keyboard and mouse effect verified on the exact disposable target.
- [x] Repository checks and guarded 0.14.0 deployment recorded.
