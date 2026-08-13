from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from aurum_field import Field
from io_fabric import IOPort, default_io_catalog


@dataclass(frozen=True)
class IOBinding:
    port: str
    carrier: str
    state: str
    evidence: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class IOBindingStatus:
    bound: tuple[IOBinding, ...]
    unbound: tuple[str, ...]
    runtime_ready: tuple[str, ...]


def known_io_bindings() -> tuple[IOBinding, ...]:
    """Repository-evidenced carriers. These records do not claim current live-node reachability."""
    return (
        IOBinding(
            "keyboard-input",
            "boxbrain-usb-hid-kvm",
            "carrier-implemented",
            ("commit:c46df446bb5ad217fe31c26cebc1b0da5e001003",),
            ("not-yet-bound-to-aurum-native-io-dispatch",),
        ),
        IOBinding(
            "pointer-input",
            "boxbrain-usb-hid-kvm",
            "carrier-implemented",
            ("commit:c46df446bb5ad217fe31c26cebc1b0da5e001003",),
            ("not-yet-bound-to-aurum-native-io-dispatch",),
        ),
        IOBinding(
            "text-dialogue",
            "aurum-bounded-dialogue",
            "aurum-carrier-implemented",
            ("commit:dd442f3815ed6e9934569fe2c3f9e67bd9e1ec91",),
        ),
        IOBinding(
            "llm-dialogue",
            "aurum-bounded-dialogue-model-lane",
            "aurum-carrier-implemented",
            ("commit:dd442f3815ed6e9934569fe2c3f9e67bd9e1ec91",),
            ("requires-explicit-model-access",),
        ),
        IOBinding(
            "display-output",
            "vnc-novnc-browser-console",
            "human-console-carrier-implemented",
            ("pr:5", "pr:8-draft"),
            ("not-yet-a-native-aurum-display-compositor",),
        ),
        IOBinding(
            "network-duplex",
            "aurum-peer-and-arkmatx-carriers",
            "aurum-carrier-implemented",
            ("pr:17", "state:cycle-20"),
            ("target-authorization-and-fresh-identity-evidence-still-required",),
        ),
        IOBinding(
            "usb-duplex",
            "boxbrain-usb-transport",
            "carrier-implemented",
            ("pr:9",),
            ("device-scope-remains-explicit",),
        ),
    )


def binding_status(
    *,
    catalog: Sequence[IOPort] | None = None,
    bindings: Iterable[IOBinding] | None = None,
) -> IOBindingStatus:
    ports = tuple(catalog or default_io_catalog())
    records = tuple(bindings or known_io_bindings())
    known = {record.port for record in records}
    runtime_ready = tuple(
        sorted(
            record.port
            for record in records
            if record.state == "aurum-carrier-implemented"
        )
    )
    return IOBindingStatus(
        bound=tuple(sorted(records, key=lambda item: (item.port, item.carrier))),
        unbound=tuple(sorted(port.name for port in ports if port.name not in known)),
        runtime_ready=runtime_ready,
    )


def io_binding_field(status: IOBindingStatus | None = None) -> Field:
    current = status or binding_status()
    field = Field()
    refs = []
    for record in current.bound:
        refs.append(
            field.add(
                "relation",
                {
                    "port": record.port,
                    "carrier": record.carrier,
                    "state": record.state,
                    "evidence": list(record.evidence),
                    "limitations": list(record.limitations),
                },
            )
        )
    field.add(
        "view",
        {
            "name": "aurum-io-binding-status",
            "bindings": refs,
            "runtime_ready": list(current.runtime_ready),
            "unbound": list(current.unbound),
        },
    )
    return field


__all__ = ["IOBinding", "IOBindingStatus", "binding_status", "io_binding_field", "known_io_bindings"]
