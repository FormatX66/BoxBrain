#!/usr/bin/env python3
"""Aurum Tiny Seed setup surface.

External-media mode is a small three-screen setup flow: network, machine, go.
Installed bootstrap mode is even smaller: if a grown phenotype is active it is
launched; otherwise networking is obtained and current genetics are regrown.
"""
from __future__ import annotations

import getpass
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import bridge
import installer
import machine
import network

INSTALLED_MARKER = Path("/etc/aurum-tinyseed-installed.json")
LIVE_MEDIUM = Path("/run/live/medium")
SLOT_STATE = Path("/var/lib/aurum/germ/slots.json")
OFFLINE_CARRIER = Path("/usr/lib/aurum/carrier")
CMDLINE = Path("/proc/cmdline")


def _boot_tokens() -> set[str]:
    override = os.environ.get("AURUM_TINYSEED_CMDLINE")
    try:
        raw = override if override is not None else CMDLINE.read_text(encoding="utf-8")
    except OSError:
        raw = ""
    return {token.strip() for token in raw.split() if token.strip()}


def _plain_ui() -> bool:
    tokens = _boot_tokens()
    return (
        "aurum.accessibility=blind" in tokens
        or "aurum.ui=plain" in tokens
        or os.environ.get("NO_COLOR") is not None
        or not sys.stdout.isatty()
    )


def _paint(code: str, value: str) -> str:
    return value if _plain_ui() else f"\033[{code}m{value}\033[0m"


def _clear() -> None:
    if _plain_ui():
        # Do not erase context or emit terminal controls in the spoken path.
        # Screen-reader users need the previous prompt to remain reviewable.
        print("\n")
    else:
        print("\033[2J\033[H", end="", flush=True)


def _title(step: str, subtitle: str) -> None:
    _clear()
    if _plain_ui():
        # Screen readers should receive words, not decorative box glyphs or
        # terminal color escapes.
        print("AURUM TINY SEED")
        print(f"{step}: {subtitle}\n")
        return
    cyan = "38;5;45"
    gold = "38;5;220"
    dim = "38;5;250"
    print(_paint(cyan, "        ◇"))
    print(_paint(cyan, "   A U R U M") + "  " + _paint(gold, "TINY SEED"))
    print(_paint(dim, "   ─────────────────────────────────────────"))
    print(f"   {_paint(gold, step)}")
    print(f"   {_paint(dim, subtitle)}\n")


def _announce_online() -> None:
    marker = (
        "AURUM_TINYSEED_NETWORK_READY resolver=true repository_tcp_443=true "
        "repository_https=true repository_sync=true"
    )
    print(marker, flush=True)
    try:
        with Path("/dev/ttyS0").open("w", encoding="utf-8") as serial:
            serial.write(marker + "\n")
    except OSError:
        pass


def _network_step() -> bool:
    repair_attempted = False
    while True:
        _title("1 · NETWORK", "Join Wi-Fi now so Aurum can regrow current trusted genetics.")
        try:
            current = network.status()
        except network.NetworkError as exc:
            if not repair_attempted:
                repair_attempted = True
                repaired = network.repair()
                if repaired["connectivity"]["online"]:
                    print("Network services repaired; the BoxBrain sync path is ready.")
                    _announce_online()
                    return True
            print(f"Network service is not ready: {exc}")
            if _retry_or_offline():
                continue
            return False
        if current.get("online"):
            print("Network, DNS, HTTPS, and the BoxBrain git sync path are ready.")
            _announce_online()
            return True

        if current.get("link_connected"):
            print(f"Connected link needs repair: {network.failure_reason(current)}")
            if not repair_attempted:
                repair_attempted = True
                repaired = network.repair()
                if repaired["connectivity"]["online"]:
                    print("Network services repaired; the BoxBrain sync path is ready.")
                    _announce_online()
                    return True

        try:
            choices = network.wifi_scan()
        except network.NetworkError as exc:
            print(f"Wi-Fi scan failed: {exc}")
            if _retry_or_offline():
                continue
            return False
        if not choices:
            print("No Wi-Fi networks found. Connect Ethernet or rescan.")
            if not repair_attempted:
                repair_attempted = True
                network.repair()
            if _retry_or_offline():
                continue
            return False

        print("Choose Wi-Fi:\n")
        for index, item in enumerate(choices[:12], start=1):
            # ASCII remains legible on firmware consoles and through speech;
            # color/decorative glyph support must never gate networking.
            lock = "*" if item["security"] != "open" else " "
            print(f"  {index:>2}. {lock} {item['ssid'][:36]:<36} {item['signal']:>3}%")
        print("   R. Rescan")
        print("   O. Continue offline")
        raw = input("\nWi-Fi number: ").strip().lower()
        if raw in {"r", "rescan", "retry"}:
            continue
        if raw in {"o", "offline"}:
            return False
        try:
            selected = int(raw)
        except ValueError:
            continue
        if selected < 1 or selected > min(12, len(choices)):
            continue
        item = choices[selected - 1]
        password = None
        if item["security"] != "open":
            password = getpass.getpass(f"Password for {item['ssid']}: ")
        try:
            result = network.wifi_connect(str(item["ssid"]), password)
        except network.NetworkError as exc:
            print(f"Wi-Fi did not connect: {exc}")
            input("\nPress Enter to rescan. ")
            continue
        finally:
            password = None
        if network.wait_online(timeout=45):
            print(f"Connected and sync-ready - {item['ssid']}")
            _announce_online()
            return True
        repaired = network.repair()
        if repaired["connectivity"]["online"]:
            print(f"Connected and repaired - {item['ssid']}")
            _announce_online()
            return True
        print(f"Wi-Fi associated, but sync is not ready: {repaired['reason']}")
        if _retry_or_offline():
            continue
        return False


def _retry_or_offline() -> bool:
    """Return True to retry; offline continuation must always be explicit."""
    while True:
        raw = input("\n[R] Rescan / retry   [O] Continue offline: ").strip().lower()
        if raw in {"r", "rescan", "retry", ""}:
            return True
        if raw in {"o", "offline"}:
            return False


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


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _exec_active_phenotype() -> int:
    runtime = Path("/opt/aurum")
    bootstrap = runtime / "aurum_bootstrap.py"
    console = runtime / "aurum_console.py"
    if bootstrap.is_file():
        os.execv("/usr/bin/python3", ["/usr/bin/python3", str(bootstrap)])
    if console.is_file():
        os.execv("/usr/bin/python3", ["/usr/bin/python3", str(console)])
    _title("RECOVERY", "The active phenotype is missing its launcher.")
    print("Tiny Seed has not modified another slot. Boot external Tiny Seed to repair/regrow.")
    return 2


def _installed_bootstrap_mode() -> int:
    """Finish a fresh offline install or launch the boot-selected phenotype."""
    state = _json(SLOT_STATE)
    trial = state.get("trial")
    active = state.get("active")
    # Preflight sets active=trial at the boot boundary. Once that happened, run
    # the candidate so the independent health service can judge the real boot.
    if trial and active == trial:
        return _exec_active_phenotype()

    # A previously promoted non-bootstrap phenotype should simply run.
    if state.get("last_result") == "candidate-promoted-healthy" or state.get("lkg") != "A":
        return _exec_active_phenotype()

    _title("FINISHING AURUM", "The protected germ is installed. Current genetics still need to grow.")
    online = _network_step()
    offline_carrier_ready = (OFFLINE_CARRIER / "carrier.json").is_file()
    if not online and not offline_carrier_ready:
        _title("OFFLINE", "The bootstrap stays healthy; nothing was overwritten.")
        print("Connect Ethernet or reboot and choose Wi-Fi to regrow current Aurum.")
        try:
            input("\nPress Enter to retry networking, or power off normally. ")
        except (EOFError, KeyboardInterrupt):
            return 1
        return _installed_bootstrap_mode()

    if online:
        _title("GROWING AURUM", "Sync verified. Building current trusted genetics in the inactive slot.")
        reseed_args = [
            "/usr/bin/python3", "/usr/lib/aurum/germ/reseed.py", "regrow",
            "--ref", "main", "--authorize-network",
        ]
    else:
        _title("GROWING OFFLINE", "Using the verified fallback image; the protected LKG stays active.")
        reseed_args = [
            "/usr/bin/python3", "/usr/lib/aurum/germ/reseed.py", "regrow",
            "--ref", "main", "--offline-carrier", str(OFFLINE_CARRIER),
        ]
    result = _run(reseed_args, timeout=1200)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {"status": "finished", "detail": result.stdout.strip()[-2000:]}
    if payload.get("status") == "trial-armed":
        _title("READY TO PROVE", "Current Aurum was grown beside the bootstrap LKG.")
        print("Rebooting into the candidate. The Guardian will promote it only if health checks pass.")
        subprocess.run(["/bin/systemctl", "reboot"], check=False)
        return 0

    _title("GERM READY", "Aurum stopped before replacing the bootstrap LKG.")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1


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


def _chroot_regrow(root: Path, *, offline: bool = False) -> dict[str, Any]:
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
        carrier_target: Path | None = None
        if offline:
            if not (OFFLINE_CARRIER / "carrier.json").is_file():
                raise RuntimeError("verified offline phenotype carrier is unavailable")
            carrier_target = root / "run/aurum-offline-carrier"
            carrier_target.mkdir(parents=True, exist_ok=True)
            _run(["mount", "--bind", str(OFFLINE_CARRIER), str(carrier_target)], timeout=20)
            mounted.append(carrier_target)
            _run(["mount", "-o", "remount,bind,ro", str(carrier_target)], timeout=20)
        reseed_arguments = [
            "chroot", str(root), "/usr/bin/python3", "/usr/lib/aurum/germ/reseed.py",
            "regrow", "--ref", "main",
        ]
        if offline:
            reseed_arguments.extend(["--offline-carrier", "/run/aurum-offline-carrier"])
        else:
            reseed_arguments.append("--authorize-network")
        result = _run(
            reseed_arguments,
            timeout=1200,
        )
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"status": "finished", "detail": result.stdout.strip()[-2000:]}
    finally:
        for target in reversed(mounted):
            _run(["umount", "-l", str(target)], check=False, timeout=20)


def _regrow_installed_root(device: str, *, offline: bool = False) -> dict[str, Any]:
    """Resume regrowth after networking becomes available post-install."""
    with tempfile.TemporaryDirectory(prefix="aurum-regrow-") as td:
        root = Path(td) / "root"
        root.mkdir()
        _run(["mount", device, str(root)], timeout=20)
        try:
            result = _chroot_regrow(root, offline=offline)
            _run(["sync"], check=False)
            return result
        finally:
            _run(["umount", str(root)], check=False, timeout=30)


def _finish_offline(result: dict[str, Any], root_device: str) -> bool:
    """Keep the live console actionable until the operator joins or defers."""
    while True:
        _title("NETWORK NEEDED", "The protected germ is safe. Current Aurum still needs networking to regrow.")
        print(f"Prepared root: {root_device}\n")
        print("  1. Join Wi-Fi now (recommended)")
        print("  2. Leave the germ prepared and finish after the next boot")
        raw = input("\nChoose: ").strip().lower()
        if raw in {"2", "later", "offline"}:
            return False
        if raw not in {"1", "join", "wifi", "wi-fi"}:
            continue
        if not _network_step():
            continue
        _title("GROWING AURUM", "Networking is ready. Growing current genetics beside the protected germ.")
        result["regrow"] = _regrow_installed_root(root_device)
        return True


def _repair_existing(entry: dict[str, Any], *, online: bool) -> dict[str, Any]:
    device = str(entry["device"])
    with tempfile.TemporaryDirectory(prefix="aurum-repair-") as td:
        root = Path(td) / "root"
        root.mkdir()
        _run(["mount", device, str(root)], timeout=20)
        try:
            bridged = bridge.install(root)
            if online:
                regrow = _chroot_regrow(root)
            elif (OFFLINE_CARRIER / "carrier.json").is_file():
                regrow = _chroot_regrow(root, offline=True)
            else:
                regrow = {"status": "deferred-offline"}
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

    if INSTALLED_MARKER.is_file() and not LIVE_MEDIUM.is_dir():
        return _installed_bootstrap_mode()

    detected = machine.detect()
    online = _network_step()

    _title("2 · MACHINE", f"Detected: {detected['architecture']} · {detected.get('model') or 'unknown model'}")
    existing = _installed_roots()
    action = "fresh"
    selected_existing: dict[str, Any] | None = None

    if len(existing) == 1:
        selected_existing = existing[0]
        action = "repair"
        print(
            "✓ Existing Aurum found — repair/reseed selected automatically:\n"
            f"  {selected_existing['device']} · {'germ-ready' if selected_existing['germ'] else 'legacy seed'}"
        )
    elif len(existing) > 1:
        print("Multiple Aurum installations were found. Choose which one to repair/reseed:\n")
        index = _choose(
            existing,
            lambda item: f"Repair / reseed {item['device']} · {'germ-ready' if item['germ'] else 'legacy seed'}",
        )
        if index is None:
            print("No unambiguous existing installation selected. Tiny Seed stopped without writing anything.")
            return 1
        selected_existing = existing[index]
        action = "repair"

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
                print("No target selected. Tiny Seed stopped without writing anything.")
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
    elif (OFFLINE_CARRIER / "carrier.json").is_file():
        print("Network is unavailable. A verified fallback phenotype will grow only in the inactive slot.")
    else:
        print("Offline mode: Tiny Seed will install/repair the protected germ; current genetics can regrow later.")
    confirm = input("\nContinue? [y/N]: ").strip().lower()
    if confirm not in {"y", "yes"}:
        print("Cancelled. No change made.")
        return 1

    try:
        if action == "repair" and selected_existing:
            result = _repair_existing(selected_existing, online=online)
            root_device = str(selected_existing["device"])
        else:
            assert selected_target is not None
            result = installer.install(
                selected_target["confirmation_code"],
                architecture=str(detected["architecture"]),
                model=detected.get("model"),
                regrow_current=online,
            )
            root_device = str(result.get("root_device") or "")
    except (bridge.BridgeError, installer.InstallError, network.NetworkError, RuntimeError) as exc:
        _title("STOPPED SAFELY", "Tiny Seed refused to continue rather than guess.")
        print(str(exc))
        return 2

    regrow = result.get("regrow") if isinstance(result, dict) else None
    if (
        isinstance(regrow, dict)
        and regrow.get("status") in {"deferred", "deferred-offline"}
        and root_device
        and (OFFLINE_CARRIER / "carrier.json").is_file()
    ):
        try:
            result["regrow"] = _regrow_installed_root(root_device, offline=True)
            regrow = result["regrow"]
        except RuntimeError as exc:
            _title("STOPPED SAFELY", "The protected germ is unchanged; offline candidate growth did not complete.")
            print(str(exc))
            return 2
    if isinstance(regrow, dict) and regrow.get("status") in {"deferred", "deferred-offline"}:
        if not root_device:
            _title("STOPPED SAFELY", "The protected germ is installed, but its root identity was not preserved.")
            print(json.dumps(result, indent=2, sort_keys=True))
            return 2
        try:
            online = _finish_offline(result, root_device)
        except (network.NetworkError, RuntimeError) as exc:
            _title("STOPPED SAFELY", "The protected germ is unchanged; online regrowth did not complete.")
            print(str(exc))
            return 2

    _title("READY", "Aurum has a protected germ and a recovery path.")
    print(json.dumps(result, indent=2, sort_keys=True))
    regrow = result.get("regrow") if isinstance(result, dict) else None
    if isinstance(regrow, dict) and regrow.get("status") == "trial-armed":
        print("\n✓ Current genetics were grown into the inactive slot.")
        print("  Power off, remove Tiny Seed, and boot the machine. The Guardian will promote or roll back automatically.")
    elif online:
        print("\nGenetics were staged as far as this platform currently allows. Keep Tiny Seed available as the recovery germ.")
    else:
        print("\nBoot is prepared. Connect networking later and Tiny Seed will finish current regrowth on the installed machine.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
