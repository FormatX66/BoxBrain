# Verification Checklist

- [x] Exact Pi serial matched before deployment.
- [x] Archive SHA-256 matched before extraction.
- [x] 43 self-contained Pi bundle tests passed.
- [x] Guarded upgrader reported 0.13.0 installed and verified.
- [x] Three existing BoxBrain services are active.
- [x] Rollback archive is `root:root` mode `600`.
- [x] USB gadget service remains disabled/inactive and no HID endpoints exist.
- [x] Live API reports all five canonical transports.
- [x] Controller tunnel restored; controller sees Pi connected at 0.13.0.
- [ ] Running controller/dashboard supports and renders connection records.
- [ ] Ethernet peer is visible, identified, and authorized.
