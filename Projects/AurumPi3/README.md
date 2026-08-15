# Aurum Pi3 v0.01

Aurum Pi3 v0.01 is a direct-to-microSD ARM64 image for Raspberry Pi 3-class hardware. It uses a pinned Raspberry Pi OS Lite 64-bit image only as the temporary hardware/firmware compatibility substrate, then injects the bounded Aurum runtime and Codelation payload.

## Target

Primary target: Raspberry Pi 3B / 3B+ / 3A+ using the BCM2837/BCM2837B0 family and booting from microSD.

The build emits:

- `Aurum-Pi3-v0.01-arm64.img.xz`
- `Aurum-Pi3-v0.01-arm64.img.xz.sha256`
- `Aurum-Pi3-v0.01-arm64.manifest.json`
- `Aurum-Pi3-v0.01-capability-update.tar.gz`
- `Aurum-Pi3-v0.01-capability-update.manifest.json`
- `Aurum-Pi3-v0.01-capability-update.manifest.json.sha256`

The compressed image can be selected directly as a custom image in Raspberry Pi Imager. It can also be decompressed and raw-written with another imaging tool.

## Boot contract

On a working Pi 3 boot, Aurum starts on HDMI/tty1 and also attempts a serial console through `/dev/serial0`. The readiness contract is:

`AURUM_PI3_READY version=0.01 target=raspberry-pi-3 arch=aarch64 ... selftest=ok`

A CI image-structure verification is not a substitute for a physical Pi boot. Physical readiness is only promoted after that marker is observed on actual Pi 3 hardware.

## Local-first capability loop

The Aurum console exposes a bounded semantic surface. It does not accept arbitrary shell commands.

- `capabilities` inventories implemented capabilities and separately reports whether each is discovered, verified, and authorized.
- `network`, `storage`, `usb`, `processes`, `services`, and `hardware` run read-only local probes.
- `observe [capability]` reads the last persisted observation without probing again.
- `rescan [capability|all]` repeats bounded probes and persists the new results.
- `frontier` or `next-gap` selects the next unverified capability or local barrier to revisit.
- `json <command>` emits a single compact JSON document. For scripts, `/opt/aurum/aurum_pi3_console.py --json <command>` does the same without the interactive readiness banner.

Capability state is Aurum-owned at `/var/lib/aurum-pi3/capability-state.json`. A failed or unavailable probe is recorded as a barrier only for that capability; other probes and commands continue to work.

`reboot` and `poweroff` do nothing without confirmation. Their exact action forms are `reboot confirm` and `poweroff confirm`.

## Update capability code without reflashing

Each image workflow artifact includes a small capability update bundle next to a manifest and the manifest's SHA-256 file. Copy all three files to the Pi on removable media, or serve the manifest and bundle together over HTTPS. Obtain the expected manifest SHA-256 from the workflow artifact/checksum through a trusted path.

First inspect the update; this verifies the caller-supplied manifest SHA-256, the package SHA-256, the exact file allowlist, each file digest, paths, modes, size bounds, and Python syntax without installing anything:

```text
upgrade inspect /media/usb/Aurum-Pi3-v0.01-capability-update.manifest.json <manifest-sha256>
```

Only then apply it with the explicit confirmation token:

```text
upgrade apply /media/usb/Aurum-Pi3-v0.01-capability-update.manifest.json <manifest-sha256> confirm
```

The updater accepts only a local file or HTTPS manifest, installs only manifest-listed regular files below `/opt/aurum`, makes a local backup, records the applied manifest under `/var/lib/aurum-pi3/updates`, and requests an explicit `reboot confirm` to activate the new console. A failed update is contained to the update operation and attempts to roll back files already replaced.

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
