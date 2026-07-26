# BoxBrain Kali Pi Edge Agent

This directory contains the Kali Pi edge agent for the main BoxBrain controller.
It performs authorized, read-only observation and assessment close to connected
targets, then exposes a deliberately small status surface through a local SSH
tunnel. Version 0.6 provides the edge-agent foundation:

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
- presents USB Ethernet through the Pi 4 USB-C port;
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

## Edge-agent model

BoxBrain follows a simple loop:

```text
Observe -> Understand -> Recommend -> Optimize -> Act with policy
```

Observation is automatic only after a target has been explicitly authorized.
Recommendations are advisory. Any future setting, software, storage, repair, or
optimization change must travel through a separate approved-action path and be
logged. The current 0.6 edge agent does not perform those changes automatically.

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

## On-Pi commands

```bash
boxbrainctl health
boxbrainctl status
boxbrainctl jobs
boxbrainctl report latest
boxbrainctl targets
boxbrainctl agent
# boxbrainctl controller remains a compatibility alias
boxbrainctl diagnose 10.12.194.4 --authorized
boxbrainctl target-report 10.12.194.4
boxbrainctl assess 192.168.137.0/24 --profile discovery --authorized --wait
sudo systemctl status boxbrain
sudo journalctl -u boxbrain
```

## Development

The service uses only Python's standard library. Run its tests with:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Install or update it on the Pi from the project directory:

```bash
sudo sh ./scripts/install.sh
```
