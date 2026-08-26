"""Six-hour staged Adaptive Kernel laboratory for the pinned Raspberry Pi 3.

The laboratory moves from observation toward reversible kernel/driver canaries.
Every privileged mutation is temporary, locally timed for rollback, and followed
by identity, reference-driver, link, thermal, and power verification.  It never
writes firmware, boot configuration, the root filesystem image, or a replacement
kernel.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterable


EXPECTED_MODEL_MARKER = "Raspberry Pi 3"
EXPECTED_SERIAL = "00000000a6a7df7f"
EXPECTED_INTERFACE = "eth0"
EXPECTED_REFERENCE_DRIVER = "smsc95xx"
EXPECTED_ROOT_SOURCE = "/dev/mmcblk0p2"
MAX_SAFE_TEMPERATURE_C = 78.0
CURRENT_THROTTLE_MASK = 0xF

RISK_LEVELS = (
    "observe",
    "userspace-adaptation",
    "virtual-driver",
    "exact-header-module",
    "smsc95xx-feature-canary",
    "adaptive-runtime-pressure-canary",
)

OFFICIAL_REFERENCES = (
    "https://pip.raspberrypi.com/documents/RP-008340-DS",
    "https://www.raspberrypi.com/documentation/computers/raspberry-pi.html",
    "https://github.com/raspberrypi/linux/blob/rpi-6.18.y/drivers/net/usb/smsc95xx.c",
    "https://docs.kernel.org/devicetree/overlay-notes.html",
    "https://docs.kernel.org/livepatch/module-elf-format.html",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def risk_index(value: str) -> int:
    try:
        return RISK_LEVELS.index(value)
    except ValueError as exc:
        raise ValueError(f"unknown risk level: {value}") from exc


def stage_for_fraction(fraction: float) -> str:
    """Return the monotonically increasing stage for elapsed run fraction."""

    if fraction < 0.15:
        return "observe"
    if fraction < 0.30:
        return "userspace-adaptation"
    if fraction < 0.45:
        return "virtual-driver"
    if fraction < 0.60:
        return "exact-header-module"
    if fraction < 0.75:
        return "smsc95xx-feature-canary"
    return "adaptive-runtime-pressure-canary"


def policy_tunables(policy_id: str) -> tuple[int, int] | None:
    """Map a governor policy to the already-proven reversible sysctl surface."""

    return {
        "runtime-gen2-conserve-v1": (5, 10),
        "runtime-gen2-balanced-v1": (8, 16),
        "runtime-gen3-opportunistic-v1": (10, 20),
    }.get(policy_id)


def parse_throttled(value: str | None) -> dict[str, Any]:
    raw = (value or "").strip().lower().replace("throttled=", "")
    try:
        numeric = int(raw, 16)
    except ValueError:
        numeric = 0
    return {
        "raw": value,
        "value": numeric,
        "current_fault_mask": numeric & CURRENT_THROTTLE_MASK,
        "current_fault": bool(numeric & CURRENT_THROTTLE_MASK),
        "historical_fault": bool(numeric & 0xF0000),
    }


def parse_ethtool_features(text: str) -> dict[str, dict[str, Any]]:
    features: dict[str, dict[str, Any]] = {}
    for line in text.splitlines():
        match = re.match(r"^\s*([a-z0-9-]+):\s+(on|off)(?:\s+\[fixed\])?\s*$", line)
        if not match:
            continue
        features[match.group(1)] = {
            "enabled": match.group(2) == "on",
            "fixed": "[fixed]" in line,
        }
    return features


def choose_mutable_feature(features: dict[str, dict[str, Any]]) -> str | None:
    preferred = (
        "rx-checksumming",
        "tx-checksumming",
        "scatter-gather",
        "generic-segmentation-offload",
        "generic-receive-offload",
        "tcp-segmentation-offload",
    )
    for name in preferred:
        state = features.get(name)
        if state and not state["fixed"]:
            return name
    return None


def read_text(path: Path, default: str | None = None) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip("\x00\n ")
    except OSError:
        return default


def sha256_file(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command(
    args: Iterable[str], *, timeout: float = 30, check: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=check,
    )


def tool_path(name: str) -> str | None:
    """Resolve admin tools even when the unprivileged SSH PATH omits sbin."""

    discovered = shutil.which(name)
    if discovered:
        return discovered
    for directory in ("/usr/sbin", "/sbin", "/usr/bin", "/bin"):
        candidate = Path(directory) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def append_jsonl(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def root_source() -> str | None:
    findmnt = tool_path("findmnt")
    if not findmnt:
        return None
    result = command((findmnt, "-n", "-o", "SOURCE", "/"), timeout=5)
    return result.stdout.strip() if result.returncode == 0 else None


def reference_driver(interface: str = EXPECTED_INTERFACE) -> str | None:
    driver = Path("/sys/class/net") / interface / "device" / "driver"
    try:
        return driver.resolve(strict=True).name
    except OSError:
        return None


def module_file(name: str) -> Path | None:
    modinfo = tool_path("modinfo")
    if not modinfo:
        return None
    result = command((modinfo, "-n", name), timeout=5)
    if result.returncode != 0:
        return None
    path = Path(result.stdout.strip())
    return path if path.is_file() else None


def collect_identity() -> dict[str, Any]:
    model = read_text(Path("/proc/device-tree/model"))
    cpuinfo = read_text(Path("/proc/cpuinfo"), "") or ""
    serial_match = re.search(r"^Serial\s*:\s*([0-9a-fA-F]+)\s*$", cpuinfo, re.MULTILINE)
    compatible = (read_text(Path("/proc/device-tree/compatible"), "") or "").split("\x00")
    return {
        "model": model,
        "serial": serial_match.group(1).lower() if serial_match else None,
        "compatible": [item for item in compatible if item],
        "kernel_release": os.uname().release,
        "machine": os.uname().machine,
        "boot_id": read_text(Path("/proc/sys/kernel/random/boot_id")),
        "root_source": root_source(),
        "interface": EXPECTED_INTERFACE,
        "reference_driver": reference_driver(),
    }


def identity_matches(identity: dict[str, Any]) -> bool:
    return bool(
        EXPECTED_MODEL_MARKER in str(identity.get("model") or "")
        and identity.get("serial") == EXPECTED_SERIAL
        and identity.get("root_source") == EXPECTED_ROOT_SOURCE
        and identity.get("reference_driver") == EXPECTED_REFERENCE_DRIVER
    )


def temperature_c() -> float | None:
    raw = read_text(Path("/sys/class/thermal/thermal_zone0/temp"))
    try:
        return round(float(raw) / 1000.0, 3)
    except (TypeError, ValueError):
        return None


def throttled_state() -> dict[str, Any]:
    tool = tool_path("vcgencmd")
    if not tool:
        return parse_throttled(None)
    result = command((tool, "get_throttled"), timeout=5)
    return parse_throttled(result.stdout if result.returncode == 0 else None)


def network_stats(interface: str = EXPECTED_INTERFACE) -> dict[str, Any]:
    base = Path("/sys/class/net") / interface
    values: dict[str, Any] = {
        "operstate": read_text(base / "operstate"),
        "carrier": read_text(base / "carrier"),
        "mtu": read_text(base / "mtu"),
    }
    for name in ("rx_packets", "tx_packets", "rx_errors", "tx_errors", "rx_dropped", "tx_dropped"):
        raw = read_text(base / "statistics" / name)
        try:
            values[name] = int(raw) if raw is not None else None
        except ValueError:
            values[name] = None
    return values


def memory_stats() -> dict[str, int]:
    selected = {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree", "Dirty", "Writeback"}
    values: dict[str, int] = {}
    for line in (read_text(Path("/proc/meminfo"), "") or "").splitlines():
        key, _, remainder = line.partition(":")
        if key in selected:
            match = re.search(r"\d+", remainder)
            if match:
                values[key] = int(match.group(0))
    return values


def microbenchmark(seconds: float = 1.5) -> dict[str, Any]:
    started = time.perf_counter()
    operations = 0
    seed = b"aurum-pi3-adaptive-kernel"
    while time.perf_counter() - started < seconds:
        seed = hashlib.sha256(seed).digest()
        operations += 1
    cpu_seconds = time.perf_counter() - started

    block = os.urandom(1024 * 1024)
    disk_started = time.perf_counter()
    with tempfile.NamedTemporaryFile(prefix="aurum-lab-", dir="/tmp", delete=True) as handle:
        for _ in range(4):
            handle.write(block)
        handle.flush()
        os.fsync(handle.fileno())
        handle.seek(0)
        while handle.read(1024 * 1024):
            pass
    disk_seconds = max(time.perf_counter() - disk_started, 0.000001)
    return {
        "cpu_sha256_per_second": round(operations / cpu_seconds, 3),
        "disk_roundtrip_mib_per_second": round(8.0 / disk_seconds, 3),
        "cpu_seconds": round(cpu_seconds, 4),
        "disk_seconds": round(disk_seconds, 4),
    }


@dataclass(frozen=True)
class LabConfig:
    state_dir: Path
    duration_minutes: float
    sample_seconds: float
    benchmark_seconds: float
    risk_ceiling: str
    allow_mutation: bool


class Pi3OvernightLab:
    def __init__(self, config: LabConfig):
        self.config = config
        self.config.state_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.config.state_dir / "events.jsonl"
        self.samples_path = self.config.state_dir / "samples.jsonl"
        self.summary_path = self.config.state_dir / "summary.json"
        self.stop_requested = False
        self.stages: dict[str, dict[str, Any]] = {}
        self.original_identity: dict[str, Any] = {}
        self.original_driver_hash: str | None = None
        self.sudo_ready = False

    def emit(self, kind: str, **payload: Any) -> None:
        event = {"timestamp": utc_now(), "kind": kind, **payload}
        append_jsonl(self.events_path, event)
        print(json.dumps(event, sort_keys=True), flush=True)

    def request_stop(self, signum: int, _frame: Any) -> None:
        self.stop_requested = True
        self.emit("signal", signal=signum)

    def allowed(self, stage: str) -> bool:
        return risk_index(stage) <= risk_index(self.config.risk_ceiling)

    def sample(self, elapsed: float, stage: str) -> dict[str, Any]:
        temperature = temperature_c()
        throttle = throttled_state()
        sample = {
            "timestamp": utc_now(),
            "elapsed_seconds": round(elapsed, 3),
            "stage": stage,
            "temperature_c": temperature,
            "throttled": throttle,
            "loadavg": read_text(Path("/proc/loadavg")),
            "memory_kib": memory_stats(),
            "network": network_stats(),
            "reference_driver": reference_driver(),
        }
        append_jsonl(self.samples_path, sample)
        return sample

    @staticmethod
    def unsafe(sample: dict[str, Any]) -> str | None:
        temperature = sample.get("temperature_c")
        if isinstance(temperature, (int, float)) and temperature >= MAX_SAFE_TEMPERATURE_C:
            return "temperature-ceiling"
        if sample.get("throttled", {}).get("current_fault"):
            return "current-power-or-throttle-fault"
        if sample.get("reference_driver") != EXPECTED_REFERENCE_DRIVER:
            return "reference-driver-changed"
        if sample.get("network", {}).get("carrier") != "1":
            return "ethernet-carrier-lost"
        return None

    def timed_rollback(self, unit: str, delay_seconds: int, args: Iterable[str]) -> bool:
        systemd_run = tool_path("systemd-run")
        if not self.sudo_ready or not systemd_run:
            return False
        result = command(
            (
                "sudo",
                "-n",
                systemd_run,
                f"--unit={unit}",
                f"--on-active={delay_seconds}s",
                "--collect",
                *args,
            ),
            timeout=15,
        )
        return result.returncode == 0

    def cancel_rollback(self, unit: str) -> None:
        systemctl = tool_path("systemctl")
        if self.sudo_ready and systemctl:
            command(("sudo", "-n", systemctl, "stop", f"{unit}.timer", f"{unit}.service"), timeout=10)

    def stage_observe(self) -> dict[str, Any]:
        return {"state": "passed", "benchmark": microbenchmark(self.config.benchmark_seconds)}

    def stage_userspace_adaptation(self) -> dict[str, Any]:
        if not self.config.allow_mutation:
            return {"state": "held", "reason": "mutation-not-authorized"}
        if not self.sudo_ready or not tool_path("sysctl") or not tool_path("systemd-run"):
            return {"state": "held", "reason": "passwordless-sudo-or-local-watchdog-unavailable"}
        sysctl = tool_path("sysctl")
        if not sysctl:
            return {"state": "held", "reason": "sysctl-unavailable"}
        keys = ("vm.dirty_background_ratio", "vm.dirty_ratio")
        originals: dict[str, str] = {}
        for key in keys:
            observed = command((sysctl, "-n", key), timeout=5)
            if observed.returncode != 0:
                return {"state": "held", "reason": f"sysctl-unavailable:{key}"}
            originals[key] = observed.stdout.strip()
        candidates = ((5, 10), (8, 16), (10, 20))
        measurements: list[dict[str, Any]] = []
        for index, (background, dirty) in enumerate(candidates):
            unit = f"aurum-sysctl-rollback-{os.getpid()}-{index}"
            rollback = (
                sysctl,
                "-w",
                f"{keys[0]}={originals[keys[0]]}",
                f"{keys[1]}={originals[keys[1]]}",
            )
            if not self.timed_rollback(unit, 90, rollback):
                return {"state": "held", "reason": "local-sysctl-rollback-not-scheduled"}
            try:
                changed = command(
                    (
                        "sudo",
                        "-n",
                        sysctl,
                        "-w",
                        f"{keys[0]}={background}",
                        f"{keys[1]}={dirty}",
                    ),
                    timeout=10,
                )
                if changed.returncode != 0:
                    measurements.append({"candidate": [background, dirty], "state": "refused"})
                    continue
                measurements.append(
                    {
                        "candidate": [background, dirty],
                        "state": "measured",
                        "benchmark": microbenchmark(self.config.benchmark_seconds),
                    }
                )
            finally:
                command(
                    (
                        "sudo",
                        "-n",
                        sysctl,
                        "-w",
                        f"{keys[0]}={originals[keys[0]]}",
                        f"{keys[1]}={originals[keys[1]]}",
                    ),
                    timeout=10,
                )
                self.cancel_rollback(unit)
        measured = [item for item in measurements if item.get("state") == "measured"]
        if not measured:
            return {"state": "held", "reason": "no-tunable-candidate-measured", "measurements": measurements}
        winner = max(measured, key=lambda item: item["benchmark"]["disk_roundtrip_mib_per_second"])
        return {
            "state": "passed",
            "original": originals,
            "measurements": measurements,
            "recommended_candidate": winner["candidate"],
            "persistent_change": False,
        }

    def stage_virtual_driver(self) -> dict[str, Any]:
        if not self.config.allow_mutation:
            return {"state": "held", "reason": "mutation-not-authorized"}
        if not self.sudo_ready or not tool_path("modprobe") or not tool_path("systemd-run"):
            return {"state": "held", "reason": "module-tools-or-local-watchdog-unavailable"}
        modprobe = tool_path("modprobe")
        rmmod = tool_path("rmmod")
        if not modprobe or not rmmod:
            return {"state": "held", "reason": "module-tools-unavailable"}
        if Path("/sys/module/dummy").exists():
            return {"state": "held", "reason": "dummy-module-preexisting"}
        unit = f"aurum-dummy-rollback-{os.getpid()}"
        if not self.timed_rollback(unit, 120, (rmmod, "dummy")):
            return {"state": "held", "reason": "local-module-rollback-not-scheduled"}
        loaded = False
        try:
            result = command(("sudo", "-n", modprobe, "dummy", "numdummies=1"), timeout=15)
            loaded = result.returncode == 0 and Path("/sys/module/dummy").exists()
            if not loaded:
                return {"state": "held", "reason": "dummy-module-load-refused", "stderr": result.stderr[-500:]}
            return {
                "state": "passed",
                "module": "dummy",
                "dummy0_present": Path("/sys/class/net/dummy0").exists(),
                "reference_driver_during": reference_driver(),
            }
        finally:
            if loaded:
                command(("sudo", "-n", rmmod, "dummy"), timeout=15)
            self.cancel_rollback(unit)

    def stage_exact_header_module(self) -> dict[str, Any]:
        if not self.config.allow_mutation:
            return {"state": "held", "reason": "mutation-not-authorized"}
        build = Path("/lib/modules") / os.uname().release / "build"
        if not (build / "Makefile").is_file() or not tool_path("make") or not tool_path("gcc"):
            return {"state": "held", "reason": "exact-running-kernel-headers-or-build-tools-unavailable"}
        insmod = tool_path("insmod")
        rmmod = tool_path("rmmod")
        if not self.sudo_ready or not insmod or not rmmod or not tool_path("systemd-run"):
            return {"state": "held", "reason": "module-authority-or-watchdog-unavailable"}
        module_dir = self.config.state_dir / "module-canary"
        module_dir.mkdir(parents=True, exist_ok=True)
        (module_dir / "aurum_probe.c").write_text(
            "#include <linux/module.h>\n"
            "static int __init aurum_probe_init(void){pr_info(\"aurum_probe: loaded\\n\");return 0;}\n"
            "static void __exit aurum_probe_exit(void){pr_info(\"aurum_probe: unloaded\\n\");}\n"
            "module_init(aurum_probe_init); module_exit(aurum_probe_exit);\n"
            "MODULE_LICENSE(\"GPL\"); MODULE_DESCRIPTION(\"Aurum harmless overnight module canary\");\n",
            encoding="utf-8",
        )
        (module_dir / "Makefile").write_text("obj-m += aurum_probe.o\n", encoding="utf-8")
        compiled = command(("make", "-C", str(build), f"M={module_dir}", "modules"), timeout=180)
        module = module_dir / "aurum_probe.ko"
        if compiled.returncode != 0 or not module.is_file():
            return {"state": "held", "reason": "module-build-failed", "stderr": compiled.stderr[-1000:]}
        unit = f"aurum-probe-rollback-{os.getpid()}"
        if not self.timed_rollback(unit, 120, (rmmod, "aurum_probe")):
            return {"state": "held", "reason": "local-module-rollback-not-scheduled"}
        loaded = False
        try:
            inserted = command(("sudo", "-n", insmod, str(module)), timeout=15)
            loaded = inserted.returncode == 0 and Path("/sys/module/aurum_probe").exists()
            if not loaded:
                return {"state": "held", "reason": "custom-module-load-refused", "stderr": inserted.stderr[-500:]}
            modinfo = tool_path("modinfo")
            vermagic = None
            if modinfo:
                vermagic_result = command((modinfo, "-F", "vermagic", str(module)), timeout=5)
                if vermagic_result.returncode == 0:
                    vermagic = vermagic_result.stdout.strip()
            return {
                "state": "passed",
                "module_sha256": sha256_file(module),
                "vermagic": vermagic,
                "reference_driver_during": reference_driver(),
            }
        finally:
            if loaded:
                command(("sudo", "-n", rmmod, "aurum_probe"), timeout=15)
            self.cancel_rollback(unit)

    def stage_smsc95xx_feature(self) -> dict[str, Any]:
        if not self.config.allow_mutation:
            return {"state": "held", "reason": "mutation-not-authorized"}
        ethtool = tool_path("ethtool")
        if not ethtool or not self.sudo_ready or not tool_path("systemd-run"):
            return {"state": "held", "reason": "ethtool-authority-or-local-watchdog-unavailable"}
        before_result = command((ethtool, "-k", EXPECTED_INTERFACE), timeout=10)
        if before_result.returncode != 0:
            return {"state": "held", "reason": "driver-feature-query-failed"}
        features = parse_ethtool_features(before_result.stdout)
        feature = choose_mutable_feature(features)
        if feature is None:
            return {"state": "held", "reason": "no-mutable-safe-offload-feature"}
        original = bool(features[feature]["enabled"])
        changed_to = not original
        original_word = "on" if original else "off"
        changed_word = "on" if changed_to else "off"
        unit = f"aurum-smsc95xx-rollback-{os.getpid()}"
        if not self.timed_rollback(unit, 90, (ethtool, "-K", EXPECTED_INTERFACE, feature, original_word)):
            return {"state": "held", "reason": "local-driver-feature-rollback-not-scheduled"}
        try:
            changed = command(("sudo", "-n", ethtool, "-K", EXPECTED_INTERFACE, feature, changed_word), timeout=15)
            if changed.returncode != 0:
                return {"state": "held", "reason": "driver-feature-change-refused", "stderr": changed.stderr[-500:]}
            time.sleep(3)
            during = network_stats()
            benchmark = microbenchmark(self.config.benchmark_seconds)
            return {
                "state": "passed",
                "feature": feature,
                "original": original_word,
                "tested": changed_word,
                "network_during": during,
                "reference_driver_during": reference_driver(),
                "benchmark": benchmark,
                "persistent_change": False,
            }
        finally:
            command(("sudo", "-n", ethtool, "-K", EXPECTED_INTERFACE, feature, original_word), timeout=15)
            self.cancel_rollback(unit)

    def adaptive_sample(self, sample_id: str) -> dict[str, Any]:
        """Collect the exact evidence shape consumed by the offline governor."""

        memory = memory_stats()
        network = network_stats()
        load_text = read_text(Path("/proc/loadavg"), "") or ""
        try:
            load_1m = float(load_text.split()[0])
        except (IndexError, ValueError):
            load_1m = -1.0
        return {
            "sample_id": sample_id,
            "temperature_c": temperature_c(),
            "current_throttled": bool(throttled_state().get("current_fault")),
            "memory_available_bytes": memory.get("MemAvailable", -1) * 1024,
            "memory_total_bytes": memory.get("MemTotal", -1) * 1024,
            "load_1m": load_1m,
            "cpu_count": os.cpu_count() or 1,
            "ethernet": {
                "carrier": network.get("carrier") == "1",
                "operstate": network.get("operstate"),
                "reference_driver": reference_driver(),
                "rx_errors": network.get("rx_errors"),
                "tx_errors": network.get("tx_errors"),
                "rx_dropped": network.get("rx_dropped"),
                "tx_dropped": network.get("tx_dropped"),
            },
        }

    def stage_adaptive_runtime_pressure(self) -> dict[str, Any]:
        """Run a receipt-bound live policy under bounded, self-expiring pressure."""

        if not self.config.allow_mutation:
            return {"state": "held", "reason": "mutation-not-authorized"}
        sysctl = tool_path("sysctl")
        if not self.sudo_ready or not sysctl or not tool_path("systemd-run"):
            return {"state": "held", "reason": "sysctl-authority-or-local-watchdog-unavailable"}
        try:
            from adaptive_runtime import (
                ReversibleAuthority,
                evaluate_shadow_window,
                execute_runtime_recommendation,
                verify_receipt,
            )
        except ImportError:
            return {"state": "held", "reason": "adaptive-runtime-governor-unavailable"}

        keys = ("vm.dirty_background_ratio", "vm.dirty_ratio")
        originals: dict[str, str] = {}
        for key in keys:
            observed = command((sysctl, "-n", key), timeout=5)
            if observed.returncode != 0:
                return {"state": "held", "reason": f"sysctl-unavailable:{key}"}
            originals[key] = observed.stdout.strip()

        pressure_seconds = 150.0
        worker_count = max(1, min(4, os.cpu_count() or 1))
        worker_source = (
            "import hashlib,sys,time\n"
            "deadline=time.monotonic()+float(sys.argv[1])\n"
            "value=b'aurum-pi3-runtime-pressure'\n"
            "while time.monotonic()<deadline:\n"
            "    value=hashlib.sha256(value).digest()\n"
        )
        workers: list[subprocess.Popen[Any]] = []
        evidence: list[dict[str, Any]] = []
        pressure_started = time.monotonic()
        try:
            for _ in range(worker_count):
                workers.append(
                    subprocess.Popen(
                        (sys.executable, "-c", worker_source, str(pressure_seconds)),
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                )
            for index in range(5):
                target_elapsed = (index + 1) * (pressure_seconds / 5.0)
                while time.monotonic() - pressure_started < target_elapsed:
                    if self.stop_requested:
                        return {"state": "held", "reason": "stop-requested-during-pressure"}
                    time.sleep(0.5)
                observed = self.adaptive_sample(f"pressure-{index + 1}")
                evidence.append(observed)
                temperature = observed.get("temperature_c")
                if isinstance(temperature, (int, float)) and temperature >= 72.0:
                    return {
                        "state": "held",
                        "reason": "pressure-thermal-stop-before-live-policy",
                        "pressure_evidence": evidence,
                    }
                ethernet = observed.get("ethernet", {})
                if (
                    observed.get("current_throttled")
                    or ethernet.get("carrier") is not True
                    or ethernet.get("operstate") != "up"
                    or ethernet.get("reference_driver") != EXPECTED_REFERENCE_DRIVER
                    or any(
                        ethernet.get(name) != 0
                        for name in ("rx_errors", "tx_errors", "rx_dropped", "tx_dropped")
                    )
                ):
                    return {
                        "state": "held",
                        "reason": "pressure-physical-gate-failed-before-live-policy",
                        "pressure_evidence": evidence,
                    }
        finally:
            for worker in workers:
                if worker.poll() is None:
                    worker.terminate()
            for worker in workers:
                try:
                    worker.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait(timeout=5)

        shadow = evaluate_shadow_window(evidence, expected_reference_driver=EXPECTED_REFERENCE_DRIVER)
        if not verify_receipt(shadow):
            return {"state": "quarantined", "reason": "governor-shadow-receipt-invalid"}
        if shadow.get("decision", {}).get("state") == "quarantined":
            return {
                "state": "held",
                "reason": "governor-refused-pressure-window",
                "pressure_evidence": evidence,
                "shadow_receipt": shadow,
            }
        selected_id = str(shadow.get("decision", {}).get("selected_policy_id", ""))
        selected_tunables = policy_tunables(selected_id)
        if shadow.get("decision", {}).get("recommendation") != "shadow-change" or selected_tunables is None:
            return {
                "state": "passed",
                "reason": "governor-preserved-baseline-under-pressure",
                "pressure_evidence": evidence,
                "shadow_receipt": shadow,
                "execution_performed": False,
                "persistent_change": False,
            }

        rollback_target = f"{keys[0]}={originals[keys[0]]};{keys[1]}={originals[keys[1]]}"
        rollback_metadata = {
            "schema": "aurum-pi3-runtime-rollback-v1",
            "target": rollback_target,
            "originals": originals,
            "watchdog_seconds": 90,
            "reference_driver": EXPECTED_REFERENCE_DRIVER,
        }
        rollback_sha256 = hashlib.sha256(
            json.dumps(rollback_metadata, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        authority = ReversibleAuthority(
            authority_ref="user-risky-runtime-20260826",
            authorized=True,
            scope="adaptive-runtime-policy",
            reversible=True,
            shadow_receipt_sha256=str(shadow["receipt_sha256"]),
            rollback_target=rollback_target,
            rollback_receipt_sha256=rollback_sha256,
        )
        unit = f"aurum-runtime-rollback-{os.getpid()}"
        rollback_armed = False
        restored = False

        def executor(policy: dict[str, Any], rollback: dict[str, Any]) -> dict[str, Any]:
            nonlocal rollback_armed
            tunables = policy_tunables(str(policy.get("policy_id", "")))
            if tunables is None:
                return {"applied": False, "rollback_armed": False}
            rollback_args = (
                sysctl,
                "-w",
                f"{keys[0]}={originals[keys[0]]}",
                f"{keys[1]}={originals[keys[1]]}",
            )
            rollback_armed = self.timed_rollback(unit, 90, rollback_args)
            if not rollback_armed:
                return {"applied": False, "rollback_armed": False}
            changed = command(
                (
                    "sudo",
                    "-n",
                    sysctl,
                    "-w",
                    f"{keys[0]}={tunables[0]}",
                    f"{keys[1]}={tunables[1]}",
                ),
                timeout=10,
            )
            return {
                "applied": changed.returncode == 0,
                "rollback_armed": rollback_armed,
                "rollback_target": rollback["target"],
                "policy_id": policy.get("policy_id"),
                "applied_tunables": {keys[0]: tunables[0], keys[1]: tunables[1]},
                "network_prefetch_executed": False,
            }

        execution: dict[str, Any] = {}
        dwell_evidence: list[dict[str, Any]] = []
        failure_reason: str | None = None
        try:
            execution = execute_runtime_recommendation(
                shadow,
                active=True,
                authority=authority,
                executor=executor,
            )
            if execution.get("state") != "executed" or not verify_receipt(execution):
                failure_reason = "active-runtime-execution-not-proven"
            else:
                for index in range(3):
                    time.sleep(10)
                    observed = self.adaptive_sample(f"active-dwell-{index + 1}")
                    dwell_evidence.append(observed)
                    ethernet = observed.get("ethernet", {})
                    temperature = observed.get("temperature_c")
                    if (
                        (isinstance(temperature, (int, float)) and temperature >= 72.0)
                        or observed.get("current_throttled")
                        or ethernet.get("carrier") is not True
                        or ethernet.get("operstate") != "up"
                        or ethernet.get("reference_driver") != EXPECTED_REFERENCE_DRIVER
                        or any(
                            ethernet.get(name) != 0
                            for name in ("rx_errors", "tx_errors", "rx_dropped", "tx_dropped")
                        )
                    ):
                        failure_reason = "live-policy-dwell-gate-failed"
                        break
        finally:
            restore = command(
                (
                    "sudo",
                    "-n",
                    sysctl,
                    "-w",
                    f"{keys[0]}={originals[keys[0]]}",
                    f"{keys[1]}={originals[keys[1]]}",
                ),
                timeout=10,
            )
            restored = restore.returncode == 0
            if rollback_armed:
                self.cancel_rollback(unit)

        observed_after: dict[str, str] = {}
        for key in keys:
            observed = command((sysctl, "-n", key), timeout=5)
            observed_after[key] = observed.stdout.strip() if observed.returncode == 0 else ""
        restored = restored and observed_after == originals
        if not restored:
            return {
                "state": "quarantined",
                "reason": "runtime-policy-rollback-not-proven",
                "original": originals,
                "observed_after": observed_after,
                "shadow_receipt": shadow,
                "execution_receipt": execution,
            }
        if failure_reason:
            return {
                "state": "quarantined",
                "reason": failure_reason,
                "pressure_evidence": evidence,
                "dwell_evidence": dwell_evidence,
                "shadow_receipt": shadow,
                "execution_receipt": execution,
                "original": originals,
                "observed_after": observed_after,
                "rollback_proven": True,
            }
        return {
            "state": "passed",
            "reason": "receipt-bound-live-policy-executed-and-restored",
            "pressure_worker_count": worker_count,
            "pressure_seconds": pressure_seconds,
            "pressure_evidence": evidence,
            "shadow_receipt": shadow,
            "execution_receipt": execution,
            "dwell_evidence": dwell_evidence,
            "rollback_metadata": rollback_metadata,
            "rollback_receipt_sha256": rollback_sha256,
            "original": originals,
            "observed_after": observed_after,
            "execution_performed": True,
            "persistent_change": False,
            "network_prefetch_executed": False,
        }

    def run_stage(self, stage: str) -> dict[str, Any]:
        if stage in self.stages:
            return self.stages[stage]
        if not self.allowed(stage):
            result = {"state": "held", "reason": "above-authorized-risk-ceiling"}
        else:
            handlers = {
                "observe": self.stage_observe,
                "userspace-adaptation": self.stage_userspace_adaptation,
                "virtual-driver": self.stage_virtual_driver,
                "exact-header-module": self.stage_exact_header_module,
                "smsc95xx-feature-canary": self.stage_smsc95xx_feature,
                "adaptive-runtime-pressure-canary": self.stage_adaptive_runtime_pressure,
            }
            try:
                result = handlers[stage]()
            except Exception as exc:  # stage boundary: quarantine instead of replay
                result = {"state": "quarantined", "reason": f"{type(exc).__name__}:{exc}"}
        self.stages[stage] = result
        self.emit("stage", stage=stage, **result)
        return result

    def run(self) -> dict[str, Any]:
        started_at = utc_now()
        started = time.monotonic()
        duration_seconds = self.config.duration_minutes * 60.0
        self.original_identity = collect_identity()
        driver_path = module_file(EXPECTED_REFERENCE_DRIVER)
        self.original_driver_hash = sha256_file(driver_path)
        sudo = tool_path("sudo")
        self.sudo_ready = bool(sudo and command((sudo, "-n", "true"), timeout=5).returncode == 0)
        if not identity_matches(self.original_identity):
            summary = {
                "schema": "aurum-pi3-adaptive-kernel-overnight-v1",
                "state": "refused",
                "reason": "pinned-physical-identity-or-reference-driver-mismatch",
                "started_at": started_at,
                "completed_at": utc_now(),
                "identity_before": self.original_identity,
                "stages": {},
            }
            atomic_json(self.summary_path, summary)
            return summary

        self.emit(
            "started",
            duration_minutes=self.config.duration_minutes,
            risk_ceiling=self.config.risk_ceiling,
            allow_mutation=self.config.allow_mutation,
            sudo_ready=self.sudo_ready,
            identity=self.original_identity,
        )
        stop_reason: str | None = None
        next_benchmark = 0.0
        while not self.stop_requested:
            elapsed = time.monotonic() - started
            if elapsed >= duration_seconds:
                break
            fraction = min(1.0, elapsed / max(duration_seconds, 1.0))
            stage = stage_for_fraction(fraction)
            sample = self.sample(elapsed, stage)
            unsafe_reason = self.unsafe(sample)
            if unsafe_reason:
                stop_reason = unsafe_reason
                self.emit("safety-stop", reason=unsafe_reason, sample=sample)
                break
            stage_result = self.run_stage(stage)
            if stage_result.get("state") == "quarantined":
                stop_reason = f"stage-quarantined:{stage}"
                break
            if elapsed >= next_benchmark:
                self.emit("benchmark", stage=stage, result=microbenchmark(self.config.benchmark_seconds))
                next_benchmark = elapsed + max(self.config.sample_seconds * 5, 60.0)
            remaining = min(self.config.sample_seconds, duration_seconds - elapsed)
            time.sleep(max(0.25, remaining))

        # Materialize stages whose time boundary was not reached as explicit holds.
        for stage in RISK_LEVELS:
            if stage not in self.stages:
                self.stages[stage] = {
                    "state": "held",
                    "reason": "time-boundary-not-reached" if self.allowed(stage) else "above-authorized-risk-ceiling",
                }

        final_identity = collect_identity()
        final_driver_hash = sha256_file(module_file(EXPECTED_REFERENCE_DRIVER))
        final_network = network_stats()
        invariant_checks = {
            "identity_match": identity_matches(final_identity),
            "model_unchanged": final_identity.get("model") == self.original_identity.get("model"),
            "serial_unchanged": final_identity.get("serial") == self.original_identity.get("serial"),
            "boot_id_unchanged": final_identity.get("boot_id") == self.original_identity.get("boot_id"),
            "kernel_unchanged": final_identity.get("kernel_release") == self.original_identity.get("kernel_release"),
            "root_source_unchanged": final_identity.get("root_source") == self.original_identity.get("root_source"),
            "reference_driver_unchanged": final_identity.get("reference_driver") == EXPECTED_REFERENCE_DRIVER,
            "reference_driver_file_hash_unchanged": final_driver_hash == self.original_driver_hash,
            "ethernet_carrier_present": final_network.get("carrier") == "1",
        }
        verified = all(invariant_checks.values())
        passed = [name for name, result in self.stages.items() if result.get("state") == "passed"]
        summary = {
            "schema": "aurum-pi3-adaptive-kernel-overnight-v1",
            "state": (
                "quarantined"
                if stop_reason and stop_reason.startswith("stage-quarantined:")
                else "safety-stopped"
                if stop_reason
                else "completed"
                if verified
                else "quarantined"
            ),
            "reason": stop_reason if stop_reason else (None if verified else "final-invariant-failed"),
            "started_at": started_at,
            "completed_at": utc_now(),
            "requested_duration_minutes": self.config.duration_minutes,
            "actual_duration_seconds": round(time.monotonic() - started, 3),
            "risk_ceiling": self.config.risk_ceiling,
            "allow_mutation": self.config.allow_mutation,
            "sudo_ready": self.sudo_ready,
            "identity_before": self.original_identity,
            "identity_after": final_identity,
            "reference_driver_file": str(driver_path) if driver_path else None,
            "reference_driver_sha256_before": self.original_driver_hash,
            "reference_driver_sha256_after": final_driver_hash,
            "final_network": final_network,
            "stages": self.stages,
            "passed_stages": passed,
            "invariant_checks": invariant_checks,
            "persistent_kernel_or_driver_change": False,
            "firmware_changed": False,
            "boot_configuration_changed": False,
            "replacement_kernel_installed": False,
            "adaptive_kernel_claim": (
                "receipt-bound reversible live adaptive runtime canary under bounded pressure"
                if self.stages.get("adaptive-runtime-pressure-canary", {}).get("execution_performed")
                else "generation-1 reversible runtime adaptation prototype"
                if "userspace-adaptation" in passed
                else "observation-only prototype"
            ),
            "official_references": list(OFFICIAL_REFERENCES),
        }
        atomic_json(self.summary_path, summary)
        self.emit("completed", state=summary["state"], reason=summary["reason"], invariants=invariant_checks)
        return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--duration-minutes", type=float, default=330.0)
    parser.add_argument("--sample-seconds", type=float, default=60.0)
    parser.add_argument("--benchmark-seconds", type=float, default=1.5)
    parser.add_argument("--risk-ceiling", choices=RISK_LEVELS, default=RISK_LEVELS[-1])
    parser.add_argument("--allow-mutation", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not (1.0 <= args.duration_minutes <= 330.0):
        raise SystemExit("duration must be between 1 and 330 minutes")
    if not (1.0 <= args.sample_seconds <= 600.0):
        raise SystemExit("sample interval must be between 1 and 600 seconds")
    config = LabConfig(
        state_dir=args.state_dir,
        duration_minutes=args.duration_minutes,
        sample_seconds=args.sample_seconds,
        benchmark_seconds=max(0.1, min(args.benchmark_seconds, 10.0)),
        risk_ceiling=args.risk_ceiling,
        allow_mutation=args.allow_mutation,
    )
    lab = Pi3OvernightLab(config)
    for name in ("SIGTERM", "SIGINT", "SIGHUP"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lab.request_stop)
    summary = lab.run()
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 0 if summary["state"] in {"completed", "safety-stopped", "refused"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
