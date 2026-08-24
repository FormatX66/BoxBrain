#!/usr/bin/env python3
"""Install the protected Reseed Germ into an older Aurum installation.

The compatibility bridge is intentionally designed to run from external Tiny
Seed/recovery media while the target Aurum root is offline. It converts the
single legacy /opt/aurum runtime into slot A, installs the independent germ and
guardian outside the adaptive slot, and adds a bounded `reseed` command to the
legacy Aurum console. It never fetches current genetics and never promotes a
candidate; those are later germ operations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Sequence

GERM_FILES = (
    "GENETICS.json",
    "carrier.py",
    "reseed.py",
    "guardian.py",
    "recovery_ledger.py",
    "bridge.py",
    "germ_console.py",
    "machine.py",
    "network.py",
    "installer.py",
    "tinyseed.py",
    "bootstrap_console.py",
    "proof.py",
    "rollback_drill.py",
    "recovery_control.py",
    "recovery_poller.py",
    "triage.py",
)


class BridgeError(RuntimeError):
    pass


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def patch_console_file(path: Path) -> dict[str, Any]:
    """Add the germ command to a compatible bounded Aurum console.

    Two exact help shapes are supported: the physical Gen0 console and the
    current richer x86 console. Anything else fails closed.
    """
    text = path.read_text(encoding="utf-8")
    if "from aurum_germ import handle_reseed" in text:
        return {"status": "already-patched", "sha256": _sha256(path)}

    import_anchor = "from aurum_workspace import AurumWorkspace, WorkspaceError\n"
    old_help = '        "install confirm ERASE-CODE | reboot | poweroff | help",\n'
    current_help = '        "reboot | poweroff | help",\n'
    reboot_anchor = '        elif command == "reboot" and len(tokens) == 1:\n'
    if import_anchor not in text or reboot_anchor not in text:
        raise BridgeError("Aurum console does not match the safe germ bridge anchors")
    if old_help in text:
        help_replacement = (
            '        "install confirm ERASE-CODE | reseed status | reseed current authorize-network | "\n'
            '        "reseed commit SHA authorize-network | reseed rollback confirm | reboot | poweroff | help",\n'
        )
        text = text.replace(old_help, help_replacement, 1)
    elif current_help in text:
        help_replacement = (
            '        "reseed status | reseed current authorize-network | reseed commit SHA authorize-network | "\n'
            '        "reseed rollback confirm | reboot | poweroff | help",\n'
        )
        text = text.replace(current_help, help_replacement, 1)
    else:
        raise BridgeError("Aurum console help surface is not a supported germ bridge shape")

    text = text.replace(import_anchor, import_anchor + "from aurum_germ import handle_reseed\n", 1)
    text = text.replace(
        reboot_anchor,
        '        elif command == "reseed" and len(tokens) >= 1:\n'
        '            print(json.dumps(handle_reseed(tokens[1:]), indent=2, sort_keys=True), flush=True)\n'
        + reboot_anchor,
        1,
    )
    temporary = path.with_name(f".{path.name}.germ-patch.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.chmod(temporary, path.stat().st_mode & 0o777)
    os.replace(temporary, path)
    return {"status": "patched", "sha256": _sha256(path)}


def _install_units(root: Path) -> dict[str, Any]:
    systemd = root / "etc/systemd/system"
    wants = systemd / "multi-user.target.wants"
    timer_wants = systemd / "timers.target.wants"
    systemd.mkdir(parents=True, exist_ok=True)
    wants.mkdir(parents=True, exist_ok=True)
    timer_wants.mkdir(parents=True, exist_ok=True)

    resolved_candidates = (
        root / "lib/systemd/system/systemd-resolved.service",
        root / "usr/lib/systemd/system/systemd-resolved.service",
    )
    resolved_available = any(path.is_file() for path in resolved_candidates)
    resolved_target = (
        "/lib/systemd/system/systemd-resolved.service"
        if resolved_candidates[0].is_file()
        else "/usr/lib/systemd/system/systemd-resolved.service"
    )

    network_manager = root / "etc/NetworkManager/conf.d/10-aurum-resolved.conf"
    resolver = systemd / "aurum-resolver-link.service"
    if resolved_available:
        network_manager.parent.mkdir(parents=True, exist_ok=True)
        network_manager.write_text(
            "[main]\n"
            "dns=systemd-resolved\n"
            "rc-manager=symlink\n",
            encoding="utf-8",
        )
        resolver.write_text(
            "[Unit]\n"
            "Description=Restore the Aurum installed resolver link\n"
            "After=local-fs.target\n"
            "Before=NetworkManager.service aurum-pc-console.service\n\n"
            "[Service]\n"
            "Type=oneshot\n"
            "ExecStart=/bin/ln -sfn /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf\n\n"
            "[Install]\n"
            "WantedBy=multi-user.target\n",
            encoding="utf-8",
        )

    preflight = systemd / "aurum-germ-preflight.service"
    preflight.write_text(
        "[Unit]\n"
        "Description=Aurum protected germ preflight\n"
        "After=local-fs.target\n"
        "Before=aurum-pc-console.service\n\n"
        "OnFailure=aurum-triage.service\n\n"
        "[Service]\n"
        "Type=oneshot\n"
        "ExecStart=/usr/bin/python3 /usr/lib/aurum/germ/guardian.py preflight --reboot-on-rollback\n\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n",
        encoding="utf-8",
    )

    health = systemd / "aurum-germ-health.service"
    health.write_text(
        "[Unit]\n"
        "Description=Aurum protected germ candidate health gate\n"
        "After=aurum-germ-preflight.service\n\n"
        "OnFailure=aurum-triage.service\n\n"
        "[Service]\n"
        "Type=oneshot\n"
        "ExecStartPre=/bin/sleep 8\n"
        "ExecStart=/usr/bin/python3 /usr/lib/aurum/germ/guardian.py health-check --reboot-on-rollback\n\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n",
        encoding="utf-8",
    )

    triage = systemd / "aurum-triage.service"
    triage.write_text(
        "[Unit]\n"
        "Description=Aurum read-only failure triage receipt\n\n"
        "[Service]\n"
        "Type=oneshot\n"
        "ExecStart=/usr/bin/python3 /usr/lib/aurum/germ/triage.py\n"
        "StandardOutput=journal+console\n"
        "StandardError=journal+console\n",
        encoding="utf-8",
    )

    boot_proof = systemd / "aurum-boot-proof.service"
    boot_proof.write_text(
        "[Unit]\n"
        "Description=Aurum non-secret boot proof receipt\n"
        "After=local-fs.target aurum-germ-preflight.service\n"
        "OnFailure=aurum-triage.service\n\n"
        "[Service]\n"
        "Type=oneshot\n"
        "ExecStart=/usr/bin/python3 /usr/lib/aurum/germ/proof.py\n"
        "StandardOutput=journal+console\n"
        "StandardError=journal+console\n\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n",
        encoding="utf-8",
    )

    recovery_poll = systemd / "aurum-recovery-poll.service"
    recovery_poll.write_text(
        "[Unit]\n"
        "Description=Aurum signed remote recovery desired-state check\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n\n"
        "[Service]\n"
        "Type=oneshot\n"
        "ExecStart=/usr/bin/python3 /usr/lib/aurum/germ/recovery_poller.py\n"
        "SuccessExitStatus=2\n"
        "NoNewPrivileges=true\n",
        encoding="utf-8",
    )
    recovery_timer = systemd / "aurum-recovery-poll.timer"
    recovery_timer.write_text(
        "[Unit]\n"
        "Description=Periodically check Aurum signed recovery desired state\n\n"
        "[Timer]\n"
        "OnBootSec=2min\n"
        "OnUnitActiveSec=5min\n"
        "RandomizedDelaySec=30s\n"
        "Persistent=true\n"
        "Unit=aurum-recovery-poll.service\n\n"
        "[Install]\n"
        "WantedBy=timers.target\n",
        encoding="utf-8",
    )

    managed_units = [preflight.name, health.name, boot_proof.name]
    if resolved_available:
        managed_units.insert(0, resolver.name)
    for unit in managed_units:
        link = wants / unit
        try:
            link.unlink()
        except FileNotFoundError:
            pass
        link.symlink_to(Path("../") / unit)

    recovery_timer_link = timer_wants / recovery_timer.name
    recovery_timer_link.unlink(missing_ok=True)
    recovery_timer_link.symlink_to(Path("../") / recovery_timer.name)

    resolved_link = wants / "systemd-resolved.service"
    if resolved_available:
        try:
            resolved_link.unlink()
        except FileNotFoundError:
            pass
        resolved_link.symlink_to(resolved_target)
    return {
        "resolver_link_unit_installed": resolved_available and resolver.is_file(),
        "network_manager_resolved_config_installed": resolved_available and network_manager.is_file(),
        "systemd_resolved_available": resolved_available,
        "systemd_resolved_enabled": resolved_available and resolved_link.is_symlink(),
        "systemd_resolved_unit": resolved_target if resolved_available else None,
        "boot_proof_enabled": (wants / boot_proof.name).is_symlink(),
        "recovery_poll_timer_enabled": recovery_timer_link.is_symlink(),
        "triage_unit_installed": triage.is_file(),
    }


def _install_wrapper(root: Path) -> None:
    wrappers = {
        "aurum-reseed": "reseed.py",
        "aurum-rollback-drill": "rollback_drill.py",
        "aurum-recovery-poll": "recovery_poller.py",
        "aurum-triage": "triage.py",
    }
    root_dir = root / "usr/sbin"
    root_dir.mkdir(parents=True, exist_ok=True)
    for name, script in wrappers.items():
        wrapper = root_dir / name
        wrapper.write_text(
            f'#!/bin/sh\nexec /usr/bin/python3 /usr/lib/aurum/germ/{script} "$@"\n',
            encoding="utf-8",
        )
        os.chmod(wrapper, 0o755)


def _install_recovery_policy(root: Path, source: Path) -> dict[str, Any]:
    target = root / "etc/aurum"
    target.mkdir(parents=True, exist_ok=True)
    trust_target = target / "recovery-trusted-refs.json"
    authority_target = target / "recovery-authority.pem"
    trust_sources = (
        source.parent / "Recovery/trusted-refs.json",
        Path("/etc/aurum/recovery-trusted-refs.json"),
    )
    authority_sources = (
        source.parent / "Recovery/authority-public.pem",
        Path("/etc/aurum/recovery-authority.pem"),
    )
    trust_source = next((path for path in trust_sources if path.is_file()), None)
    authority_source = next((path for path in authority_sources if path.is_file()), None)
    if trust_source is not None:
        shutil.copy2(trust_source, trust_target)
        os.chmod(trust_target, 0o644)
    if authority_source is not None:
        shutil.copy2(authority_source, authority_target)
        os.chmod(authority_target, 0o644)
    return {
        "trust_policy_installed": trust_target.is_file(),
        "authority_enrolled": authority_target.is_file(),
        "polling_enabled": (root / "etc/systemd/system/timers.target.wants/aurum-recovery-poll.timer").is_symlink(),
    }


def _copy_germ(root: Path, source: Path) -> dict[str, str]:
    target = root / "usr/lib/aurum/germ"
    target.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    for name in GERM_FILES:
        src = source / name
        if not src.is_file():
            raise BridgeError(f"Tiny Seed germ payload is incomplete: {name}")
        dst = target / name
        shutil.copy2(src, dst)
        if dst.suffix == ".py":
            os.chmod(dst, 0o755)
        hashes[name] = _sha256(dst)
    return hashes


def install(root: Path, *, source_dir: Path | None = None) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise BridgeError("germ bridge requires root")
    root = root.resolve()
    source = (source_dir or Path(__file__).resolve().parent).resolve()
    if not (root / "etc/aurum-installed.json").is_file():
        raise BridgeError("target is not an installed Aurum root")

    runtime_path = root / "opt/aurum"
    slots_root = root / "var/lib/aurum/slots"
    germ_root = root / "var/lib/aurum/germ"
    state_file = germ_root / "slots.json"

    if runtime_path.is_symlink() and state_file.is_file():
        hashes = _copy_germ(root, source)
        resolver_repair = _install_units(root)
        _install_wrapper(root)
        recovery_control = _install_recovery_policy(root, source)
        return {
            "schema": "aurum-pre-germ-bridge-v1",
            "status": "already-bridged-refreshed-germ",
            "root": str(root),
            "germ_hashes": hashes,
            "resolver_repair": resolver_repair,
            "recovery_control": recovery_control,
            "live_phenotype_replaced": False,
        }

    if not runtime_path.is_dir() or runtime_path.is_symlink():
        raise BridgeError("legacy /opt/aurum runtime is missing or has an unknown layout")
    console = runtime_path / "aurum_console.py"
    if not console.is_file():
        raise BridgeError("legacy Aurum console is missing")

    original_console_hash = _sha256(console)
    backup_root = root / "var/lib/aurum/germ/backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(console, backup_root / f"aurum_console.{original_console_hash}.py")

    slot_a = slots_root / "A/opt/aurum"
    slot_b = slots_root / "B/opt/aurum"
    if slot_a.exists() or slot_b.exists():
        raise BridgeError("slot directories already exist but /opt/aurum is not germ-managed")
    slot_a.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(runtime_path), str(slot_a))
    runtime_path.symlink_to("/var/lib/aurum/slots/A/opt/aurum")

    hashes = _copy_germ(root, source)
    shutil.copy2(source / "germ_console.py", slot_a / "aurum_germ.py")
    os.chmod(slot_a / "aurum_germ.py", 0o755)
    patch = patch_console_file(slot_a / "aurum_console.py")

    state = {
        "schema": "aurum-germ-slots-v1",
        "active": "A",
        "lkg": "A",
        "trial": None,
        "trial_boots": 0,
        "quarantined": [],
        "last_result": "pre-germ-bridge-installed",
        "legacy_console_sha256": original_console_hash,
        "updated_at_unix": int(time.time()),
    }
    _atomic_json(state_file, state)
    resolver_repair = _install_units(root)
    _install_wrapper(root)
    recovery_control = _install_recovery_policy(root, source)

    receipt = {
        "schema": "aurum-pre-germ-bridge-receipt-v1",
        "status": "installed",
        "root": str(root),
        "active_slot": "A",
        "lkg_slot": "A",
        "legacy_console_sha256": original_console_hash,
        "patched_console": patch,
        "germ_hashes": hashes,
        "resolver_repair": resolver_repair,
        "recovery_control": recovery_control,
        "live_overwrite_allowed": False,
        "current_organism_preserved_as_slot_a": True,
        "installed_at_unix": int(time.time()),
    }
    _atomic_json(germ_root / "bridge-receipt.json", receipt)
    return receipt


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Install the Aurum pre-germ compatibility bridge")
    p.add_argument("command", choices=("install",))
    p.add_argument("--root", type=Path, required=True, help="mounted installed Aurum root")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = install(args.root)
    except BridgeError as exc:
        print(json.dumps({"status": "refused", "detail": str(exc)}, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
