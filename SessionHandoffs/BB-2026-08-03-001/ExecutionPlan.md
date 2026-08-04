# Execution Plan

1. Review and merge the source-only composite USB changes.
2. Confirm Wi-Fi or Ethernet management remains available on the Pi.
3. Run `sudo boxbrainctl usb-hid preview`.
4. Stage with exact authorization; do not reboot outside the maintenance window.
5. Reboot separately, confirm `usb0`, `/dev/hidg0`, and `/dev/hidg1`, then test
   host enumeration on the disposable target.
6. Commit before the rollback timer expires only when all checks pass.
7. Resolve the Bluetooth pairing-window and bond-retention questions.
8. Implement and test Bluetooth HID as a separate disabled-by-default service.
