# Kali Pi Edge Agent

The Kali Pi implementation is part of BoxBrain, not a second BoxBrain product.
The Flutter/FastAPI application remains the controller and operator interface.
The Pi runs a restricted edge agent close to USB-connected or explicitly
authorized private-network targets.

## Responsibility split

| Component | Responsibility |
| --- | --- |
| Flutter dashboard | Operator status, task intent, safety state, and audit visibility |
| FastAPI controller | Authentication, policy, task state, audit, and edge-agent inventory |
| Kali Pi edge agent | Authorized read-only diagnostics, bounded private-scope assessment, and recommendations |
| Windows Sandbox observer | View-only frames from the isolated local Sandbox |

The controller reads only the agent's bounded summary: version, hostname,
connection state, authorized-target count, and recommendation count. Raw
diagnostic reports, SSH keys, recovery credentials, and Pi runtime state stay
outside the controller response and outside Git.

## SSH-tunnel connection

The edge agent dashboard/API listens on Pi loopback port `8787`. Forward it to
the controller workstation:

```powershell
ssh -i "<path-to-your-dedicated-pi-key>" `
  -L 8787:127.0.0.1:8787 `
  kali@<pi-hostname-or-address>
```

Keep that SSH process open. The controller reads
`http://127.0.0.1:8787/api/v1/status` and exposes the sanitized result at
`GET /api/v1/edge-agents`. The endpoint is configured with:

```powershell
$env:BOXBRAIN_KALI_PI_AGENT_URL = "http://127.0.0.1:8787"
```

The controller rejects non-loopback URLs, credentials in URLs, HTTPS URLs, and
extra URL paths. This keeps edge-agent access on the authenticated SSH channel
and prevents the setting from becoming a general network-fetch feature.

The optional Pi screen uses a separate loopback VNC/WebSocket SSH tunnel and is
not part of the controller API or target executor. A current-user Windows
watcher may open it when the preferred Pi SSH path comes online without
changing that boundary. Its canonical setup is documented under
[Optional live Pi screen](../edge/kali-pi-agent/README.md#optional-live-pi-screen).

## USB onboarding boundary

The onboarding service listens only on the dedicated USB gadget address
`10.12.194.1:8788`. Version 0.6 migrates the old `0.0.0.0` default to that
address while preserving any other operator-selected bind address.

Normal onboarding still requires an explicit target-side `AUTHORIZE`
confirmation and creates a restricted, key-only diagnostic account. It does
not install an administrator channel or copy a private key to the target.

## Recovery access point

Version 0.14 adds an optional recovery access point without replacing the Pi's
existing Wi-Fi client. The Pi creates a separate `bbap0` virtual interface on
the physical radio's current channel, uses `10.42.194.1/24`, supplies DHCP only
to attached AP clients, and rejects forwarding from `bbap0` into other
interfaces. WPA2/CCMP credentials are generated on the Pi and stored root-only;
preview and status commands never print the key.

Installation leaves the AP disabled. Staging requires explicit authorization,
starts it immediately, and arms a 15-minute rollback. Commit is accepted only
after the interface, address, NetworkManager connection, and isolation table
are active. The AP provides a fallback SSH path; it does not expand target
authority or expose the USB-only onboarding listener automatically.

## Headless Windows keystroke bootstrap

Version 0.12 adds an optional, preview-first USB-HID fallback for a physically
attached Windows target with an unlocked interactive administrator console. It
types only a fixed US-layout PowerShell sequence that downloads the existing
Windows link helper from the Pi's USB-only onboarding address, verifies its
SHA-256, and invokes its existing authorization gate. It cannot accept
arbitrary text and never types a password, Wi-Fi passphrase, or saved `Key
Content`.

The source includes an optional ConfigFS composite profile containing RNDIS
USB Ethernet (`usb0`), a boot-protocol keyboard (`/dev/hidg0`), and a
boot-protocol three-button mouse with relative X/Y/wheel reports
(`/dev/hidg1`). Installing the files leaves that profile disabled. Staging it requires root, exact
authorization, and a working non-USB management interface; it modifies the
next-boot module/service configuration without rebooting and arms a 15-minute
rollback. A post-reboot commit is accepted only while the service, USB network,
both HID devices, UDC binding, and absence of legacy `g_ether` are all verified.

USB HID and Bluetooth HID are separate transports. Plugging in the USB cable
does not make a USB device enumerate as Bluetooth. A future Bluetooth HID path
may use USB attachment as a trigger for a short pairing window, but it must
remain disabled until an operator explicitly authorizes pairing and a bounded
trusted-host policy is selected. The current change does not advertise,
pair, or accept Bluetooth clients automatically.

The migration design follows the kernel's
[ConfigFS gadget](https://docs.kernel.org/usb/gadget_configfs.html) and
[HID gadget](https://docs.kernel.org/usb/gadget_hid.html) contracts and keeps
the Raspberry Pi project's established RNDIS/`usb0` model. It is currently a
Windows-focused USB profile; cross-host ECM support is not claimed.

Keystroke execution additionally requires `--authorized` and the exact
`CONNECT HEADLESS WINDOWS` confirmation. It refuses an already linked target,
and a new result is not successful until the Pi proves the restricted target
account over key-only SSH. Failure produces an unverified state and no
automatic retry. Installation never changes the active gadget or reboots the
Pi.

This fallback cannot operate at a login screen, create an interactive session,
or satisfy UAC that requires credentials. Sessionless servers still require
WinRM/SSH, a hardware or hypervisor console, or a preinstalled agent. The
canonical managed-Windows repair boundary remains BrainConnect's HTTPS/JEA
Windows Headless Rescue workflow.

## Authorized Wi-Fi/Ethernet targets

Version 0.7 keeps USB-C discovery automatic and adds explicit private-network
enrollment. First run the target-side onboarding script and allow the Pi's exact
RFC1918/link-local address through the target firewall. Then, on the Pi:

```bash
boxbrainctl add-target <target-private-ip> --authorized
```

The local Unix control socket enforces the exact authorization assertion, checks
that the address is private or link-local, rejects loopback and the USB gadget
route, verifies key-only SSH, and caps the target registry. Enrolled targets are
rechecked on every monitor interval and retain `connected` or `offline` state.
The controller continues to receive only the bounded target count; enrollment,
keys, routes, and raw diagnostics stay on the Pi.

## USB-C Wi-Fi provisioning and access-control audit

Version 0.8 adds a separate administrator-approved Windows helper for
provisioning the Pi from the computer's currently connected Wi-Fi profile. The
helper is fixed to the USB gadget address `10.12.194.1`, requires a previously
trusted Pi SSH host key, and sends the passphrase only through SSH standard
input. The passphrase is never placed in command arguments, BoxBrain reports,
or logs. NetworkManager retains the resulting system connection using its
root-only profile storage.

Discovering the connected SSID and Windows profile is read-only and may be
automatic. Retrieving saved `Key Content` with `netsh wlan show profile
name="<profile>" key=clear` is credential access and is permitted only after the
local operator explicitly authorizes the Wi-Fi provisioning workflow. The
credential must never be displayed, copied to logs or reports, uploaded to
Drive, retained by BoxBrain, or placed in process arguments. It may exist only
transiently in memory and in the verified USB-C SSH standard-input stream, and
the helper clears its transient variables after delivery.

The ordinary `boxbrain-link` diagnostic account remains non-administrator. Its
Windows health check attempts a bounded, redacted access-control audit and
records only whether the current saved Wi-Fi key was visible. A visible key is
reported as a high-severity boundary failure; the key itself is never returned
to the Pi.

## Source and validation

The deployable agent is in `edge/kali-pi-agent`. It uses Python's standard
library and retains its existing service names and `boxbrainctl controller`
alias so an upgrade does not strand the current Pi deployment. New scripts and
documentation use `boxbrainctl agent`.

Run the agent tests directly:

```powershell
$env:PYTHONPATH = "edge/kali-pi-agent/src"
python -m unittest discover -s edge/kali-pi-agent/tests -v
```

The repository validator runs these tests together with the FastAPI and Flutter
checks.

## Upgrade the Pi

Copy only the checked-in `edge/kali-pi-agent` directory to a temporary directory
on the Pi, inspect the diff, then run:

```bash
sudo sh ./scripts/upgrade.sh
boxbrainctl health
boxbrainctl agent
```

The guarded upgrader stops the agent briefly, writes a consistent state archive
under `/var/backups/boxbrain` with directory mode 700 and archive mode 600,
verifies the archive, and restores the prior installation automatically if any
install, service, API, or onboarding health check fails. Use `install.sh` only
for the first installation.

The installer preserves `/var/lib/boxbrain`, the target identity, linked-target
records, reports, and custom environment values. Do not copy workstation keys,
credential exports, database files, or other runtime state into the repository
or deployment bundle.
