# Aurum PC v0.01

Aurum PC is the removable-media x86_64 bring-up environment for Aurum. Linux is used only as a temporary hardware compatibility substrate. Physical live media boots directly into the native full-screen Aurum Setup application; the bounded `aurum>` console remains a serial verification and last-resort recovery surface.

## Graphical setup

The normal USB workflow contains no shell commands:

1. Boot the Aurum USB on a compatible 64-bit PC in UEFI or legacy BIOS mode.
2. Aurum Setup opens automatically and lists only safe, non-USB internal drives.
3. Optionally connect Ethernet or choose Wi-Fi in the graphical network screen.
4. Select a drive, then choose **Erase & Install Fresh** or **Repair Aurum**.
5. Review the selected drive and confirm once on screen.
6. Wait for filesystem, runtime, dual-mode bootloader, and two-entry boot-menu verification.
7. Choose **Shut Down Safely**, remove the USB after power is off, and start the PC.

Fresh installation cleans and repartitions only the selected drive. Repair never partitions or formats: it checks the existing Aurum filesystem, refreshes the bundled runtime and services, rebuilds both UEFI and legacy boot paths, and verifies the result. Multiple internal drives are supported through explicit graphical selection. The USB and any ineligible, active, removable, read-only, or protected drive are never offered as targets.

The installed menu is regenerated, not appended: it contains exactly **Aurum PC** and **Aurum PC (graphics recovery)**. Hopper's normal entry excludes its physically failing `nouveau` path while leaving other native graphics available; the recovery entry keeps the stronger `nomodeset` fallback. A short timeout preserves automatic boot while leaving the recovery choice reachable.

## Seed lifecycle

Aurum follows the canonical rule **Boot once. Grow continuously. Never move backward.** The initial seed is bootstrap infrastructure; established Aurum nodes do not require rebuilt or reflashed boot media for normal generation updates. The running seed discovers, pulls, verifies, stages, applies, proves, and becomes the next seed. If a candidate fails, Aurum heals the running seed, culls the candidate, preserves its evidence, and waits for a new forward descendant regrown from verified LKG genetics. Boot media is reserved for first seeding or true recovery conditions. See [SEED_LIFECYCLE.md](SEED_LIFECYCLE.md).

## First boot

After a verified installation, Aurum automatically:

1. captures a read-only exact-machine hardware profile from `/proc` and `/sys`;
2. derives a conservative kernel/driver plan while preserving the removable recovery path;
3. if no wireless interface exists, emits `AURUM_WIFI_DIAG` with PCI/USB network-controller candidates, modaliases, bound drivers and loaded-module evidence;
4. reconnects the Wi-Fi profile saved by Aurum Setup when one is available;
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

## Open core sharing

Aurum cores share their non-personal system state without controller pairing. Hopper exposes an open JSON core surface on port `8767`: `GET /status` returns sanitized seed state and `POST /seed-sync` runs the fixed `FormatX66/BoxBrain` `aurum/trunk-v0.01` fast-forward/apply path. Port `8765` remains reserved for Hopper's loopback GUI. The core surface is not a file server and has no shell, directory, branch-selection, push, credential, Wi-Fi-profile, home-directory, or personal-data operation.

`aurum-auto-sync.service` runs that same forward-only update automatically after saved networking comes up on every boot, retrying while the network is unavailable. `aurum-core-share.service` keeps the two open core actions available to reachable Aurum peers. Both services hide `/home`, `/root`, and `/var/lib/aurum/slush`; personal files and information belong to the user-only Slush namespace and are never part of the open core response.

## Unattended PC-01 lane

The installed PC-01 sandbox has a machine-bound unattended policy keyed to its install receipt. After the seed sees `aurum-x86-ready`, it launches `aurum_autonomy.py` outside the short seed subprocess bound. The worker holds a single-instance lock and, every five minutes, can reconnect saved networking, fast-forward only `aurum/trunk-v0.01`, atomically refresh the allowlisted `/opt/aurum` runtime and bounded system assets, run a local resumable self-build without dirtying Git, start the loopback-only GUI/arcade surfaces, and advance the adaptive driver synthesis lane.

The unattended lane never pushes Git and does not automatically reboot. Its state is receipted under `/var/lib/aurum/state/autonomy.json` and driver evidence under `/var/lib/aurum/state/driver-lab/`.

Saved Wi-Fi is reconnected at boot by `aurum-network-bootstrap.service` only when `/var/lib/aurum/state/wifi.conf` is on durable storage. The physical-discovery USB remains intentionally stateless: syncing its live overlay can update the current session, but it cannot make GUI code or credentials survive a reboot. Cross-reboot proof therefore requires the installed Hopper root (or separately authorized media with a versioned state-only volume), and the generation stays pending rather than claiming success on a volatile live overlay.

Each growth cycle also emits `/var/lib/aurum/state/seed-generation.json`, an append-only `/var/lib/aurum/state/seed-lineage-events.jsonl`, and its current `/var/lib/aurum/state/seed-lineage.json` projection. Hopper's read-only self-debug channel exposes the landed commit, forward relation, heal/cull/regrow disposition, and sanitized discover/pull, verify, stage, apply, physical projection, bounded GPT, sandboxed browser/prompt surface, keyboard/pointer, GUI recovery-console, Wi-Fi persistence, and `become_next_seed` proof without enabling remote shell control.

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
