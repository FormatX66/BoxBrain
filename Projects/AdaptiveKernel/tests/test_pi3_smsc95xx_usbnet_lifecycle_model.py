from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from Projects.AdaptiveKernel.pi3_smsc95xx_usbnet_lifecycle_model import (
    _REQUIRED_FALSE,
    _SMSC_TOKENS,
    _USBNET_TOKENS,
    _verify_sealed,
    build_lifecycle_model,
    explore_state_graph,
    transition,
    LifecycleState,
)


def _seal(value: dict) -> dict:
    body = dict(value)
    body.pop("receipt_sha256", None)
    value["receipt_sha256"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    ).hexdigest()
    return value


SMSC_SOURCE = "\n".join(_SMSC_TOKENS) + "\n"
USBNET_SOURCE = "\n".join(_USBNET_TOKENS) + "\n"


def fixture_packet_differential() -> dict:
    return _seal(
        {
            "schema": "aurum.pi3.smsc95xx.packet-transfer-differential.v1",
            "state": "controlled-source-referenced-packet-differential-passed",
            "mismatch_count": 0,
            "authority": {key: False for key in _REQUIRED_FALSE},
            "invariants": {
                "live_pi_contacted": False,
                "usb_device_opened": False,
                "usb_transfer_submitted": False,
                "driver_binding_changed": False,
            },
        }
    )


def fixture_qpu() -> dict:
    return _seal(
        {
            "schema": "aurum-pi3-qpu-routing-reference-v1",
            "model": {
                "candidate_kind": "machine-experiment-paths",
                "hardware_digital_twin": False,
                "hardware_submission_performed": False,
                "submission": None,
            },
        }
    )


def fixture_sources() -> dict[str, str]:
    return {
        "raspberry-pi-linux-smsc95xx-c": SMSC_SOURCE,
        "upstream-linux-v6.18-smsc95xx-c": SMSC_SOURCE,
        "raspberry-pi-linux-usbnet-c": USBNET_SOURCE,
        "upstream-linux-v6.18-usbnet-c": USBNET_SOURCE,
    }


def fixture_manifest(sources: dict[str, str] | None = None) -> dict:
    values = sources or fixture_sources()
    return {
        "schema": "aurum-pi3-hardware-reference-manifest-v1",
        "sources": [
            {"id": key, "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest()}
            for key, value in values.items()
        ],
    }


class UsbnetLifecycleModelTests(unittest.TestCase):
    def build(self) -> dict:
        sources = fixture_sources()
        return build_lifecycle_model(
            packet_differential=fixture_packet_differential(),
            qpu_router=fixture_qpu(),
            reference_manifest=fixture_manifest(sources),
            sources=sources,
        )

    def test_builds_complete_sealed_zero_authority_graph(self):
        result = self.build()
        self.assertEqual(result["state"], "verified-offline-usbnet-lifecycle-fault-model")
        self.assertTrue(_verify_sealed(result))
        self.assertGreater(result["graph"]["state_count"], 10)
        self.assertEqual(
            result["graph"]["transition_count"],
            result["graph"]["state_count"] * 13,
        )
        self.assertEqual(len(result["graph"]["transitions"]), result["graph"]["transition_count"])
        self.assertTrue(all(result["graph"]["invariants"].values()))
        self.assertFalse(result["qpu"]["used"])
        self.assertFalse(result["qpu"]["router_is_hardware_digital_twin"])
        for key in _REQUIRED_FALSE:
            self.assertFalse(result["authority"][key])
        self.assertFalse(result["invariants"]["live_pi_contacted"])
        self.assertFalse(result["invariants"]["driver_binding_changed"])

    def test_suspended_fault_transition_is_refused_without_state_change(self):
        state = LifecycleState(present=True, bound=True, opened=True, suspended=True)
        next_state, accepted, reason = transition(state, "rx_halt")
        self.assertFalse(accepted)
        self.assertEqual(reason, "precondition-refused")
        self.assertEqual(next_state, state)

    def test_disconnect_and_reprobe_are_explicit_reversible_shadow_states(self):
        state = LifecycleState(present=True, bound=True, opened=True, carrier=True)
        disconnected, accepted, _ = transition(state, "disconnect")
        self.assertTrue(accepted)
        self.assertTrue(disconnected.disconnected)
        self.assertFalse(disconnected.present)
        reprobed, accepted, _ = transition(disconnected, "probe_success")
        self.assertTrue(accepted)
        self.assertTrue(reprobed.present)
        self.assertTrue(reprobed.bound)
        self.assertFalse(reprobed.disconnected)

    def test_graph_is_deterministic(self):
        first = explore_state_graph()
        second = explore_state_graph()
        self.assertEqual(first["transition_matrix_sha256"], second["transition_matrix_sha256"])
        self.assertEqual(first["states"], second["states"])

    def test_tampered_source_fails_closed(self):
        sources = fixture_sources()
        sources["raspberry-pi-linux-usbnet-c"] += "tamper"
        with self.assertRaisesRegex(ValueError, "hash does not match"):
            build_lifecycle_model(
                packet_differential=fixture_packet_differential(),
                qpu_router=fixture_qpu(),
                reference_manifest=fixture_manifest(),
                sources=sources,
            )

    def test_qpu_router_cannot_be_promoted_to_hardware_twin(self):
        qpu = fixture_qpu()
        qpu["model"]["hardware_digital_twin"] = True
        _seal(qpu)
        sources = fixture_sources()
        with self.assertRaisesRegex(ValueError, "hardware twin"):
            build_lifecycle_model(
                packet_differential=fixture_packet_differential(),
                qpu_router=qpu,
                reference_manifest=fixture_manifest(sources),
                sources=sources,
            )


class UsbnetLifecycleWorkflowTests(unittest.TestCase):
    def workflow(self) -> str:
        return (
            Path(__file__).parents[3] / ".github" / "workflows" / "aurum-pi3-smsc95xx-usbnet-lifecycle.yml"
        ).read_text(encoding="utf-8").lower()

    def test_workflow_is_host_only_and_main_gated(self):
        workflow = self.workflow()
        self.assertIn("runs-on: ubuntu-24.04", workflow)
        self.assertIn("if: github.ref == 'refs/heads/main'", workflow)
        self.assertNotIn("169.254.129.122", workflow)
        self.assertNotIn("ssh ", workflow)
        self.assertNotIn("self-hosted", workflow)

    def test_workflow_has_no_driver_or_usb_execution_path(self):
        workflow = self.workflow()
        for token in ("modprobe", "insmod", "modules_install", ".ko", "unbind", "usb_submit_urb", "libusb"):
            self.assertNotIn(token, workflow)


if __name__ == "__main__":
    unittest.main()
