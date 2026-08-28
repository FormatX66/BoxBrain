# Hopper recovery-hardening generation

This generation starts from the exact restored LKG at
`f3c0a2d3f59a22f496e4bf29dff614136bfe7abd`. It changes only the guarded Aurum
runtime, input system assets, verification contracts, and their tests. It does
not replace the current Wi-Fi configuration, landscape graphics, logo, crop, or
presentation assets.

## Running-seed delivery

Delivery remains:

`current seed -> discover -> pull -> verify -> stage -> apply -> prove -> become next seed`

The updater snapshots the saved Aurum, NetworkManager, and wpa_supplicant
profiles plus current network state before replacement. After the GUI and input
path are refreshed, it verifies that the same profile set, content hashes, file
modes, and any pre-existing online/interface state remain. The receipt is
secret-safe and never records profile contents, SSIDs, or credentials.

The HTML projection is no longer allowed to claim primary readiness merely
because pixels are visible. It requires a detected readable keyboard, a
detected readable pointer, and the Xorg libinput event driver. Input bootstrap
and resume recovery load the common HID, PS/2, and AT keyboard paths and retrigger
input discovery before the GUI starts.

## GUI recovery console

Both the primary HTML projection and the Pygame fallback keep a small recovery
panel visible. It exposes only named bounded actions:

- status;
- input recovery;
- Wi-Fi reconnect;
- update availability check;
- GUI restart on the HTML projection.

The panel delegates to the existing receipted Aurum control executor. It has no
raw shell, arbitrary command, arbitrary Git endpoint, or direct promotion
control. `Ctrl+Alt+F1` remains a fallback but is no longer the only recovery
surface.

## Acceptance boundary

The exact candidate commit must pass source tests and the existing UEFI/HP
physical-twin workflow before it can replace the propagation branch LKG. After
landing on Hopper, `become_next_seed` remains false until all of these are true
for that same generation:

1. installed runtime and system-asset hashes match the verified stage;
2. the physical GUI is running through an identified primary or fallback path;
3. a real keyboard event and a real pointer event have reached the GUI during
   the current boot;
4. the bounded GUI recovery console returns a status receipt and exposes every
   required named action with raw shell disabled;
5. the saved Wi-Fi profile set and any previously online/interface state match
   the pre-update snapshot;
6. the existing bounded GPT and system-integration proofs pass.

If any check is missing, the generation is retained as reversible
`applied-not-proven`; it is not promoted to the next running seed.
