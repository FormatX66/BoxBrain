# Local development helpers

These PowerShell helpers make the authenticated loopback setup repeatable. They
do not install packages, modify PATH, add services, change firewall rules, or
expose BoxBrain to another host. The TLS setup changes certificate trust only
for the current Windows user and records exact thumbprints for removal.

From the repository root:

```powershell
# Inspect prerequisites without changing the machine.
powershell -ExecutionPolicy Bypass -File .\installer\check-prerequisites.ps1

# Create an ignored random token without printing its value.
powershell -ExecutionPolicy Bypass -File .\installer\initialize-local-auth.ps1

# Create and trust the Current User-only local development certificate.
powershell -ExecutionPolicy Bypass -File .\installer\setup-local-tls.ps1

# Build the web dashboard with that token and HTTPS controller URL.
powershell -ExecutionPolicy Bypass -File .\installer\build-dashboard.ps1

# Start these HTTPS services in separate terminals.
powershell -ExecutionPolicy Bypass -File .\installer\start-controller.ps1
powershell -ExecutionPolicy Bypass -File .\installer\serve-dashboard.ps1

# Check certificate trust, authentication, targeting, safety, and dashboard health.
powershell -ExecutionPolicy Bypass -File .\installer\check-local-security.ps1
```

Open `https://127.0.0.1:8080/`. The setup script is idempotent and refuses to
replace certificates that are not tracked by its ignored metadata.

Use `initialize-local-auth.ps1 -Rotate` only when intentionally invalidating the
old local dashboard build; rebuild the dashboard immediately afterward.

## Remove local HTTPS trust

Stop the controller and dashboard first. Preview the exact rollback:

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\remove-local-tls.ps1 -ConfirmRemoval -WhatIf
```

Then remove only the certificate thumbprints recorded by BoxBrain and the
verified ignored TLS directory:

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\remove-local-tls.ps1 -ConfirmRemoval
```

The root CA private key is non-exportable. The server key is development-only,
ACL-restricted, and excluded from Git.

## Optional Raspberry Pi screen

The Pi screen is a separate, opt-in feature. It is not installed by the normal
edge-agent installer, never starts at boot, and does not change Windows firewall
rules. From the repository root, provision the checked scripts and verified
viewer package over the existing key-only SSH connection:

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\setup-pi-console.ps1
```

The setup command pins noVNC 1.7.0 by SHA-256, preserves its MPL-2.0 license,
and refuses missing Pi dependencies instead of installing packages. It also
creates **BoxBrain Pi Screen** on the desktop when that name is available.

Open the console without a shortcut:

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\open-pi-console.ps1
```

The launcher requires the trusted Pi host key and dedicated SSH identity. VNC
and WebSocket ports stay on Pi loopback; the browser reaches the WebSocket only
through a Windows-loopback SSH tunnel. See
[`edge/kali-pi-agent/README.md`](../edge/kali-pi-agent/README.md#optional-live-pi-screen)
for the transport boundary, prerequisites, stop command, and removal notes.
