# Aurum Pi3 v0.01

Aurum Pi3 v0.01 is a direct-to-microSD ARM64 image for Raspberry Pi 3-class hardware. It uses a pinned Raspberry Pi OS Lite 64-bit image only as the temporary hardware/firmware compatibility substrate, then injects the bounded Aurum runtime and Codelation payload.

## Target

Primary target: Raspberry Pi 3B / 3B+ / 3A+ using the BCM2837/BCM2837B0 family and booting from microSD.

The build emits:

- `Aurum-Pi3-v0.01-arm64.img.xz`
- `Aurum-Pi3-v0.01-arm64.img.xz.sha256`
- `Aurum-Pi3-v0.01-arm64.manifest.json`

The compressed image can be selected directly as a custom image in Raspberry Pi Imager. It can also be decompressed and raw-written with another imaging tool.

## Boot contract

On a working Pi 3 boot, Aurum starts on HDMI/tty1 and also attempts a serial console through `/dev/serial0`. The readiness contract is:

`AURUM_PI3_READY version=0.01 target=raspberry-pi-3 arch=aarch64 ... selftest=ok`

A CI image-structure verification is not a substitute for a physical Pi boot. Physical readiness is only promoted after that marker is observed on actual Pi 3 hardware.

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
