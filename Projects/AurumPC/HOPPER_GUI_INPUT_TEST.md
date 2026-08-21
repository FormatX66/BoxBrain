# Hopper GUI, boot, and input test lane

Branch: `aurum/hopper-gui-input-test-20260821`

This lane starts from the standalone `aurum/trunk-v0.01` build. It does not
include StateWeave, the adaptive-kernel experiment, or their combined branch.
Echo Rally remains a manual Easter egg and is not restored as an unattended
startup surface.

## Update the installed Hopper runtime

From Hopper's root-owned Aurum recovery console, fetch the branch and stage the
guarded helper without changing the current checkout first:

```sh
workspace=/var/lib/aurum/workspace/BoxBrain
branch=aurum/hopper-gui-input-test-20260821
git -C "$workspace" fetch --no-tags origin "$branch"
git -C "$workspace" show "origin/$branch:installer/prepare-hopper-gui-input-test.sh" \
  > /run/prepare-hopper-gui-input-test.sh
sh /run/prepare-hopper-gui-input-test.sh
```

The helper refuses a dirty workspace or a machine without an installed Aurum
receipt. It fetches the exact test branch, applies only the runtime allowlist,
installs the bounded libinput/wake configuration, restarts the Hopper GUI, and
records `/var/lib/aurum/state/hopper-gui-input-test.json`. No reflash or reboot
is required for the live GUI/input update.

The boot screen is visible on the next normal boot. The recovery console stays
on `tty1`; the graphical desktop remains on `tty2`.

## Physical checks

1. Confirm the Aurum loading screen advances through hardware, input, network,
   workspace, verification, and desktop.
2. Confirm the Hopper desktop appears once and Echo Rally does not relaunch.
3. Open the loopback GUI and switch Balanced, Focus, and Engineering views.
4. Click with the external mouse and tap/click with the trackpad.
5. Suspend and resume once, then verify both pointer paths still respond.
6. In Hardware, confirm the pointer count, trackpad count, and wake-policy state.

If the runtime cannot be pulled, use the `Aurum-Hopper-GUI-Input-Test-20260821`
ISO artifact produced by the branch workflow. Keep the currently working Aurum
media available as the recovery path.
