# Hopper GUI, boot, and input growth release

Branch: `aurum/hopper-gui-input-test-20260821`

This lane starts from the standalone `aurum/trunk-v0.01` build. It does not
include StateWeave, the adaptive-kernel experiment, or their combined branch.
Echo Rally remains a manual Easter egg and is not restored as an unattended
startup surface.

## Unattended delivery

After the verified test lane is promoted to `aurum/trunk-v0.01`, Hopper's
machine-bound autonomy worker discovers it during the normal five-minute growth
cycle. The worker fast-forwards only the allowlisted trunk, atomically updates
the guarded Python runtime and system assets, enables/restarts the input wake
service, refreshes the GUI, and records its receipts. No operator shell command,
reflash, or live-update reboot is required.

The managed system assets are sourced from `Projects/AurumPC/runtime-assets` and
share one implementation with the bootable ISO. They include the deterministic
libinput configuration, input bootstrap service, post-resume wake hook, and
primary-console loading-screen unit. Runtime replacement keeps displaced-state evidence
under Aurum state before changing any installed file.

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

If Hopper is powered off or offline, growth remains published on the allowlisted
trunk and is consumed automatically after connectivity returns. The
`Aurum-Hopper-GUI-Input-Test-20260821` ISO artifact remains the recovery-media
path, not the normal update mechanism.
