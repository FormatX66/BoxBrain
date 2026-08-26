# Experimental Pi 3 Headless-Control Handoff

This handoff keeps the current experimental Pi 3 usable without treating a
software console as a physical recovery system. It is preparation, not live
deployment authority.

## Current route

The safest no-typing route for the current Raspberry Pi OS card is the already
proven strict, key-only SSH path at `169.254.129.122`. Every new live session
still fails closed until the single pinned host key, `Raspberry Pi 3` model
marker, and serial `00000000a6a7df7f` all match. The USB3 HDMI capture remains
the independent view of boot state.

Generate the local zero-authority receipt from the repository root:

```powershell
python Projects/Aurum/Germ/pi3_headless_readiness.py `
  --identity Projects/AdaptiveDrivers/config/pi3-identity.json `
  --known-hosts Projects/AdaptiveDrivers/config/pi3_known_hosts `
  --private-key C:\Users\bruce\.ssh\id_ed25519 `
  --output data/aurum/pi3-headless-readiness.json
```

The command performs no network operation. It validates the exact pinned target,
the single-entry host trust, and the controller key locally. Its receipt cannot
grant authority or claim that the Pi is presently reachable.

## Warm routes

- The repository's SSH-tunneled noVNC console can improve convenience after
  deployment, but it depends on the same running OS and SSH service. It is not a
  recovery route and should not be installed merely to create a second-looking
  view of the same dependency.
- Aurum Early KVM is implemented and repository-tested for the Raspberry Pi Tiny
  Seed image. It is not proven as a retrofit for this Raspberry Pi OS card, so
  its fresh TLS/HMAC authority package must remain off this card.
- A separate physical KVM can provide the independent input path that software
  on the target cannot. Its hardware identity, capture route, and authority must
  be established in a separate bounded lane before use.

## Exact remaining live gate

Strict SSH automation needs only a fresh bounded TCP/22 observation followed by
strict key-only model-and-serial proof; after that, no local typing is required.

Full KVM deployment remains `waiting`. Before that state may advance, all of the
following must be true:

1. A verified rollback image and receipt protect the current experimental card.
2. Fresh live evidence matches the exact model and serial.
3. The chosen KVM payload is compatible with this boot environment and has
   immutable hashes.
4. USB3 HDMI capture remains independently usable during the canary.
5. The operator explicitly authorizes the selected service, input, and any
   network changes.
6. Input, disconnect release, loss-of-network behavior, and rollback are tested
   before promotion.

Until then, keep the current card unchanged, use strict SSH as the autonomous
control plane, and preserve HDMI capture as evidence rather than silently
turning convenience software into Last Known Good.
