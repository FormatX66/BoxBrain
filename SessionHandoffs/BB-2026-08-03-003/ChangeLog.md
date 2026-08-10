# Change Log

## Runtime changes

- Upgraded `/opt/boxbrain` from 0.10.0 to 0.13.0.
- Restarted the three existing BoxBrain services through the guarded upgrader.
- Created root-only rollback archive
  `/var/backups/boxbrain/pre-0.13.0-20260804T004551Z.tar.gz`.
- Restored the existing Windows-to-Pi loopback SSH tunnel.

## Preserved boundaries

- Composite USB HID service remains disabled and inactive.
- `/dev/hidg0` and `/dev/hidg1` were not created.
- Bluetooth remained unpaired; NFC remained absent.
- No Windows networking or target configuration changed.

## Future implications

The Pi now publishes the connection map; the local controller and dashboard
still need their committed source rollout to display it.
