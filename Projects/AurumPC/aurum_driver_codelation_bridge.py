#!/usr/bin/env python3
"""Bridge exact PC-01 hardware evidence into Aurum's Codelation driver synthesizer.

The PC hardware lane captures exact machine facts. This bridge converts those
facts into the existing provenance-aware Codelation EvidenceClaim model so the
same deterministic reconciliation, candidate-interface, and read-only trace
verification machinery is used for real PC devices. No hardware I/O is done
here; the only physical observations consumed are files already captured by the
read-only PC lane.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "aurum-pc-codelation-driver-bridge-v1"
DEFAULT_WORKSPACE = Path(os.environ.get("AURUM_GIT_WORKSPACE", "/var/lib/aurum/workspace/BoxBrain"))
DEFAULT_STATE = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state")) / "driver-lab"


class BridgeError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _load_codelation(workspace: Path):
    path = workspace / "Projects" / "Codelation" / "driver_synthesis.py"
    if not path.is_file():
        raise BridgeError("Codelation driver_synthesis.py is unavailable")
    spec = importlib.util.spec_from_file_location(
        f"aurum_pc_codelation_driver_synthesis_{os.getpid()}_{time.time_ns()}", path
    )
    if spec is None or spec.loader is None:
        raise BridgeError("Codelation driver synthesizer could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _claim(module: Any, key: str, value: Any, source_kind: str, source_id: str, confidence: float):
    return module.EvidenceClaim(
        key=key,
        value=value,
        source_kind=source_kind,
        source_id=source_id,
        confidence=confidence,
    )


def _claims_for_device(module: Any, device: Mapping[str, Any], device_model: Mapping[str, Any]) -> list[Any]:
    identity = device_model.get("identity") if isinstance(device_model.get("identity"), dict) else {}
    observation = device_model.get("latest_observation") if isinstance(device_model.get("latest_observation"), dict) else {}
    module_info = device_model.get("module") if isinstance(device_model.get("module"), dict) else {}
    device_id = str(device.get("device_id") or device_model.get("device_id") or "unknown")
    claims: list[Any] = []

    for key in ("collection", "address", "name", "event", "card", "vendor", "device", "product", "serial", "manufacturer", "product_name", "model", "revision", "modalias", "class"):
        value = identity.get(key)
        if value is not None:
            claims.append(_claim(module, f"identity.{key}", value, "os_metadata", f"pc01-sysfs:{device_id}", 0.96))

    driver = identity.get("driver") or device_model.get("bound_driver")
    if driver:
        claims.append(_claim(module, "driver.bound_name", driver, "os_metadata", f"pc01-driver-link:{device_id}", 0.98))
        if module_info.get("available") and module_info.get("driver") == driver:
            claims.append(_claim(module, "driver.bound_name", driver, "reference_driver", f"linux-module:{driver}", 0.98))

    network = observation.get("network") if isinstance(observation.get("network"), dict) else None
    if network is not None:
        mapping = {
            "carrier": "interface.carrier",
            "operstate": "interface.operstate",
            "mtu": "interface.mtu",
        }
        for source_key, claim_key in mapping.items():
            value = network.get(source_key)
            if value is None:
                continue
            if identity.get(source_key) is not None:
                claims.append(_claim(module, claim_key, identity[source_key], "os_metadata", f"pc01-net-metadata:{device_id}", 0.96))
            claims.append(_claim(module, claim_key, value, "observation", f"pc01-read-only-net:{device_id}", 0.98))

    pci = observation.get("pci") if isinstance(observation.get("pci"), dict) else None
    if pci is not None:
        for key in ("enable", "numa_node", "runtime_status", "current_link_speed", "current_link_width"):
            if pci.get(key) is not None:
                claims.append(_claim(module, f"observation.pci.{key}", pci[key], "observation", f"pc01-read-only-pci:{device_id}", 0.95))

    usb = observation.get("usb") if isinstance(observation.get("usb"), dict) else None
    if usb is not None:
        for key in ("authorized", "speed", "configuration"):
            if usb.get(key) is not None:
                claims.append(_claim(module, f"observation.usb.{key}", usb[key], "observation", f"pc01-read-only-usb:{device_id}", 0.95))

    graphics = observation.get("graphics") if isinstance(observation.get("graphics"), dict) else None
    if graphics is not None and graphics.get("runtime_status") is not None:
        claims.append(_claim(module, "observation.graphics.runtime_status", graphics["runtime_status"], "observation", f"pc01-read-only-gpu:{device_id}", 0.95))

    block = observation.get("block") if isinstance(observation.get("block"), dict) else None
    if block is not None:
        for key in ("read_only", "removable"):
            if block.get(key) is not None:
                claims.append(_claim(module, f"observation.block.{key}", block[key], "observation", f"pc01-read-only-block:{device_id}", 0.95))
    return claims


def _verification_trace(module: Any, model: Mapping[str, Any]) -> dict[str, Any] | None:
    claims = model.get("claims") if isinstance(model.get("claims"), dict) else {}
    events = []
    step = 0
    for key, entry in sorted(claims.items()):
        if not isinstance(entry, dict) or entry.get("state") != "verified":
            continue
        events.append({"step": step, "claim_key": key, "observed_value": entry.get("value")})
        step += 1
    if not events:
        return None
    return {
        "schema": module.BEHAVIOR_TRACE_SCHEMA,
        "origin": "captured-read-only",
        "actuating": False,
        "physical_hardware_observation": True,
        "model_identity": model.get("model_identity"),
        "events": events,
    }


class DriverCodelationBridge:
    def __init__(self, *, workspace: Path = DEFAULT_WORKSPACE, state_dir: Path = DEFAULT_STATE) -> None:
        self.workspace = workspace
        self.state_dir = state_dir
        self.summary_path = state_dir / "codelation-bridge.json"

    def status(self) -> dict[str, Any]:
        value = _load_json(self.summary_path)
        return value or {"schema": SCHEMA, "status": "never-started"}

    def cycle(self) -> dict[str, Any]:
        latest = _load_json(self.state_dir / "latest-cycle.json")
        queue = latest.get("queue") if isinstance(latest.get("queue"), list) else []
        if not queue:
            raise BridgeError("adaptive driver inventory is unavailable; run the PC driver cycle first")
        module = _load_codelation(self.workspace)
        outputs: list[dict[str, Any]] = []
        for item in queue:
            if not isinstance(item, dict):
                continue
            model_path = Path(str(item.get("model") or ""))
            device_model = _load_json(model_path)
            if not device_model:
                continue
            claims = _claims_for_device(module, item, device_model)
            if not claims:
                continue
            behavior_model = module.reconcile_evidence(claims)
            candidate = module.synthesize_candidate_interface(behavior_model)
            device_dir = model_path.parent
            behavior_path = device_dir / "codelation-behavior-model.json"
            candidate_path = device_dir / "codelation-candidate-interface.json"
            _atomic_json(behavior_path, behavior_model)
            _atomic_json(candidate_path, candidate)
            trace = _verification_trace(module, behavior_model)
            verification = None
            if trace is not None:
                verification = module.verify_behavior_trace(behavior_model, trace)
                _atomic_json(device_dir / "codelation-read-only-trace.json", trace)
                _atomic_json(device_dir / "codelation-trace-verification.json", verification)
            model_claims = behavior_model.get("claims") if isinstance(behavior_model.get("claims"), dict) else {}
            verified = sum(1 for entry in model_claims.values() if isinstance(entry, dict) and entry.get("state") == "verified")
            uncertain = sum(1 for entry in model_claims.values() if isinstance(entry, dict) and entry.get("state") == "uncertain")
            outputs.append(
                {
                    "device_id": item.get("device_id"),
                    "risk_class": item.get("risk_class"),
                    "gated": bool(item.get("gated")),
                    "claims": len(model_claims),
                    "verified_claims": verified,
                    "uncertain_claims": uncertain,
                    "model_identity": behavior_model.get("model_identity"),
                    "candidate_identity": candidate.get("candidate_identity"),
                    "trace_status": verification.get("status") if isinstance(verification, dict) else "no-verified-claims",
                    "physical_hardware_proof": bool(verification and verification.get("physical_hardware_proof")),
                    "physical_write_authorized": bool((candidate.get("promotion_gates") or {}).get("physical_write_authorized")),
                    "behavior_model": str(behavior_path),
                    "candidate_interface": str(candidate_path),
                }
            )
        summary = {
            "schema": SCHEMA,
            "status": "cycle-complete",
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "devices": outputs,
            "devices_reconciled": len(outputs),
            "verified_claims": sum(item["verified_claims"] for item in outputs),
            "uncertain_claims": sum(item["uncertain_claims"] for item in outputs),
            "physical_write_authorized": False,
            "host_actuation": False,
            "source": "pc01-exact-hardware-plus-codelation-provenance-engine",
        }
        _atomic_json(self.summary_path, summary)
        return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bridge PC hardware evidence into Codelation driver synthesis")
    parser.add_argument("command", choices=("cycle", "status"))
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    bridge = DriverCodelationBridge(workspace=args.workspace, state_dir=args.state_dir)
    try:
        result = bridge.cycle() if args.command == "cycle" else bridge.status()
    except (BridgeError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "failed", "detail": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
