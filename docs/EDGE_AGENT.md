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
sudo sh ./scripts/install.sh
boxbrainctl health
boxbrainctl agent
```

The installer preserves `/var/lib/boxbrain`, the target identity, linked-target
records, reports, and custom environment values. Do not copy workstation keys,
credential exports, database files, or other runtime state into the repository
or deployment bundle.
