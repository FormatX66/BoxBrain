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

The optional operator-started Pi screen uses a separate loopback VNC/WebSocket
SSH tunnel and is not part of the controller API or target executor. Its
canonical setup and security boundary are documented under
[Optional live Pi screen](../edge/kali-pi-agent/README.md#optional-live-pi-screen).

## USB onboarding boundary

The onboarding service listens only on the dedicated USB gadget address
`10.12.194.1:8788`. Version 0.6 migrates the old `0.0.0.0` default to that
address while preserving any other operator-selected bind address.

Onboarding still requires an explicit target-side `AUTHORIZE` confirmation and
creates a restricted, key-only diagnostic account. It does not emulate input,
install an administrator channel, or copy a private key to the target.

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
