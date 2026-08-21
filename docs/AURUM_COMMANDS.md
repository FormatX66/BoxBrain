# Aurum Command Registry

This file is the canonical list of Aurum / BoxBrain commands that are actually implemented or explicitly documented.

## Rule

A command is not real merely because it sounds reasonable or was suggested in chat. It must have repository evidence showing where it is implemented or documented.

States:
1. **Proposed** — vocabulary only; do not tell a user to run it.
2. **Implemented** — executable handling exists in code.
3. **Tested** — automated or bounded functional proof exists.
4. **Physical** — successfully exercised on an authorized physical Aurum node such as Hopper.

## Hopper Aurum console

Implementation: `Projects/AurumPC/aurum_console.py` on `aurum/trunk-v0.01`.

| Command | State | Purpose / boundary |
|---|---:|---|
| `status` | Physical | Overall Aurum node status. |
| `hardware` | Physical | Read-only hardware inventory. |
| `network-status` | Physical | Read-only network status. |
| `wifi-setup` | Implemented | Interactive Wi-Fi setup. |
| `wifi-reconnect` | Implemented | Reconnect using existing configuration. |
| `input-status` | Implemented | Read-only pointer/touchpad discovery, libinput/module state, and power-policy observation. |
| `input-recover` | Implemented | Applies the bounded pointer wake policy already defined by `aurum_input.py`; no broad driver replacement. |
| `field` | Physical | Show current reusable native/local capability field. |
| `selftest` | Physical | Run bounded Aurum self-test. |
| `seed` | Physical | Seed local Aurum state. |
| `seed-status` | Physical | Read seed status. |
| `self-build` | Physical | Start bounded background self-build. |
| `self-build-status` | Physical | Read self-build progress. |
| `self-build-cancel` | Implemented | Request bounded cancellation while preserving checkpoint state. |
| `git-status` | Physical | Read Hopper's bounded Aurum workspace state. |
| `git-sync authorize-network` | Physical | Fetch and fast-forward only from the configured BoxBrain branch; refuses dirty/local divergent state. |
| `git-auth` | Implemented | Cache a GitHub token in memory for one hour; no token persistence. |
| `git-promote authorize-network confirm-push` | Implemented | Promote only allowlisted verified self-build outputs. |
| `runtime-status` | Physical | Compare workspace runtime payload with installed Aurum runtime. |
| `runtime-sync` | Physical | Apply the bounded allowlisted runtime update. |
| `autonomy-status` | Physical | Read autonomy state. |
| `autonomy-cycle` | Physical | Run one bounded autonomy cycle. |
| `driver-status` | Physical | Read adaptive driver-synthesis status. |
| `driver-cycle` | Physical | Run one shadow driver-synthesis cycle; `physical_swap=false`. |
| `gui-status` | Physical | Read GUI, arcade, and physical desktop runtime state. |
| `gui-start` | Physical | Start Aurum GUI/desktop presentation. |
| `gui-stop` | Physical | Stop Aurum GUI/desktop presentation. |
| `install` | Implemented | Show bounded install plan. |
| `install confirm ERASE-CODE` | Implemented | Confirm an explicitly selected destructive install target. |
| `reboot` | Physical | Explicit Aurum reboot command. |
| `poweroff` | Implemented | Explicit Aurum poweroff command. |
| `help` / `?` | Physical | Print the real command surface. |

### Input commands

`input-status` and `input-recover` were added on 2026-08-21 in commit `0938a229631394f3d06382e1a935161ac83df345` on `aurum/trunk-v0.01`.

They use `Projects/AurumPC/aurum_input.py`, which detects touchpads/pointers, reports `libinput`, checks `i2c_hid_acpi`, `hid_multitouch`, `psmouse`, and `usbhid`, and can apply a bounded wake policy to managed pointer devices.

They remain **Implemented** until physically exercised on Hopper.

## BoxBrain confirmation phrases

| Command | Scope | State |
|---|---|---:|
| `RUN` | Approval-gated fixed read-only diagnostics | Documented |
| `RESET` | Dashboard emergency-stop reset | Documented |
| `OPEN` | Operator-controlled target session launch | Documented |

## Assistant behavior

Before suggesting an Aurum command:
1. Read this registry or the live `help` output.
2. Use only commands whose documented scope matches the requested action.
3. Do not invent Aurum commands.
4. Do not substitute Linux/Windows administration when an Aurum-native command exists.
5. If no command exists, identify the missing capability as an implementation gap.

Last updated: 2026-08-21.
