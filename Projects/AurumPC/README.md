# Aurum PC v0.01

Aurum PC is the removable-media x86_64 bring-up environment for Aurum. Linux is used only as a temporary hardware compatibility substrate; the operator surface remains the bounded `aurum>` console.

## Seed lifecycle

Aurum follows the canonical rule **Boot once. Grow continuously.** The initial seed is bootstrap infrastructure; established Aurum nodes do not require rebuilt or reflashed boot media for normal generation updates. The running seed discovers, pulls, verifies, stages, applies, proves, and becomes the next seed. Boot media is reserved for first seeding or true recovery conditions. See [SEED_LIFECYCLE.md](SEED_LIFECYCLE.md).

## First boot

On a physical primary console Aurum automatically:

1. captures a read-only exact-machine hardware profile from `/proc` and `/sys`;
2. derives a conservative kernel/driver plan while preserving the removable recovery path;
3. if no wireless interface exists, emits `AURUM_WIFI_DIAG` with PCI/USB network-controller candidates, modaliases, bound drivers and loaded-module evidence;
4. attempts Wi-Fi bring-up, asking for credentials only when a wireless interface is available;
5. verifies addressing, routing, DNS and GitHub TCP connectivity;
6. refreshes only the allowlisted `FormatX66/BoxBrain` trunk when online;
7. seeds Aurum state, runs its bounded self-test, and starts the resumable local-first self-build;
8. starts the machine-bound Hopper desktop when the installed receipt authorizes it, while keeping the bounded `aurum>` recovery console on `tty1`.

The serial/QEMU console disables autonomous first boot so CI can drive deterministic verification without racing the physical-console build.

## Hopper

The original PC-01 physical sandbox is now **Hopper**. The name preserves the history of the machine as Grace's first real gaming PC while also giving a quiet nod to Grace Hopper. Its machine-bound autonomy policy verifies the installed NVMe serial/size before applying the persistent hostname `hopper`; the previous hostname is backed up in Aurum state.

Hopper's first Aurum application is **Echo Rally**, a dependency-free Pong-like proof running through the loopback-only Aurum arcade runtime. Every fourth paddle return leaves a temporary echo well at that impact point. The wells gently bend later ball trajectories, so the arena literally remembers earlier play. The game exercises canvas rendering, frame timing, keyboard input, pointer/touch input, synthesized audio, pause/reset, solo AI and two-player control without exposing host actuation.

The [Hopper GUI, boot, and input growth release](HOPPER_GUI_INPUT_TEST.md) packages the next presentation profiles, a real-stage VT loading screen, and bounded mouse/trackpad wake handling without pulling in the StateWeave/adaptive-kernel experiment. Its verified capability is promoted through the allowlisted Aurum trunk so Hopper consumes it through the unattended growth loop rather than an operator shell procedure.

The [Hopper recovery-hardening generation](HOPPER_RECOVERY_HARDENING.md) extends that running-seed path with keyboard and pointer event proof, explicit Wi-Fi persistence proof, and a small named-action recovery console inside both GUI renderers. It deliberately leaves the established Wi-Fi configuration and landscape presentation assets outside the update payload.

The [Hopper remote-control generation](HOPPER_REMOTE_CONTROL.md) adds a fixed
remote seed-sync command, an on-demand browser Remote Desktop carried only
inside a key-authenticated SSH tunnel, and the Aurum GPT prompt panel on both
the primary HTML projection and Pygame fallback. It builds on, rather than
replaces, the recovery-hardening LKG.

## Unattended PC-01 lane

The installed PC-01 sandbox has a machine-bound unattended policy keyed to its install receipt. After the seed sees `aurum-x86-ready`, it launches `aurum_autonomy.py` outside the short seed subprocess bound. The worker holds a single-instance lock and, every five minutes, can reconnect saved networking, fast-forward only `aurum/trunk-v0.01`, atomically refresh the allowlisted `/opt/aurum` runtime and bounded system assets, run a local resumable self-build without dirtying Git, start the loopback-only GUI/arcade surfaces, and advance the adaptive driver synthesis lane.

The unattended lane never pushes Git and does not automatically reboot. Its state is receipted under `/var/lib/aurum/state/autonomy.json` and driver evidence under `/var/lib/aurum/state/driver-lab/`.

Each growth cycle also emits `/var/lib/aurum/state/seed-generation.json`. Hopper's read-only self-debug channel exposes the landed commit and sanitized discover/pull, verify, stage, apply, physical projection, bounded GPT, keyboard/pointer, GUI recovery-console, restricted remote-control, Wi-Fi persistence, and `become_next_seed` proof without enabling remote shell control.

## One-shot seed recovery

`build-hopper-recovery-iso.sh` produces a true-recovery image for a specific
Hopper commit and exact worktree-only path set. The image uses a small live
overlay, boots directly into a noninteractive recovery target, proves the
installed receipt plus physical internal-drive identity, mounts read-only for
preflight, and refuses any unlisted or staged change. Before restoring the
allowlisted paths from the current commit, it saves a binary patch and receipts
under `/var/lib/aurum/state/recovery/`. It then proves Git clean and powers off.
The builder discovers the source image's exact kernel/initrd pair and refuses to
produce UEFI recovery media unless the kernel carries an embedded Secure Boot
signature.

This path is not a normal generation mechanism. Once the obstruction is
removed, Hopper returns to `current seed -> discover -> pull -> verify -> stage
-> apply -> prove -> become next seed` and the Pi returns to its normal BoxBrain
USB role on its next boot.

## Adaptive driver synthesis

`aurum_driver_synthesis.py` builds a confidence-scored exact-device dossier from OS hardware metadata, modaliases, the currently proven bound driver and module hash/metadata, and repeated read-only controlled observations. It queues one non-critical target at a time and emits a candidate behavior contract. When the matching kernel build toolchain is available it may compile a non-binding shadow `.ko` carrier to prove the build path.

The shadow carrier contains no device-id table or probe callback and is never loaded. Network, graphics, input and other non-critical devices can therefore begin model/contract/compile work while storage and boot-critical devices stay gated. Later physical replacement still requires a separate one-target-at-a-time backup, behavior-comparison and automatic-restore gate.

## Safety

Hardware inventory is read-only and defaults to `/run/aurum`. The removable boot path remains the known-good recovery path. Aurum does not automatically overwrite an internal disk. Physical driver replacement remains one target at a time with compile-before-load, behavior comparison, backup and automatic-restore gates. Storage/boot-critical replacement, firmware/NVRAM/OTP/fuse writes, power/clock/voltage/thermal/reset control and unbounded raw MMIO/PIO remain separately gated.
