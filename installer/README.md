# Local development helpers

These PowerShell helpers make the authenticated loopback setup repeatable. They
do not install packages, modify PATH, add services, change firewall rules, trust
certificates, or expose BoxBrain to another host.

From the repository root:

```powershell
# Inspect prerequisites without changing the machine.
powershell -ExecutionPolicy Bypass -File .\installer\check-prerequisites.ps1

# Create an ignored random token without printing its value.
powershell -ExecutionPolicy Bypass -File .\installer\initialize-local-auth.ps1

# Build the web dashboard with that token.
powershell -ExecutionPolicy Bypass -File .\installer\build-dashboard.ps1

# Start the authenticated controller in the current terminal.
powershell -ExecutionPolicy Bypass -File .\installer\start-controller.ps1

# Check authentication, read-only targeting, safety state, and dashboard health.
powershell -ExecutionPolicy Bypass -File .\installer\check-local-security.ps1
```

Use `initialize-local-auth.ps1 -Rotate` only when intentionally invalidating the
old local dashboard build; rebuild the dashboard immediately afterward.

TLS certificate creation and trust-store changes remain deliberately manual and
pending. They affect machine-wide browser trust and should not happen in an
unattended development session.