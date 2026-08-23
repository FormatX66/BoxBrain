#!/usr/bin/env python3
"""Aurum Tiny Seed setup surface.

This is intentionally not a desktop. It is a small full-screen-ish setup flow:
1) network (skipped when already online), 2) choose existing Aurum or a target
disk, 3) confirm and let the germ bridge/install/regrow automatically.
"""
from __future__ import annotations

import getpass
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import bridge
import installer
import network
import platform as py_platform


def _clear() -> None:
    print("\033[2J\033[H", end="", flush=True)


def _title(step: str, subtitle: str) -> None:
    _clear()
    print("╭──────────────────────────────────────────────────────────────╮")
    print("│                         A U R U M                            │")
    print("│                         TINY SEED                            │")
    print("╰──────────────────────────────────────────────────────────────╯")
    print(f"\n{step}\n{subtitle}\n")


def _detect() -> dict[str, Any]:
    machine = py_platform.machine().lower()
    architecture = "x86_64" if machine in {"x86_64", "amd64"} else "arm64" if machine in {"aarch64", "arm64"} else machine
    model = None
    for path in (Path("/sys/firmware/devicetree/base/model"), Path("/sys/class/dmi/id/product_name")):
        try:
            model = path.read_text(encoding="utf-8", errors="replace").replace("\x00", "").strip()
        except OSError:
            continue
        if model:
            break
    return {"architecture": architecture, "model": model}


def _network_step() -> bool:
    _title("1 · NETWORK", "Aurum uses the network only to fetch trusted genetics.")
    try:
        current = network.status()
    except network.NetworkError as exc:
        print(f"Network service is unavailable: {exc}")
        return False
    if current.get("online"):
        print("✓ Network already connected. Nothing to do.")
        return True

    try:
        choices = network.wifi_scan()
    except network.NetworkError as exc:
        print(f"No automatic network path: {exc}")
        return False
    if not choices:
        print("No Wi-Fi networks found. Ethernet may still come up automatically.")
        return False

    print("Choose Wi-Fi:\n")
    for index, item in enumerate(choices[:12], start=1):
        lock = "🔒" if item["security"] != "open" else "  "
        print(f"  {index:>2}. {lock} {item['ssid'][:36]:<36} {item['signal']:>3}%")
    print("   0. Continue offline")
    raw = input("\nWi-Fi number: ").strip()
    try:
        selected = int(raw)
    except ValueError:
        return False
    if selected == 0:
        return False
    if selected < 1 or selected > min(12, len(choices)):
        return False
    item = choices[selected - 1]
    password = None
    if item["security"] != "open":
        password = getpass.getpass(f"Password for {item['ssid']}: ")
    try:
        result = network.wifi_connect(str(item["ssid"]), password)
    finally:
        password = None
    print(f"✓ {result.get('status')} — {item['ssid']}")
    return network.online()


def _run(args: list[str], *, check: bool = True, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=timeout,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stdout.strip()[-1200:] or "command failed")
    return result


def _installed_roots() -> list[dict[str, Any]]:
    result = _run(
        ["lsblk", "--json", "--paths", "--output", "PATH,TYPE,FSTYPE,SIZE,MODEL,MOUNTPOINTS"],
        timeout=20,
    )
    devices = json.loads(result.stdout).get("blockdevices") or []
    partitions: list[dict[str, Any]] = []

    def walk(records: list[dict[str, Any]]) -> None:
        for record in records:
            if record.get("type") == "part" and str(record.get("fstype") or "") in {"ext4", "xfs", "btrfs"}:
                partitions.append(record)
            children = record.get("children") or []
            if isinstance(children, list):
                walk([x for x in children if isinstance(x, dict)])

    walk([x for x in devices if isinstance(x, dict)])
    found: list[dict[str, Any]] = []
    for record in partitions:
        device = str(record.get("path") or "")
        if not device:
            continue
        with tempfile.TemporaryDirectory(prefix="aurum-probe-") as td:
            mount = Path(td) / "root"
            mount.mkdir()
            mounted = _run(["mount", "-o", "ro", device, str(mount)], check=False, timeout=20)
            if mounted.returncode != 0:
                continue
            try:
                legacy = (mount / "etc/aurum-installed.json").is_file()
                tiny = (mount / "etc/aurum-tinyseed-installed.json").is_file()
                slots = (mount / "var/lib/aurum/germ/slots.json").is_file()
                if legacy or tiny:
                    found.append(
                        {
                            "device": device,
                            "size": record.get("size"),
                            "model": record.get("model"),
                            "legacy": legacy,
                            "germ": slots,
                        }
                    )
            finally:
                _run(["umount", str(mount)], check=False, timeout=20)
    return found


def _chroot_regrow(root: Path) -> dict[str, Any]:
    mounted: list[Path] = []
    try:
        for source, rel in (("/dev", "dev"), ("/run", "run")):
            target = root / rel
            target.mkdir(parents=True, exist_ok=True)
            _run(["mount", "--bind", source, str(target)], timeout=20)
            mounted.append(target)
        for fs, rel in (("proc", "proc"), ("sysfs", "sys")):
            target = root / rel
            target.mkdir(parents=True, exist_ok=True)
            _run(["mount", "-t", fs, fs, str(target)], timeout=20)
            mounted.append(target)
        result = _run(
            [
                "chroot", str(root), "/usr/bin/python3", "/usr/lib/aurum/germ/reseed.py",
                "regrow", "--ref", "main", "--authorize-network",
            ],
            timeout=1200,
        )
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"status": "finished", "detail": result.stdout.strip()[-2000:]}
    finally:
        for target in reversed(mounted):
            _run(["umount", "-l", str(target)], check=False, timeout=20)


def _repair_existing(entry: dict[str, Any], *, online: bool) -> dict[str, Any]:
    device = str(entry["device"])
    with tempfile.TemporaryDirectory(prefix="aurum-repair-") as td:
        root = Path(td) / "root"
        root.mkdir()
        _run(["mount", device, str(root)], timeout=20)
        try:
            bridged = bridge.install(root)
            regrow = _chroot_regrow(root) if online else {"status": "deferred-offline"}
            _run(["sync"], check=False)
            return {"status": "prepared", "device": device, "bridge": bridged, "regrow": regrow}
        finally:
            _run(["umount", str(root)], check=False, timeout=30)


def _choose(items: list[dict[str, Any]], label) -> int | None:
    for index, item in enumerate(items, start=1):
        print(f"  {index}. {label(item)}")
    raw = input("\nChoose: ").strip()
    try:
        number = int(raw)
    except ValueError:
        return None
    return number - 1 if 1 <= number <= len(items) else None


def main() -> int:
    if os.geteuid() != 0:
        print("Aurum Tiny Seed must run as root.")
        return 2
    detected = _detect()
    online = _network_step()

    _title("2 · MACHINE", f"Detected: {detected['architecture']} · {detected.get('model') or 'unknown model'}")
    existing = _installed_roots()
    action = "fresh"
    selected_existing: dict[str, Any] | None = None
    if existing:
        print("Aurum found on this machine:\n")
        index = _choose(
            existing,
            lambda item: f"Repair / reseed {item['device']}  {'germ-ready' if item['germ'] else 'legacy seed'}",
        )
        if index is not None:
            action = "repair"
            selected_existing = existing[index]
        else:
            print("No existing installation selected; switching to fresh install.")

    selected_target: dict[str, Any] | None = None
    if action == "fresh":
        plan = installer.plan()
        targets = plan.get("targets") or []
        if not targets:
            print("No safe install target is available. The boot medium remains usable for diagnostics/recovery.")
            return 1
        print("Install Aurum to:\n")
        if len(targets) == 1:
            selected_target = targets[0]
            print(f"  → {selected_target['device']} · {selected_target['size_gib']} GiB · {selected_target['model']}")
        else:
            index = _choose(
                targets,
                lambda item: f"{item['device']} · {item['size_gib']} GiB · {item['model']}" + (" · removable" if item['removable'] else ""),
            )
            if index is None:
                print("No target selected.")
                return 1
            selected_target = targets[index]

    if action == "repair" and selected_existing:
        summary = f"Repair/reseed {selected_existing['device']}"
        destructive = False
    else:
        assert selected_target is not None
        summary = f"Fresh install to {selected_target['device']} · {selected_target['size_gib']} GiB · {selected_target['model']}"
        destructive = True

    _title("3 · GO", summary)
    if destructive:
        print("WARNING: the selected target disk will be completely erased.\n")
    if online:
        print("Current trusted genetics will be fetched automatically.")
    else:
        print("Offline mode: Tiny Seed will install/repair the protected germ; current genetics can regrow later.")
    confirm = input("\nContinue? [y/N]: ").strip().lower()
    if confirm not in {"y", "yes"}:
        print("Cancelled. No change made.")
        return 1

    try:
        if action == "repair" and selected_existing:
            result = _repair_existing(selected_existing, online=online)
        else:
            assert selected_target is not None
            result = installer.install(
                selected_target["confirmation_code"],
                architecture=str(detected["architecture"]),
                model=detected.get("model"),
                regrow_current=online,
            )
    except (bridge.BridgeError, installer.InstallError, network.NetworkError, RuntimeError) as exc:
        _title("STOPPED SAFELY", "Tiny Seed refused to continue rather than guess.")
        print(str(exc))
        return 2

    _title("READY", "Aurum has a protected germ and a recovery path.")
    print(json.dumps(result, indent=2, sort_keys=True))
    regrow = result.get("regrow") if isinstance(result, dict) else None
    if isinstance(regrow, dict) and regrow.get("status") == "trial-armed":
        print("\n✓ Current genetics were grown into the inactive slot.")
        print("  Power off, remove Tiny Seed, and boot the machine. The guardian will promote or roll back automatically.")
    elif online:
        print("\nGenetics were staged as far as this platform currently allows. Keep Tiny Seed available as the recovery germ.")
    else:
        print("\nBoot is prepared. Connect networking later and choose reseed current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
