# Installer placeholder

The installer is intentionally limited to prerequisite inspection in this
scaffold. It does not modify PATH, install packages, create services, change
firewall rules, or write a bootable image.

Run the Windows check from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\check-prerequisites.ps1
```

Future packaging targets:

- Windows development workstation
- Debian/Raspberry Pi OS controller service
- Bootable USB development image with persistent workspace

Image creation comes after the controller, authentication, audit store, and one
observation-only transport are proven on a normal operating system.

