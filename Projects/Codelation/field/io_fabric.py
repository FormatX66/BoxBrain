from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from aurum_field import Field


@dataclass(frozen=True)
class IOPort:
    name: str
    direction: str
    medium: str
    semantics: frozenset[str]
    permission: str = "none"
    realtime: bool = False
    privacy_sensitive: bool = False
    actuator: bool = False
    human_visible: bool = False
    traits: Mapping[str, object] | None = None


@dataclass(frozen=True)
class IOPlan:
    selected: tuple[str, ...]
    covered: frozenset[str]
    missing: frozenset[str]
    blocked: tuple[str, ...]


def default_io_catalog() -> tuple[IOPort, ...]:
    """Declarative Aurum I/O vocabulary; no port grants execution authority."""
    return (
        IOPort("keyboard-input", "in", "hid", frozenset({"human-text-input", "human-command-input", "discrete-input"}), realtime=True, human_visible=True),
        IOPort("pointer-input", "in", "hid", frozenset({"pointing-input", "selection-input", "gesture-input"}), realtime=True, human_visible=True),
        IOPort("touch-input", "in", "touch", frozenset({"pointing-input", "gesture-input", "continuous-input"}), realtime=True, human_visible=True),
        IOPort("gamepad-input", "in", "hid", frozenset({"button-input", "continuous-input", "directional-input"}), realtime=True, human_visible=True),
        IOPort("accessibility-switch-input", "in", "assistive", frozenset({"binary-input", "assistive-input"}), realtime=True, human_visible=True),
        IOPort("text-dialogue", "duplex", "text", frozenset({"natural-language-input", "natural-language-output", "human-readable"}), human_visible=True),
        IOPort("llm-dialogue", "duplex", "model", frozenset({"language-reasoning", "natural-language-input", "natural-language-output"}), permission="model-access", privacy_sensitive=True),
        IOPort("microphone-input", "in", "acoustic", frozenset({"audio-observation", "human-speech-input", "pressure-wave-observation"}), permission="microphone", realtime=True, privacy_sensitive=True),
        IOPort("speaker-output", "out", "acoustic", frozenset({"audio-emission", "machine-speech-output", "pressure-wave-emission"}), permission="audible-output", realtime=True, actuator=True, human_visible=True),
        IOPort("display-output", "out", "optical", frozenset({"visual-output", "human-readable", "structured-photon-emission"}), permission="visible-output", realtime=True, actuator=True, human_visible=True),
        IOPort("screen-observation", "in", "framebuffer", frozenset({"visual-observation", "screen-state-observation", "structured-photon-proxy"}), permission="screen-capture", realtime=True, privacy_sensitive=True),
        IOPort("camera-input", "in", "optical", frozenset({"visual-observation", "structured-photon-observation"}), permission="camera", realtime=True, privacy_sensitive=True),
        IOPort("haptic-output", "out", "tactile", frozenset({"tactile-output", "attention-output"}), permission="haptic-output", realtime=True, actuator=True, human_visible=True),
        IOPort("clipboard-duplex", "duplex", "shared-buffer", frozenset({"structured-text-transfer", "human-context-transfer"}), permission="clipboard", privacy_sensitive=True),
        IOPort("network-duplex", "duplex", "packet", frozenset({"packet-transport", "remote-capability-transport", "event-transport"}), permission="authorized-network-scope", realtime=True),
        IOPort("usb-duplex", "duplex", "usb", frozenset({"device-enumeration", "byte-transport", "power-observation", "physical-presence-evidence"}), permission="authorized-device-scope", realtime=True),
        IOPort("bluetooth-duplex", "duplex", "radio", frozenset({"short-range-radio", "device-discovery", "byte-transport", "signal-strength-observation"}), permission="authorized-device-scope", realtime=True),
        IOPort("serial-duplex", "duplex", "serial", frozenset({"byte-transport", "low-level-console", "device-telemetry"}), permission="authorized-device-scope", realtime=True),
        IOPort("gpio-duplex", "duplex", "electrical", frozenset({"digital-observation", "digital-actuation", "timing-signal"}), permission="hardware-actuation", realtime=True, actuator=True),
        IOPort("machine-bus-duplex", "duplex", "i2c-spi-can", frozenset({"device-register-transport", "sensor-transport", "actuator-transport"}), permission="hardware-actuation", realtime=True, actuator=True),
        IOPort("midi-duplex", "duplex", "midi", frozenset({"timed-event-input", "timed-event-output", "musical-control"}), permission="authorized-device-scope", realtime=True),
        IOPort("imu-input", "in", "motion", frozenset({"motion-observation", "orientation-observation", "acceleration-observation"}), permission="motion-sensor", realtime=True, privacy_sensitive=True),
        IOPort("location-input", "in", "gnss", frozenset({"location-observation", "time-observation"}), permission="location", privacy_sensitive=True),
        IOPort("power-thermal-input", "in", "telemetry", frozenset({"power-observation", "thermal-observation", "resource-health-observation"}), permission="device-telemetry"),
        IOPort("storage-duplex", "duplex", "storage", frozenset({"durable-byte-store", "durable-byte-recall", "capacity-observation"}), permission="authorized-storage-scope"),
    )


def plan_io(
    required: Iterable[str],
    *,
    available_ports: Iterable[str] | None = None,
    permissions: Iterable[str] = (),
    catalog: Sequence[IOPort] | None = None,
) -> IOPlan:
    """Choose a deterministic minimal-ish set of available ports that covers meaning."""
    ports = tuple(catalog or default_io_catalog())
    allowed_names = None if available_ports is None else set(available_ports)
    permission_set = set(permissions)
    remaining = set(required)
    selected: list[str] = []
    covered: set[str] = set()
    blocked: set[str] = set()

    candidates = [port for port in ports if allowed_names is None or port.name in allowed_names]
    while remaining:
        ranked = sorted(
            candidates,
            key=lambda port: (
                -len(port.semantics & remaining),
                port.privacy_sensitive,
                port.actuator,
                port.name,
            ),
        )
        if not ranked or not (ranked[0].semantics & remaining):
            break
        port = ranked[0]
        if port.permission != "none" and port.permission not in permission_set:
            blocked.add(port.name)
            candidates = [candidate for candidate in candidates if candidate.name != port.name]
            continue
        gain = port.semantics & remaining
        selected.append(port.name)
        covered.update(gain)
        remaining.difference_update(gain)
        candidates = [candidate for candidate in candidates if candidate.name != port.name]

    return IOPlan(
        selected=tuple(selected),
        covered=frozenset(covered),
        missing=frozenset(remaining),
        blocked=tuple(sorted(blocked)),
    )


def io_field(catalog: Sequence[IOPort] | None = None) -> Field:
    """Project the I/O vocabulary into declarative Field capability grains."""
    field = Field()
    refs = []
    for port in sorted(catalog or default_io_catalog(), key=lambda item: item.name):
        refs.append(
            field.add(
                "capability",
                {
                    "name": port.name,
                    "direction": port.direction,
                    "medium": port.medium,
                    "provides": sorted(port.semantics),
                    "permission": port.permission,
                    "realtime": port.realtime,
                    "privacy_sensitive": port.privacy_sensitive,
                    "actuator": port.actuator,
                    "human_visible": port.human_visible,
                    "traits": dict(port.traits or {}),
                },
            )
        )
    field.add("view", {"name": "aurum-universal-io", "ports": refs})
    return field


__all__ = ["IOPlan", "IOPort", "default_io_catalog", "io_field", "plan_io"]
