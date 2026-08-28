# Hopper remote-control generation

This candidate starts from recovery-hardening LKG
`0f8bfc5cced3db6d3ab89878531907ac910d4a5a`. It preserves the current Wi-Fi
profiles and connectivity proof, the landscape GUI, logo/crop assets, keyboard
and pointer recovery, and the always-available named-action recovery console.

## Fixed remote seed sync

Hopper exposes one key-only OpenSSH identity named `aurum-remote`. It has no
password authentication, TTY, agent forwarding, X11 forwarding, arbitrary
command, Git endpoint selection, push, or interactive shell. The forced-command
adapter accepts only:

- `status`;
- `seed-sync`;
- `desktop-start`;
- `desktop-stop`;
- `desktop-tunnel`.

`seed-sync` reconnects only saved networking, fast-forwards only
`FormatX66/BoxBrain` branch `aurum/trunk-v0.01`, and hands the landed commit to
the existing runtime updater. That updater still performs discover, verify,
stage, atomic apply, rollback capture, installed-hash proof, physical/input/GPT
proof, GUI-console proof, remote-control proof, Wi-Fi persistence proof, and
the final `become_next_seed` decision. The remote command cannot bypass or
weaken those gates.

## Remote Desktop

Remote Desktop is on demand and bounded to four hours. `x11vnc` listens only on
Hopper loopback port 5900; the bundled noVNC viewer listens only on loopback
port 6080. OpenSSH permits the paired identity to forward only Hopper loopback
ports 5900, 6080, and 8765, with gateway ports disabled. Nothing listens for
VNC directly on the LAN.

On the Main PC:

1. Open Hopper's local **Remote Control** panel and note its SSH host-key
   fingerprint.
2. Run `installer/setup-aurum-hopper-remote.ps1` with Hopper's address and that
   exact fingerprint. It creates a dedicated Ed25519 key locally, pins the host
   key, and copies only the public key.
3. Paste that public key into Hopper's local pairing panel.
4. Run `installer/invoke-aurum-hopper-seed-sync.ps1` for the fixed seed update,
   or `installer/open-aurum-hopper-remote-desktop.ps1` for browser Remote
   Desktop.

The private controller key never enters Hopper or Git. Pairing replaces the
single prior controller public key and records a secret-safe fingerprint
receipt.

## Aurum GPT prompt

The primary HTML desktop again keeps the Aurum GPT conversation panel and
prompt bar visible. The Pygame recovery renderer now also has a bounded prompt
box and asynchronous send action, so falling back from HTML does not remove the
GPT surface or freeze the GUI while a model call is pending. Both surfaces use
the existing machine-sealed GPT trait and bounded tool receipts; neither asks
for or displays an API key.

## Acceptance boundary

The exact candidate must pass all source checks, build a bootable image, install
and reboot in UEFI, start and stop both loopback Remote Desktop listeners in the
installed virtual seed, retain the HP input/topology preflight, and converge the
same image digest across the independent verifiers. Until those checks pass,
the candidate is not eligible to replace `aurum/trunk-v0.01`.

After it lands on physical Hopper, the normal same-generation proofs remain in
force. Missing keyboard, pointer, physical GUI, GPT, recovery-console, remote
pairing plus a loopback Remote Desktop start/stop receipt from the current boot,
or Wi-Fi persistence evidence leaves the update reversible and
`applied-not-proven`; it does not become the next running seed.
