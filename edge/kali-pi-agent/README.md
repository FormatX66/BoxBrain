# BoxBrain Kali Pi Edge Agent

This directory contains the Kali Pi edge agent for the main BoxBrain controller.
It performs authorized, read-only observation and assessment close to connected
targets, then exposes a deliberately small status surface through a local SSH
tunnel. Version 0.13 adds a read-only connection map for USB, Ethernet, Wi-Fi,
Bluetooth, and near-field adapters while retaining the guarded USB HID profile
and optional Pi console:

- runs as a dedicated, unprivileged Linux service account;
- exposes a local dashboard for health, recommendations, capabilities, and policy;
- separates every supported transport and its observed capabilities in a
  connection map;
- listens only on `127.0.0.1`, so it is reached through the secured SSH channel;
- reports hardware, memory, storage, temperature, network, and service uptime;
- treats authorized computers as managed systems with comparable health baselines;
- turns findings into prioritized optimization, repair, operations, and security
  recommendations;
- separates automatic observation, automatic recommendations, and
  operator-approved execution;
- keeps destructive edge-agent actions disabled;
- exposes an AI-reasoning capability boundary without pretending that an AI
  provider is configured;
- stores assessment history, assets, open services, and findings in SQLite;
- generates JSON and standalone HTML evidence reports;
- supports discovery and light baseline profiles through a local Unix socket;
- restricts targets to directly connected private/link-local IPv4 scopes of no
  more than 1,024 addresses;
- requires `--authorized` for every active assessment;
- keeps application state in `/var/lib/boxbrain`;
- does not run exploits, vulnerability scripts, stealth scans, or public-target scans.
- presents USB Ethernet through the Pi 4 USB-C port and discovers authorized USB targets automatically;
- enrolls explicitly authorized RFC1918/link-local targets over key-only SSH on Wi-Fi or Ethernet;
- rechecks registered USB-C and network targets and records connected/offline link state;
- serves read-only Windows and Linux onboarding scripts on port 8788;
- requires the target operator to type `AUTHORIZE` before making changes during
  normal interactive onboarding;
- creates a non-administrator/non-sudo `boxbrain-link` account on the target;
- keeps the target-access private key on the Pi and uses public-key-only SSH;
- provides an optional, disabled-until-configured USB-HID fallback for an
  explicitly authorized headless Windows console;
- never types a password, Wi-Fi key, arbitrary command, or operator-provided
  text, and accepts success only after key-only SSH verification;
- automatically performs a read-only health check after an authorized target
  connects;
- supports Windows and Linux targets through the restricted SSH link;
- records operating-system, memory, storage, network, device-error, and
  restart-pending information when available;
- translates raw health data into plain-language optimization and repair priorities;
- generates JSON and standalone HTML target diagnostic reports;
- does not change target settings, remove files, install drivers, or perform
  repairs.
- can provision the Pi from the current Windows Wi-Fi profile through a
  separately authorized administrator helper over USB-C SSH standard input;
- may discover the connected SSID automatically, but retrieves saved Windows
  `Key Content` only after explicit local provisioning authorization;
- never places a Wi-Fi passphrase in command arguments, reports, or logs;
- checks whether the restricted `boxbrain-link` account can improperly retrieve
  saved key content and reports only the result, never the credential.
- can use an operator-enrolled, reboot-persistent Google Drive transport to
  upload service health snapshots and diagnostic reports;
- downloads patches into a checksum-gated local staging area, but never
  executes them automatically;
- requires explicit authorization and the exact `DELIVER PATCH` confirmation
  before SFTP copies a verified patch into a connected target's restricted
  account.

## Recovery access point

The optional recovery AP preserves the existing `wlan0` client connection and
adds `bbap0` on the same channel at `10.42.194.1/24`. It uses WPA2/CCMP, serves
DHCP to AP clients, and blocks forwarding from AP clients into every other Pi
interface. Installation does not enable it.

```bash
sudo boxbrainctl access-point preview
sudo boxbrainctl access-point stage \
  --authorized \
  --confirmation 'STAGE ACCESS POINT'
sudo boxbrainctl access-point commit \
  --authorized \
  --confirmation 'COMMIT ACCESS POINT'
```

Staging generates a device-specific SSID and root-only key, starts the AP, and
arms a 15-minute rollback. Verify the advertised SSID and a client connection
before committing. Roll back with the exact `ROLL BACK ACCESS POINT`
confirmation if verification fails. The AP is a management fallback; target
enrollment and every repair capability keep their existing authorization gates.

## Connect a target by USB

The Pi 4 must use its onboard USB-C port for USB gadget mode. Its USB-A ports
are host-only and cannot act as a USB device to another computer.

After connecting the Pi USB-C port to the target computer with a data-capable
cable, open:

```text
http://10.12.194.1:8788
```

Download the Windows or Linux link script, inspect it, run it with
administrator/root rights, and type `AUTHORIZE` when prompted. BoxBrain then
detects the target over its dedicated SSH key and shows it under Authorized
target links on the dashboard.

Once the target link is confirmed, BoxBrain automatically collects a read-only
health baseline. The dashboard shows system status, lowest free disk percentage,
available memory, findings, edge-agent recommendations, and the capability
registry. Diagnostics refresh no more than once every 15 minutes by default.

To provision the Pi from the Windows computer's currently connected Wi-Fi,
download `windows-wifi-provision.ps1` from the same onboarding page and run it
from Administrator PowerShell. Type `PROVISION WIFI` when prompted. The helper
is restricted to the dedicated Pi address `10.12.194.1`, requires an already
trusted Pi SSH host key, and streams the credential through SSH standard input.
It does not write the credential to a file or display it.

## Headless Windows keystroke fallback

Version 0.12 adds a narrow bootstrap for a physically attached Windows machine
that has no screen or keyboard available but still has an unlocked interactive
administrator console. This does not replace Windows Headless Rescue over
WinRM/JEA. A truly sessionless machine must use WinRM, SSH, BMC/iDRAC/iLO, a VM
console, or a preinstalled agent; this fixed USB sequence cannot log in or
create a desktop session.

The installer places the composite-gadget helper and systemd units on the Pi,
but does not enable them. The current legacy `g_ether` USB networking stays in
place until an operator stages the Windows-focused RNDIS plus
keyboard-and-mouse profile.
Staging requires a working non-USB management interface and an exact local
confirmation, changes only the next-boot configuration, and arms a 15-minute
rollback timer. It does not reboot the Pi.

```bash
sudo boxbrainctl usb-hid preview
sudo boxbrainctl usb-hid stage \
  --authorized \
  --confirmation 'STAGE USB HID' \
  --alternate-interface wlan0
```

During an approved maintenance window, reboot separately. After reconnecting
over the alternate interface, confirm that `usb0`, `/dev/hidg0`, and
`/dev/hidg1` exist. Commit before the timer expires only after USB Ethernet,
keyboard, and mouse enumeration have been verified:

```bash
sudo boxbrainctl usb-hid preview
sudo boxbrainctl usb-hid commit \
  --authorized \
  --confirmation 'COMMIT USB HID'
```

If verification fails, either allow the pending migration to restore legacy
`g_ether` automatically or roll it back explicitly:

```bash
sudo boxbrainctl usb-hid rollback \
  --authorized \
  --confirmation 'ROLL BACK USB HID'
```

The command defaults to a no-change preview:

```bash
sudo boxbrainctl headless-windows-link
```

Execution is available only after `/dev/hidg0` has been deliberately configured
as part of the Pi's USB gadget, the target uses a US keyboard layout, and the
operator authorizes that exact physical computer. It types a fixed PowerShell
bootstrap, downloads `windows-link.ps1` only from `10.12.194.1:8788`, checks the
installed helper's SHA-256 before execution, and supplies the helper's existing
authorization assertion. It never types credentials or arbitrary text.
Version 0.14.1 retries only the current eight-byte HID report for up to one
second when Linux reports that the configured endpoint is transiently busy; it
never restarts the command sequence or retries an unverified enrollment.

```bash
sudo boxbrainctl headless-windows-link \
  --execute \
  --authorized \
  --confirmation 'CONNECT HEADLESS WINDOWS'
```

The tool first refuses to type if the target is already linked, then waits for
the new `boxbrain-link` key-only SSH proof. If it cannot verify that proof, it
reports the run as unverified and refuses to retry blindly. UAC policies that
require credential entry are intentionally not supported. Installation alone
never creates `/dev/hidg0` or `/dev/hidg1`, changes the active gadget, or
reboots the Pi.

The USB cable now exposes descriptors for both keyboard and mouse emulation.
This does not automatically enable Bluetooth HID: Bluetooth uses a separate
radio, pairing process, and trust relationship. BoxBrain will not advertise or
accept a Bluetooth keyboard/mouse pairing merely because a USB cable was
inserted; that path requires its own bounded pairing authorization before
deployment.

The composite layout follows the kernel's
[ConfigFS gadget](https://docs.kernel.org/usb/gadget_configfs.html) and
[HID gadget](https://docs.kernel.org/usb/gadget_hid.html) interfaces. Its
`usb0` behavior is aligned with Raspberry Pi's maintained
[USB gadget tooling](https://github.com/raspberrypi/rpi-usb-gadget). The first
live migration and disposable-target proof remain maintenance-window actions.

### Kali desktop headless shortcut

After a Windows target is enrolled, host-key verified, and shown as connected,
install the optional Kali desktop shortcut explicitly:

```bash
sudo sh ./scripts/install-desktop-shortcut.sh kali
```

**BoxBrain Headless Windows** selects exactly one connected `usb0`
`boxbrain-link` target from the registry and opens non-administrator
PowerShell-over-SSH in a terminal. It uses the existing private identity and
pinned trust store, refuses ambiguous or offline targets, and never performs
HID enrollment, accepts a new host key, or changes the target.

## Continue a target over Wi-Fi or Ethernet

Use this only for a target you own or are explicitly authorized to manage. The
target must already have run one of the BoxBrain link scripts, and the Pi and
target must share a private or link-local IPv4 network.

Allow the Pi's exact private-network address through the target firewall by
rerunning the link script. Keep `10.12.194.1` in the list if USB-C will also be
used. Examples, where `192.168.50.10` is the Pi address:

```powershell
PowerShell -ExecutionPolicy Bypass -File $env:TEMP\boxbrain-link.ps1 `
  -BoxBrainAddress '10.12.194.1','192.168.50.10'
```

```bash
sudo env BOXBRAIN_AGENT_ADDRESS=10.12.194.1,192.168.50.10 sh /tmp/boxbrain-link.sh
```

Then run this on the Pi, using the target's private address:

```bash
boxbrainctl add-target 192.168.50.23 --authorized
boxbrainctl targets
```

BoxBrain verifies the Pi route, refuses public addresses and manual USB
enrollment, requires its dedicated key-only SSH identity, and saves the target
only after SSH verification succeeds. No password or private key is copied to
the target or controller.

## Edge-agent model

BoxBrain follows a simple loop:

```text
Observe -> Understand -> Recommend -> Optimize -> Act with policy
```

Observation is automatic only after a target has been explicitly authorized.
Recommendations are advisory. Any future setting, software, storage, repair, or
optimization change must travel through a separate approved-action path and be
logged. The current 0.7 edge agent does not perform those changes automatically.

## Connect to the dashboard

From Windows, start an SSH tunnel:

```powershell
ssh -i "$HOME\.ssh\boxbrain_pi_ed25519" -L 8787:127.0.0.1:8787 kali@kali-raspberrypi.mshome.net
```

Keep that window open, then visit `http://127.0.0.1:8787` in a browser.

SSH password login is disabled. Use the dedicated private key provisioned for
your workstation. Private keys, recovery credentials, and live Pi state are
runtime-only and must never be committed to this repository.

The main BoxBrain controller reads agent status through this same tunnel. Its
default endpoint is `http://127.0.0.1:8787`; override
`BOXBRAIN_KALI_PI_AGENT_URL` only with another loopback address.

## Optional live Pi screen

This console is for viewing and operating the Pi itself. It is separate from
target diagnostics and does not grant BoxBrain control of an enrolled target.
The normal `install.sh` and `upgrade.sh` paths do not install, start, or enable
it.

From the BoxBrain repository root on the authorized Windows workstation:

```powershell
.\installer\setup-pi-console.ps1
.\installer\open-pi-console.ps1
```

The first command copies only three console scripts through key-only SSH,
downloads the official noVNC 1.7.0 tag archive over HTTPS on the Pi, verifies
its pinned SHA-256 before extraction, and preserves the bundled MPL-2.0 license.
It does not install missing packages. The Pi must already provide TightVNC,
websockify, XFCE, D-Bus, Python 3, curl, and standard systemd/network tools.

The second command starts four transient services for the current session and
opens the viewer. TightVNC listens on `127.0.0.1:5901`, websockify listens on
`127.0.0.1:6080`, and the browser reaches both the viewer page and WebSocket
through SSH forwards bound to Windows loopback. The Pi's private HTTP endpoint
serves static noVNC files; it does not carry the desktop stream without the
SSH tunnel. No VNC password is used because the VNC and WebSocket listeners are
not reachable off Pi loopback.

An optional current-user Windows watcher can open this console once whenever
the preferred reachable Pi path changes from offline to online:

```powershell
.\installer\install-pi-console-auto-open.ps1 -StartNow
```

It prefers USB Ethernet, then the known LAN address, then the isolated recovery
AP. A named mutex prevents duplicate watcher processes, and an unchanged link
does not create repeated browser tabs. The watcher does not discover arbitrary
hosts, change networking, install a service, or weaken SSH host-key checking.
Remove only its logon shortcut with
`install-pi-console-auto-open.ps1 -Remove`.

Stop only these transient console services:

```powershell
ssh -i "$HOME\.ssh\boxbrain_pi_ed25519" kali@10.12.194.1 `
  "sudo -n /usr/local/bin/boxbrain-console-stop"
```

To change the dedicated USB bind or static viewer port, edit the root-owned
`/etc/boxbrain/console.env` on the Pi. The start script accepts only a private
or link-local assigned address. Removing the feature is a separate manual
operation so setup never deletes an existing verified package unexpectedly.
After stopping it, the only feature-owned Pi paths to review for removal are
`/opt/boxbrain/pi-console`, `/etc/boxbrain/console.env`,
`/usr/local/bin/boxbrain-console-start`, and
`/usr/local/bin/boxbrain-console-stop`.

## On-Pi commands

```bash
boxbrainctl health
boxbrainctl status
boxbrainctl jobs
boxbrainctl report latest
boxbrainctl targets
boxbrainctl add-target 192.168.50.23 --authorized
boxbrainctl agent
# boxbrainctl controller remains a compatibility alias
boxbrainctl diagnose 10.12.194.4 --authorized
boxbrainctl target-report 10.12.194.4
boxbrainctl patches
boxbrainctl deliver-patch <verified-reference> --authorized --confirmation "DELIVER PATCH"
boxbrainctl assess 192.168.137.0/24 --profile discovery --authorized --wait
sudo systemctl status boxbrain
sudo journalctl -u boxbrain
```

## Connect Google Drive

The optional Drive transport remains disabled until its one-time OAuth
enrollment succeeds. It uses a root-folder-restricted rclone remote, creates the
canonical BoxBrain folder layout without deleting existing content, uploads
telemetry and diagnostics every five minutes, and stages verified patch
packages. See the canonical [Drive transport runbook](../../docs/DRIVE_TRANSPORT.md).

Rclone is a separately installed upstream dependency. The BoxBrain installer
does not download it, and the Drive token is runtime-only.

## Development

The service uses only Python's standard library. Run its tests with:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Install it for the first time from the project directory:

```bash
sudo sh ./scripts/install.sh
```

For later upgrades, use the guarded upgrade path. It stops BoxBrain briefly for
a consistent state backup, creates the rollback archive with root-only
permissions, restores automatically if install or health verification fails, and
prints the retained archive path:

```bash
sudo sh ./scripts/upgrade.sh
```
