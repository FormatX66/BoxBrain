# BoxBrain Pi 4 One-Shot Rescue

BoxBrain one-shot rescue lets an authorized operator arm exactly one Raspberry
Pi boot that presents a checksum-verified rescue image through the Pi USB device
controller. The pending state is reset to `normal` during early boot, before the
image checksum is verified or the USB gadget is created. The next Pi reboot
therefore returns to normal BoxBrain even when rescue preparation fails.

## Safety boundaries

- Rescue media is copied into `/var/lib/boxbrain/rescue-images`; media is never
  stored in Git.
- The registry accepts only regular files inside that dedicated image store.
  Block devices, the Pi root filesystem, and arbitrary external paths cannot be
  exported.
- Imported content must match an operator-supplied SHA-256 checksum.
- Every new registry entry records the public official URL or signed manifest
  used as the checksum source.
- Media defaults to read-only. Read/write mode must be explicitly recorded at
  import time.
- The registry records image kind, ARM64/x86-64/multi architecture, BIOS/UEFI/
  Pi 4 compatibility, Secure Boot status, signature metadata, size, and SHA-256.
- Arming, cancellation, import, and normal reboot use exact confirmation gates.
- `reboot-normal` is a preview unless `--execute` is supplied.

This feature does not alter permanent target boot order, Secure Boot, TPM,
firmware passwords, storage-controller mode, or other firmware security state.

## State lifecycle

1. `rescue arm` validates Pi 4 USB-device hardware, selects exactly one matching
   verified image, rechecks its checksum, and writes `next-boot.json`.
2. `boxbrain-rescue-early.service` runs before the USB gadget service. It first
   rewrites the pending state to `normal`, then verifies the consumed image and
   writes `active-boot.json`.
3. The composite gadget adds one mass-storage function only when the active
   state points to a valid file in the dedicated rescue image directory.
4. On the following Pi boot, early consumption sees `normal`, removes the active
   state, and starts the usual BoxBrain USB Ethernet/HID gadget without rescue
   media.

Atomic JSON replacement and timestamped state backups protect configuration
updates. If a state replacement fails, the previous file is restored. If early
image validation fails, the active state is removed while the already-reset
next-boot state remains normal.

The guarded application upgrader backs up installed code, configuration, and
rescue registry/state, but deliberately excludes both the multi-gigabyte
`rescue-images` payload directory and the reproducible synced
`drive/rescue-media` cache. The installer does not replace or remove those
persistent media directories, so rollback restores the registry while leaving
the unchanged verified media in place.

## CLI

All examples run locally on the Pi. Use `sudo` when the current account cannot
write the protected state directory.

```sh
boxbrainctl rescue status
boxbrainctl rescue images
boxbrainctl rescue hardware-check
```

Import a legitimate administrator-supplied image. Windows ISO files remain
outside Git and use the same checksum gate as other media:

```sh
sudo boxbrainctl rescue import /media/operator/rescue.iso \
  --id windows-recovery-x64 \
  --kind windows \
  --architecture x86_64 \
  --boot-compatible uefi \
  --secure-boot supported \
  --signed \
  --sha256 <trusted-sha256> \
  --checksum-source <public-official-url-or-signed-manifest> \
  --authorized \
  --confirmation 'IMPORT VERIFIED RESCUE IMAGE'
```

ARM64 and x86-64 Kali builds are separate registry entries. Select the target
architecture when arming a standard profile:

```sh
sudo boxbrainctl rescue arm rescue:kali \
  --target-architecture x86_64 \
  --authorized \
  --confirmation 'ARM ONE-SHOT RESCUE'
```

An exact image may be selected with `rescue:<image-id>`. Cancel before reboot:

```sh
sudo boxbrainctl rescue cancel \
  --authorized \
  --confirmation 'CANCEL ONE-SHOT RESCUE'
```

Force saved state back to normal without rebooting:

```sh
sudo boxbrainctl rescue reboot-normal \
  --authorized \
  --confirmation 'REBOOT NORMAL BOXBRAIN'
```

Add `--execute` only when an immediate Pi reboot is intended and authorized.

## Web controls

The local/tunneled dashboard links to `/rescue`. Read-only endpoints expose
status, image metadata, and hardware readiness; full checksum verification
remains an explicit CLI operation. Mutating requests require
loopback access, a per-process CSRF token, and the same exact confirmation text
as the CLI. Media import remains CLI-only so browsers never upload large rescue
images into the management process.

## Hardware activation checklist

Before enabling this on a live Pi 4:

1. Back up the SD card or boot volume.
2. Confirm `boxbrainctl rescue hardware-check` reports `ready: true`, exactly one
   USB device controller, and `actual_boxbrain_filesystem_exported: false`.
3. Import a small test image with a separately verified SHA-256.
4. Arm the test image, reboot the Pi once, and confirm the target sees rescue
   media plus BoxBrain USB Ethernet, keyboard, and mouse.
5. Power-cycle or reboot the Pi again and confirm the rescue mass-storage device
   is absent while normal BoxBrain connectivity returns.
6. Exercise a deliberately corrupted test image and verify the attempt fails
   closed and the following boot remains normal.

Do not activate rescue mode on an irreplaceable target until the disposable
hardware test and normal-boot recovery both pass.
