# BoxBrain Kali Pi Edge Agent

This directory contains the Kali Pi edge agent for the main BoxBrain controller.
It performs authorized, read-only observation and assessment close to connected
targets, then exposes a deliberately small status surface through a local SSH
tunnel. Version 0.9 retains guarded Wi-Fi provisioning and adds an optional,
human-operated Pi console:

- runs as a dedicated, unprivileged Linux service account;
- exposes a local dashboard for health, recommendations, capabilities, and policy;
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
- requires the target operator to type `AUTHORIZE` before making changes;
- creates a non-administrator/non-sudo `boxbrain-link` account on the target;
- keeps the target-access private key on the Pi and uses public-key-only SSH;
- does not emulate a keyboard or inject commands into an unapproved computer.
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
`127.0.0.1:6080`, and the browser connects to that WebSocket through an SSH
forward bound to Windows loopback. The USB-only HTTP endpoint at
`10.12.194.1:8790` serves static noVNC files; it does not carry the desktop
stream without the SSH tunnel. No VNC password is used because the VNC and
WebSocket listeners are not reachable off Pi loopback.

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
