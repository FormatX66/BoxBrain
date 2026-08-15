# Aurum Pi3 v0.01

Aurum Pi3 v0.01 is a direct-to-microSD ARM64 image for Raspberry Pi 3-class hardware. It uses a pinned Raspberry Pi OS Lite 64-bit image only as the temporary hardware/firmware compatibility substrate, then injects the bounded Aurum runtime and Codelation payload.

## Target

Primary target: Raspberry Pi 3B / 3B+ / 3A+ using the BCM2837/BCM2837B0 family and booting from microSD.

The build emits:

- `Aurum-Pi3-v0.01-arm64.img.xz`
- `Aurum-Pi3-v0.01-arm64.img.xz.sha256`
- `Aurum-Pi3-v0.01-arm64.manifest.json`
- `Aurum-Pi3-runtime-<version>-<revision>-arm64.tar.gz`
- `Aurum-Pi3-runtime-<version>-<revision>-arm64.manifest.json`
- `Aurum-Pi3-runtime-<version>-<revision>-arm64.manifest.json.sha256`

The compressed image can be selected directly as a custom image in Raspberry Pi Imager. It can also be decompressed and raw-written with another imaging tool.

## Application self-update

New images keep immutable application releases below `/opt/aurum/releases` and atomically select one through `/opt/aurum/current`. The updater changes only that application/runtime layer. It does not update the Raspberry Pi boot firmware, kernel, partition table, or base operating system.

The update contract is:

1. read a manifest whose SHA-256 was supplied out of band by the operator;
2. require the exact `authorize-network` token before any HTTPS access;
3. verify manifest schema, numeric version, `raspberry-pi-3` target, ARM64 architecture, and minimum updater version;
4. download/copy a complete release artifact into same-filesystem staging;
5. verify its SHA-256 and byte count, reject unsafe archive entries, and run the candidate selftest;
6. atomically switch `/opt/aurum/current` and restart the bounded console services from an independent systemd update service;
7. require a new release-specific readiness marker and active primary console;
8. automatically switch back and restart the previous release if readiness fails;
9. recover the previous release at boot if power was lost during activation.

Build a repository release artifact and its pinned manifest with:

```sh
python3 Projects/AurumPi3/build-runtime-release.py --version 0.02
```

CI publishes the resulting `.tar.gz`, manifest, and manifest `.sha256` together. Put all three on local storage/USB for the local-first path, or attach them to a repository release and use its HTTPS asset URLs. Aurum downloads a release artifact; it never executes a repository checkout merely because Git fetched it.

From the Aurum Pi3 prompt, use the manifest hash printed in the `.manifest.json.sha256` file:

```text
update-check /media/updates/Aurum-Pi3-runtime-0.02-REV-arm64.manifest.json MANIFEST_SHA256
update /media/updates/Aurum-Pi3-runtime-0.02-REV-arm64.manifest.json MANIFEST_SHA256
update-status
rollback confirm
```

Remote access is separate and explicit:

```text
update-check https://github.com/FormatX66/BoxBrain/releases/download/TAG/MANIFEST.json MANIFEST_SHA256 authorize-network
update https://github.com/FormatX66/BoxBrain/releases/download/TAG/MANIFEST.json MANIFEST_SHA256 authorize-network
```

The manifest hash is mandatory for both local and remote updates. Remote URLs must use HTTPS. `rollback confirm` selects the last healthy release; it does not accept a path or command.

## One-time v0.01 updater bootstrap (no reflash)

An already-running original v0.01 card predates the updater and therefore cannot invent an update command from its bounded prompt. Bootstrap it once using either of these exact paths:

- If an authorized underlying Pi shell is already available, copy this repository's complete `Projects/AurumPi3` directory onto the Pi and run:

  ```sh
  sudo sh /path/to/Projects/AurumPi3/bootstrap-updater-v001.sh
  ```

- If the original image exposes only the Aurum prompt, power it off, put the microSD in a Linux machine, mount the card's ext4 root partition at `/mnt/aurum-root`, open a checkout of this branch, and run:

  ```sh
  sudo sh Projects/AurumPi3/bootstrap-updater-v001.sh --root /mnt/aurum-root
  ```

Unmount the card cleanly, return it to the Pi, and boot. The script preserves the original `/opt/aurum` files, copies them into the `0.01-bootstrap` release, installs the stable updater/recovery units, and activates that same payload. It does not rewrite the card, boot partition, kernel, or firmware. This is the only one-time card-access step; subsequent application releases use the prompt commands above.

## Boot contract

On a working Pi 3 boot, Aurum starts on HDMI/tty1 and also attempts a serial console through `/dev/serial0`. The readiness contract is:

`AURUM_PI3_READY version=0.01 release=0.01-bootstrap target=raspberry-pi-3 arch=aarch64 ... selftest=ok`

A CI image-structure verification is not a substitute for a physical Pi boot. Physical readiness is only promoted after that marker is observed on actual Pi 3 hardware.

## Local-first capability loop

The Aurum console exposes a bounded semantic surface. It does not accept arbitrary shell commands.

- `capabilities` inventories implemented capabilities and separately reports whether each is discovered, verified, and authorized.
- `network`, `storage`, `usb`, `processes`, `services`, and `hardware` run read-only local probes.
- `observe [capability]` reads the last persisted observation without probing again.
- `rescan [capability|all]` repeats bounded probes and persists the new results.
- `frontier` or `next-gap` selects the next unverified capability or local barrier to revisit.
- `json <command>` emits a single compact JSON document. For scripts, `/opt/aurum/current/aurum_pi3_console.py --json <command>` does the same without the interactive readiness banner.

Capability state is Aurum-owned at `/var/lib/aurum-pi3/capability-state.json`. A failed or unavailable probe is recorded as a barrier only for that capability; other probes and commands continue to work.

`reboot` and `poweroff` do nothing without confirmation. Their exact action forms are `reboot confirm` and `poweroff confirm`.

## Build

Run on Linux with root privileges because the image is edited using loop devices and mounts:

```sh
sudo sh Projects/AurumPi3/build-image.sh
```

The upstream Raspberry Pi image is pinned by both URL and SHA-256 before any modification.

## Flash to microSD

Fastest cross-platform path: Raspberry Pi Imager → **Choose OS** → **Use custom** → select `Aurum-Pi3-v0.01-arm64.img.xz` → select the microSD card → write.

On Linux, after verifying the destination device very carefully:

```sh
xzcat Aurum-Pi3-v0.01-arm64.img.xz | sudo dd of=/dev/sdX bs=8M status=progress conv=fsync
```

Writing an image destroys the existing contents of the selected card. Never substitute a device path without positively identifying the microSD device first.
