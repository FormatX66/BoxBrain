#!/usr/bin/env python3
"""Adaptive exact-hardware driver synthesis lane for installed Aurum PCs.

This module starts the driver work without taking over hardware.  It learns an
exact device model from read-only Linux/sysfs observations, the currently proven
bound driver, module metadata, and repeated behavior snapshots.  It emits a
confidence-scored contract and may compile a deliberately non-binding shadow
kernel carrier when the exact kernel build toolchain is available.

The shadow carrier has no device-id table, no probe callback, no MMIO/PIO, and
is never loaded by this module.  Physical replacement remains a later, separate
one-target-at-a-time gate with backup, behavior comparison, and restore proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from aurum_hardware import collect_hardware_profile, derive_kernel_driver_plan

SCHEMA = "aurum-adaptive-driver-synthesis-v1"
MODEL_SCHEMA = "aurum-adaptive-driver-model-v1"
CONTRACT_SCHEMA = "aurum-adaptive-driver-contract-v1"
DEFAULT_STATE = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state")) / "driver-lab"
DEFAULT_POLICY = Path(__file__).with_name("pc01_autonomy_policy.json")
MAX_OBSERVATION_LINES = 128
Runner = Callable[..., subprocess.CompletedProcess[str]]


class DriverSynthesisError(RuntimeError):
    pass


def _run(arguments: list[str], *, timeout: int = 30, env: Mapping[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            arguments,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            env=dict(env) if env is not None else None,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise DriverSynthesisError(f"bounded driver operation failed: {type(exc).__name__}:{exc}") from exc


def _sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _canonical_hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _read(path: Path, default: str | None = None) -> str | None:
    try:
        value = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return default
    return value if value else default


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    os.chmod(path, 0o600)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_OBSERVATION_LINES:
            path.write_text("\n".join(lines[-MAX_OBSERVATION_LINES:]) + "\n", encoding="utf-8")
            os.chmod(path, 0o600)
    except OSError:
        pass


def load_policy(path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _identity(collection: str, device: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "address", "name", "event", "card", "vendor", "device", "product", "serial",
        "manufacturer", "product_name", "model", "revision", "modalias", "driver", "class",
    )
    return {
        "collection": collection,
        **{key: device.get(key) for key in keys if device.get(key) is not None},
    }


def _device_id(identity: Mapping[str, Any]) -> str:
    return _canonical_hash(identity)[:20]


def _risk_class(collection: str, device: Mapping[str, Any]) -> tuple[str, bool]:
    pci_class = str(device.get("class") or "").lower()
    if collection == "block_devices" or pci_class.startswith("0x01"):
        return "storage-or-boot-critical", True
    if collection == "network_interfaces" or pci_class.startswith("0x02"):
        return "network", False
    if collection == "graphics_devices" or pci_class.startswith("0x03"):
        return "graphics", False
    if collection == "input_devices":
        return "input", False
    if collection == "usb_devices":
        return "usb-peripheral", False
    return "general-device", False


def _priority(collection: str, device: Mapping[str, Any], gated: bool) -> int:
    if gated:
        return 100
    if device.get("modalias") and not device.get("driver"):
        return 0
    if collection == "network_interfaces" or str(device.get("class") or "").lower().startswith("0x02"):
        return 10
    if collection == "graphics_devices":
        return 20
    if collection == "input_devices":
        return 30
    if collection == "usb_devices":
        return 40
    return 50


def _module_metadata(driver: str | None, runner: Runner = _run) -> dict[str, Any]:
    if not driver:
        return {"available": False}
    modinfo = shutil.which("modinfo")
    if not modinfo:
        return {"available": False, "reason": "modinfo-missing", "driver": driver}
    fields: dict[str, Any] = {"available": True, "driver": driver}
    for field in ("filename", "version", "license", "description", "vermagic"):
        result = runner([modinfo, "-F", field, driver], timeout=10)
        value = result.stdout.strip().splitlines()
        fields[field] = value[0][:1000] if result.returncode == 0 and value else None
    alias = runner([modinfo, "-F", "alias", driver], timeout=10)
    if alias.returncode == 0:
        fields["aliases"] = [line.strip() for line in alias.stdout.splitlines() if line.strip()][:32]
    filename = fields.get("filename")
    if isinstance(filename, str) and filename.startswith("/"):
        fields["module_sha256"] = _sha256_file(Path(filename))
    return fields


def _network_observation(name: str) -> dict[str, Any]:
    root = Path("/sys/class/net") / name
    observation: dict[str, Any] = {
        "carrier": _read(root / "carrier"),
        "operstate": _read(root / "operstate"),
        "mtu": _read(root / "mtu"),
    }
    stats: dict[str, Any] = {}
    for key in ("rx_packets", "tx_packets", "rx_bytes", "tx_bytes", "rx_errors", "tx_errors"):
        value = _read(root / "statistics" / key)
        if value is not None:
            stats[key] = value
    observation["statistics"] = stats
    return observation


def _controlled_observation(collection: str, device: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "read_only": True,
        "raw_mmio_pio": False,
        "firmware_write": False,
    }
    if collection == "network_interfaces" and device.get("name"):
        result["network"] = _network_observation(str(device["name"]))
    elif collection == "pci_devices" and device.get("address"):
        root = Path("/sys/bus/pci/devices") / str(device["address"])
        result["pci"] = {
            "enable": _read(root / "enable"),
            "numa_node": _read(root / "numa_node"),
            "runtime_status": _read(root / "power" / "runtime_status"),
            "current_link_speed": _read(root / "current_link_speed"),
            "current_link_width": _read(root / "current_link_width"),
        }
    elif collection == "usb_devices" and device.get("address"):
        root = Path("/sys/bus/usb/devices") / str(device["address"])
        result["usb"] = {
            "authorized": _read(root / "authorized"),
            "speed": _read(root / "speed"),
            "configuration": _read(root / "bConfigurationValue"),
        }
    elif collection == "graphics_devices" and device.get("card"):
        root = Path("/sys/class/drm") / str(device["card"]) / "device"
        result["graphics"] = {"runtime_status": _read(root / "power" / "runtime_status")}
    elif collection == "block_devices" and device.get("name"):
        root = Path("/sys/class/block") / str(device["name"])
        result["block"] = {"read_only": _read(root / "ro"), "removable": _read(root / "removable")}
    return result


def _stable_observation(observation: Mapping[str, Any]) -> dict[str, Any]:
    stable = dict(observation)
    stable.pop("observed_at", None)
    network = stable.get("network")
    if isinstance(network, dict):
        network = dict(network)
        network.pop("statistics", None)
        stable["network"] = network
    return stable


def _confidence(identity: Mapping[str, Any], module: Mapping[str, Any], observation: Mapping[str, Any], samples: int) -> float:
    score = 0.20
    if any(identity.get(key) for key in ("vendor", "device", "product", "serial", "modalias")):
        score += 0.25
    if identity.get("modalias"):
        score += 0.15
    if identity.get("driver"):
        score += 0.15
    if module.get("available"):
        score += 0.10
    if module.get("module_sha256"):
        score += 0.05
    if len(observation) > 4:
        score += 0.05
    score += min(max(samples - 1, 0), 5) * 0.01
    return round(min(score, 0.95), 3)


def _contract(identity: Mapping[str, Any], risk: str, gated: bool, confidence: float, module: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": CONTRACT_SCHEMA,
        "device_identity": dict(identity),
        "risk_class": risk,
        "confidence": confidence,
        "evidence_sources": [
            "exact-os-hardware-metadata",
            "current-proven-driver-metadata" if module.get("available") else "current-driver-metadata-unavailable",
            "controlled-read-only-observation",
        ],
        "source_expansion_needed": [
            "vendor-datasheet-or-programming-manual",
            "reference-design-or-schematic",
            "errata",
            "proven-driver-behavior-comparison",
        ],
        "synthesis_stage": "gated-critical" if gated else "shadow-contract-ready",
        "validation_order": [
            "static-contract-validation",
            "shadow-compile-no-bind",
            "read-only-behavior-comparison",
            "reversible-one-target-physical-trial",
        ],
        "physical_load_authorized": False,
        "driver_replacement_authorized": False,
        "automatic_restore_required_before_future_swap": True,
        "forbidden_without_separate_gate": [
            "storage-or-boot-critical-replacement",
            "firmware-nvram-otp-fuse-write",
            "power-clock-voltage-thermal-reset-control",
            "unbounded-raw-mmio-pio",
        ],
    }


def _shadow_source(module_name: str, contract_digest: str, identity: Mapping[str, Any]) -> str:
    description = json.dumps({k: identity.get(k) for k in ("collection", "driver", "vendor", "device", "product") if identity.get(k)}, sort_keys=True)
    description = description.replace('"', '\\"')[:700]
    return f'''// Generated Aurum shadow carrier. It binds to no hardware and performs no I/O.\n#include <linux/init.h>\n#include <linux/module.h>\n\nstatic int __init {module_name}_init(void) {{ return 0; }}\nstatic void __exit {module_name}_exit(void) {{ }}\nmodule_init({module_name}_init);\nmodule_exit({module_name}_exit);\nMODULE_LICENSE("GPL");\nMODULE_DESCRIPTION("Aurum shadow contract {contract_digest[:16]} {description}");\n''' 


def _ensure_toolchain(policy: Mapping[str, Any], runner: Runner = _run) -> dict[str, Any]:
    build = Path("/lib/modules") / platform.release() / "build"
    if (build / "Makefile").is_file() and shutil.which("make"):
        return {"status": "ready", "build": str(build)}
    if not bool(policy.get("install_driver_build_toolchain")):
        return {"status": "missing", "build": str(build), "install_attempted": False}
    apt = shutil.which("apt-get")
    if not apt or os.geteuid() != 0:
        return {"status": "missing", "build": str(build), "install_attempted": False, "reason": "apt-or-root-unavailable"}
    env = dict(os.environ)
    env["DEBIAN_FRONTEND"] = "noninteractive"
    update = runner([apt, "update"], timeout=300, env=env)
    if update.returncode != 0:
        return {"status": "install-failed", "phase": "apt-update", "detail": update.stdout[-1000:]}
    headers = f"linux-headers-{platform.release()}"
    install = runner([apt, "install", "-y", "--no-install-recommends", "build-essential", headers], timeout=600, env=env)
    if install.returncode != 0:
        return {"status": "install-failed", "phase": "apt-install", "package": headers, "detail": install.stdout[-1500:]}
    ready = (build / "Makefile").is_file() and bool(shutil.which("make"))
    return {"status": "ready" if ready else "missing-after-install", "build": str(build), "install_attempted": True}


def _compile_shadow(device_dir: Path, identity: Mapping[str, Any], contract: Mapping[str, Any], policy: Mapping[str, Any], runner: Runner = _run) -> dict[str, Any]:
    driver_policy = policy.get("driver_policy") if isinstance(policy.get("driver_policy"), dict) else {}
    if not bool(driver_policy.get("compile_shadow_carrier", True)):
        return {"status": "disabled"}
    if bool(contract.get("physical_load_authorized")) or bool(driver_policy.get("load_synthesized_modules")):
        raise DriverSynthesisError("shadow compiler refuses any policy that authorizes automatic module loading")
    toolchain = _ensure_toolchain(policy, runner=runner)
    if toolchain.get("status") != "ready":
        return {"status": "toolchain-not-ready", "toolchain": toolchain, "loaded": False, "bound": False}
    digest = _canonical_hash(contract)
    module_name = "aurum_shadow_" + _device_id(identity)[:12]
    shadow = device_dir / "shadow"
    shadow.mkdir(parents=True, exist_ok=True)
    source = shadow / f"{module_name}.c"
    makefile = shadow / "Makefile"
    source.write_text(_shadow_source(module_name, digest, identity), encoding="utf-8")
    makefile.write_text(f"obj-m += {module_name}.o\n", encoding="utf-8")
    build = str(toolchain["build"])
    result = runner(["make", "-C", build, f"M={shadow}", "modules"], timeout=180)
    ko = shadow / f"{module_name}.ko"
    return {
        "status": "compiled" if result.returncode == 0 and ko.is_file() else "compile-failed",
        "module": module_name,
        "ko": str(ko) if ko.is_file() else None,
        "ko_sha256": _sha256_file(ko) if ko.is_file() else None,
        "contract_sha256": digest,
        "loaded": False,
        "bound": False,
        "detail": "" if result.returncode == 0 else result.stdout[-1500:],
        "toolchain": toolchain,
    }


class AdaptiveDriverSynthesizer:
    def __init__(
        self,
        *,
        state_dir: Path = DEFAULT_STATE,
        profile_provider: Callable[[], dict[str, Any]] = collect_hardware_profile,
        runner: Runner = _run,
        policy: Mapping[str, Any] | None = None,
    ) -> None:
        self.state_dir = state_dir
        self.profile_provider = profile_provider
        self.runner = runner
        self.policy = dict(policy or load_policy())

    @property
    def summary_path(self) -> Path:
        return self.state_dir / "latest-cycle.json"

    def status(self) -> dict[str, Any]:
        try:
            return json.loads(self.summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"schema": SCHEMA, "status": "never-started", "state_dir": str(self.state_dir)}

    def cycle(self) -> dict[str, Any]:
        profile = self.profile_provider()
        plan = derive_kernel_driver_plan(profile)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        _atomic_json(self.state_dir / "machine-profile.json", profile)
        _atomic_json(self.state_dir / "kernel-driver-plan.json", plan)
        queue: list[dict[str, Any]] = []
        collections = ("pci_devices", "usb_devices", "network_interfaces", "graphics_devices", "input_devices", "block_devices")
        for collection in collections:
            for raw in profile.get(collection, []) or []:
                if not isinstance(raw, dict):
                    continue
                identity = _identity(collection, raw)
                device_id = _device_id(identity)
                risk, gated = _risk_class(collection, raw)
                priority = _priority(collection, raw, gated)
                device_dir = self.state_dir / "devices" / device_id
                previous: dict[str, Any] = {}
                try:
                    previous = json.loads((device_dir / "model.json").read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    pass
                observation = _controlled_observation(collection, raw)
                module = _module_metadata(str(raw.get("driver")) if raw.get("driver") else None, runner=self.runner)
                stable_hash = _canonical_hash({"identity": identity, "observation": _stable_observation(observation), "module_sha256": module.get("module_sha256")})
                previous_samples = int(previous.get("samples") or 0)
                samples = previous_samples + 1
                confidence = _confidence(identity, module, observation, samples)
                contract = _contract(identity, risk, gated, confidence, module)
                model = {
                    "schema": MODEL_SCHEMA,
                    "device_id": device_id,
                    "identity": identity,
                    "risk_class": risk,
                    "gated": gated,
                    "priority": priority,
                    "confidence": confidence,
                    "samples": samples,
                    "stable_signature": stable_hash,
                    "stable_from_previous": bool(previous and previous.get("stable_signature") == stable_hash),
                    "bound_driver": raw.get("driver"),
                    "module": module,
                    "latest_observation": observation,
                    "contract_sha256": _canonical_hash(contract),
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                _atomic_json(device_dir / "model.json", model)
                _atomic_json(device_dir / "candidate-contract.json", contract)
                _append_jsonl(device_dir / "observations.jsonl", observation)
                queue.append({
                    "device_id": device_id,
                    "collection": collection,
                    "identity": identity,
                    "risk_class": risk,
                    "gated": gated,
                    "priority": priority,
                    "confidence": confidence,
                    "bound_driver": raw.get("driver"),
                    "model": str(device_dir / "model.json"),
                    "contract": str(device_dir / "candidate-contract.json"),
                })
        queue.sort(key=lambda item: (item["priority"], -item["confidence"], item["device_id"]))
        selectable = [item for item in queue if not item["gated"]]
        selected = selectable[0] if selectable else None
        shadow: dict[str, Any] | None = None
        if selected is not None:
            device_dir = self.state_dir / "devices" / selected["device_id"]
            contract = json.loads((device_dir / "candidate-contract.json").read_text(encoding="utf-8"))
            shadow = _compile_shadow(device_dir, selected["identity"], contract, self.policy, runner=self.runner)
            _atomic_json(device_dir / "shadow-build.json", shadow)
        summary = {
            "schema": SCHEMA,
            "status": "cycle-complete",
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "kernel": profile.get("kernel"),
            "devices_modeled": len(queue),
            "unresolved_devices": len(plan.get("unresolved_devices") or []),
            "selected_build": selected,
            "shadow_build": shadow,
            "queue": queue,
            "safety": {
                "read_only_observation": True,
                "physical_driver_swap": False,
                "module_load": False,
                "bound_driver_replacement": False,
                "firmware_write": False,
                "raw_mmio_pio": False,
                "storage_boot_critical_replacement": False,
            },
            "next": "repeat observations; enrich selected device with vendor/reference/errata evidence; synthesize behavior behind the same no-load gate",
        }
        _atomic_json(self.summary_path, summary)
        return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aurum adaptive exact-hardware driver synthesis")
    parser.add_argument("command", choices=("cycle", "status"))
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    synth = AdaptiveDriverSynthesizer(state_dir=args.state_dir, policy=load_policy(args.policy))
    try:
        result = synth.cycle() if args.command == "cycle" else synth.status()
    except (DriverSynthesisError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "failed", "detail": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
