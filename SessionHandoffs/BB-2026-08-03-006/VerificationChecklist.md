# Verification Checklist

- [x] Exact authorization was received for the first attempt.
- [x] Failure stopped without sequence replay.
- [x] Gadget state, carrier, device nodes, and neighbor were inspected.
- [x] Retry is limited to `EAGAIN` and `EWOULDBLOCK`.
- [x] Partial and other failed writes remain fatal.
- [x] Retry count is bounded to approximately one second.
- [x] All 58 edge-agent tests pass.
- [x] Full repository validation passes.
- [ ] BoxBrain 0.14.1 is deployed and healthy.
- [ ] A fresh exact confirmation is received before retrying enrollment.
- [ ] Key-only SSH to the target is proven.
