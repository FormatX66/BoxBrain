# Aurum Early KVM

Status: **implemented for the Raspberry Pi Tiny Seed image; physical Pi 3 proof pending**

## Boundary

The Raspberry Pi ROM and firmware cannot provide network KVM. Aurum Early KVM therefore starts at the earliest honest controllable boundary: Linux userspace after local filesystems and NetworkManager, before the Tiny Seed installer.

The Raspberry Pi firmware, Linux kernel, and reference drivers remain the boot and hardware Last Known Good. Early KVM does not alter firmware, boot configuration, kernel modules beyond loading the standard `uinput` interface, or any physical driver binding.

## Activation contract

**No authority file means no listener.**

The published image contains the service and controller protocol but no live authority, secret, certificate, Wi-Fi password, or controller address. Before first boot, `prepare_early_kvm.py` writes a fresh, machine-specific handoff to the mounted FAT boot partition and a private controller file to the operator machine.

On first boot, `early_kvm_bootstrap.py` validates the whole handoff before activation. It installs the TLS identity, optional NetworkManager profile, optional SSH key, and authority with protected permissions. Authority is installed last and the physical source is consumed only after every copy verifies. A malformed optional input leaves authority on the boot partition and no listener in the root.

## Transport and input protocol

- TLS encrypts keyboard, mouse, and framebuffer traffic. The controller trusts only the fresh certificate created during physical provisioning; hostnames are not trusted implicitly.
- A separate 256-bit authority secret binds a fresh server challenge, controller identity, session, monotonic command sequence, and every command with HMAC-SHA-256.
- Only configured controller address ranges are accepted.
- Exactly one authenticated controller session may own input at a time.
- Key names, text length, pointer deltas, buttons, frame size, request size, and session duration are bounded.
- Replay, sequence change, bad MAC, unsupported input, oversize input, and second-controller attempts fail closed.
- Every disconnect releases all held keys and pointer buttons.
- Receipts record operation, sequence, outcome, controller, and session; typed text and authority secrets are never logged.

Input is created through Linux `uinput` via `python3-evdev`. This is a virtual userspace input device, not a replacement for the Pi USB, Bluetooth, keyboard, mouse, display, network, or framebuffer drivers.

## Video

The controller can request a bounded raw Linux framebuffer snapshot when `/dev/fb0` is present and authority permits it. The response is compressed, size-bounded, and SHA-256 bound before the controller writes it.

Framebuffer absence is not hidden. The protocol reports `hdmi-capture` as the fallback, and the USB3 HDMI capture attached to the controller computer remains the independent visual reference during Pi 3 proof.

## First-boot behavior

The Pi image creates a locked `aurum` account while it is built and masks Raspberry Pi OS `userconfig.service`. This prevents the vendor username prompt from blocking networking before Tiny Seed starts. SSH accepts keys only, root login is disabled, and a unique SSH host identity is generated on each Pi instead of being cloned in the image.

System startup is ordered as:

1. local filesystems;
2. physical authority bootstrap;
3. NetworkManager;
4. optional authenticated early KVM;
5. protected Germ preflight and Tiny Seed;
6. normal evidence, candidate, LKG, and rollback gates.

## Provision and control

From the Germ directory on the controller:

```text
python prepare_early_kvm.py --boot-root <mounted-boot> --controller-config <private-controller.json> --controller-cidr <controller-ip/32> --target <pi-address> --controller <name> --ssh-public-key <key.pub>
python early_kvm_controller.py --config <private-controller.json> status
python early_kvm_controller.py --config <private-controller.json> type "text"
python early_kvm_controller.py --config <private-controller.json> key KEY_ENTER press
python early_kvm_controller.py --config <private-controller.json> key KEY_ENTER release
python early_kvm_controller.py --config <private-controller.json> mouse --dx 10 --dy -4
python early_kvm_controller.py --config <private-controller.json> frame --output frame.raw
python early_kvm_controller.py --config <private-controller.json> release-all
```

If Wi-Fi is needed, add `--wifi-ssid`; the password is read from `AURUM_KVM_WIFI_PASSWORD` or a no-echo prompt and is never accepted as a command-line value.

## Physical promotion gates

The implementation may be called repository-verified after its protocol, builder, and image-inspection workflows pass. It may be called Pi-verified only after the experimental Pi 3 proves:

1. exact model and serial identity;
2. no vendor first-user prompt;
3. networking without a local keyboard;
4. pinned TLS and HMAC session acceptance from the allowed controller only;
5. keyboard and pointer behavior observed through USB HDMI capture;
6. disconnect release behavior;
7. no system-driver mutation;
8. preserved reference driver and LKG;
9. bootstrap, session, and rollback evidence sealed.

QPU is held: cryptographic transport, event injection, and bounded control do not benefit measurably. A future QPU branch may optimize large candidate-driver parameter searches after the physical KVM and driver evidence gates pass, with the classical path remaining authoritative.
