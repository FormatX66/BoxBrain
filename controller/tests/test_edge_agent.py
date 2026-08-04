import json
from email.message import Message

import pytest

from boxbrain_controller.edge_agent import (
    EdgeAgentConfigurationError,
    KaliPiEdgeAgentClient,
)


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self._body = json.dumps(payload).encode("utf-8")
        self.headers = Message()
        self.headers["Content-Type"] = "application/json"

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self, amount: int) -> bytes:
        return self._body[:amount]


def test_edge_agent_accepts_only_a_loopback_ssh_tunnel() -> None:
    KaliPiEdgeAgentClient("http://127.0.0.1:8787")
    KaliPiEdgeAgentClient("http://[::1]:8787")

    for endpoint in (
        "http://10.12.194.1:8787",
        "https://127.0.0.1:8787",
        "http://user:password@127.0.0.1:8787",
        "http://127.0.0.1:8787/untrusted",
    ):
        with pytest.raises(EdgeAgentConfigurationError):
            KaliPiEdgeAgentClient(endpoint)


def test_edge_agent_maps_status_without_exposing_raw_details(monkeypatch) -> None:
    payload = {
        "version": "0.6.0",
        "hostname": "kali-pi",
        "agent": {
            "target_count": 2,
            "recommendation_count": 3,
            "recommendations": [{"sensitive": "not returned"}],
        },
        "network": {"default_route": {"interface": "wlan0"}},
        "connection_map": {
            "schema_version": 1,
            "transports": [
                {
                    "id": "usb",
                    "label": "USB / USB-C",
                    "state": "connected",
                    "interfaces": ["usb0"],
                    "target_count": 1,
                    "capabilities": [
                        {
                            "id": "keyboard",
                            "state": "available",
                            "detail": "Explicit approval required before input",
                        },
                        {
                            "id": "mouse",
                            "state": "available",
                            "detail": "Explicit approval required before input",
                        },
                    ],
                }
            ],
        },
        "target_links": [
            {
                "diagnostics": {
                    "metrics": {
                        "wifi_saved_key_visible_to_restricted_account": False
                    }
                }
            }
        ],
    }
    monkeypatch.setattr(
        "boxbrain_controller.edge_agent.urlopen",
        lambda *_args, **_kwargs: FakeResponse(payload),
    )

    summary = KaliPiEdgeAgentClient("http://127.0.0.1:8787").describe()

    assert summary.connected is True
    assert summary.version == "0.6.0"
    assert summary.hostname == "kali-pi"
    assert summary.target_count == 2
    assert summary.recommendation_count == 3
    assert summary.network_interface == "wlan0"
    assert summary.wifi_credential_audit == "blocked"
    assert len(summary.connections) == 1
    assert summary.connections[0].id == "usb"
    assert {item.id for item in summary.connections[0].capabilities} == {
        "keyboard",
        "mouse",
    }
    assert "sensitive" not in summary.model_dump()


def test_edge_agent_is_offline_when_the_tunnel_is_unavailable(monkeypatch) -> None:
    def unavailable(*_args, **_kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr("boxbrain_controller.edge_agent.urlopen", unavailable)

    summary = KaliPiEdgeAgentClient("http://127.0.0.1:8787").describe()

    assert summary.connected is False
    assert summary.version is None
    assert summary.hostname is None
    assert summary.connections == ()


def test_edge_agent_discards_malformed_connection_capabilities(monkeypatch) -> None:
    payload = {
        "connection_map": {
            "transports": [
                {
                    "id": "bluetooth",
                    "label": "Bluetooth",
                    "state": "available",
                    "interfaces": [],
                    "target_count": -3,
                    "capabilities": [
                        {"id": "mouse", "state": "invented", "detail": "bad"},
                        {
                            "id": "keyboard",
                            "state": "requires-pairing",
                            "detail": "Explicit pairing required",
                        },
                    ],
                }
            ]
        }
    }
    monkeypatch.setattr(
        "boxbrain_controller.edge_agent.urlopen",
        lambda *_args, **_kwargs: FakeResponse(payload),
    )

    summary = KaliPiEdgeAgentClient("http://127.0.0.1:8787").describe()

    assert summary.connections[0].target_count == 0
    assert [item.id for item in summary.connections[0].capabilities] == ["keyboard"]
